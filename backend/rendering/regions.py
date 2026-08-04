"""Detect axis-aligned modelspace frames for region-aware visual analysis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DrawingRegion:
    """A named axis-aligned CAD extent selected for independent visual inference."""

    name: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y

    @property
    def area(self) -> float:
        return self.width * self.height


def _iou(first: DrawingRegion, second: DrawingRegion) -> float:
    width = max(0.0, min(first.max_x, second.max_x) - max(first.min_x, second.min_x))
    height = max(0.0, min(first.max_y, second.max_y) - max(first.min_y, second.min_y))
    intersection = width * height
    if intersection == 0.0:
        return 0.0
    return intersection / (first.area + second.area - intersection)


def _rectangle_from_polyline(entity: Any) -> tuple[float, float, float, float] | None:
    if entity.dxftype() != "LWPOLYLINE" or not entity.closed:
        return None
    points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
    if len(points) != 4:
        return None
    min_x, max_x = min(point[0] for point in points), max(point[0] for point in points)
    min_y, max_y = min(point[1] for point in points), max(point[1] for point in points)
    corners = {(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)}
    tolerance = max(max_x - min_x, max_y - min_y, 1.0) * 1e-6
    if all(any(abs(x - corner_x) <= tolerance and abs(y - corner_y) <= tolerance for corner_x, corner_y in corners) for x, y in points):
        return min_x, min_y, max_x, max_y
    return None


def _merged_axis_segments(
    layout: Any,
    *,
    tolerance: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Join touching horizontal and vertical LWPOLYLINE edges.

    Some CAD exporters write a drawing frame as several two-point polylines
    instead of one closed rectangle. The output tuples are ``(coordinate,
    start, end)`` for horizontal and vertical lines respectively.
    """
    horizontal: list[tuple[float, float, float]] = []
    vertical: list[tuple[float, float, float]] = []
    for entity in layout:
        if entity.dxftype() != "LWPOLYLINE":
            continue
        points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
        if len(points) < 2:
            continue
        pairs = list(zip(points, points[1:]))
        if entity.closed:
            pairs.append((points[-1], points[0]))
        for first, second in pairs:
            delta_x, delta_y = second[0] - first[0], second[1] - first[1]
            if abs(delta_y) <= tolerance and abs(delta_x) > tolerance:
                horizontal.append(((first[1] + second[1]) / 2, min(first[0], second[0]), max(first[0], second[0])))
            elif abs(delta_x) <= tolerance and abs(delta_y) > tolerance:
                vertical.append(((first[0] + second[0]) / 2, min(first[1], second[1]), max(first[1], second[1])))

    def merge(segments: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
        merged: list[tuple[float, float, float]] = []
        for coordinate, start, end in sorted(segments):
            if merged:
                previous_coordinate, previous_start, previous_end = merged[-1]
                if abs(coordinate - previous_coordinate) <= tolerance and start <= previous_end + tolerance:
                    merged[-1] = (previous_coordinate, previous_start, max(previous_end, end))
                    continue
            merged.append((coordinate, start, end))
        return merged

    return merge(horizontal), merge(vertical)


def _rectangles_from_segmented_polylines(
    layout: Any,
    *,
    min_width: float,
    min_height: float,
    tolerance: float,
) -> list[tuple[float, float, float, float]]:
    """Find large rectangles whose four sides are connected polyline segments."""
    horizontal, vertical = _merged_axis_segments(layout, tolerance=tolerance)
    long_horizontal = [item for item in horizontal if item[2] - item[1] >= min_width]
    long_vertical = [item for item in vertical if item[2] - item[1] >= min_height]
    rectangles: list[tuple[float, float, float, float]] = []
    span_groups: list[list[tuple[float, float, float]]] = []
    for segment in sorted(long_horizontal, key=lambda item: (item[1], item[2], item[0])):
        if span_groups:
            min_x, max_x = span_groups[-1][0][1], span_groups[-1][0][2]
            if abs(segment[1] - min_x) <= tolerance and abs(segment[2] - max_x) <= tolerance:
                span_groups[-1].append(segment)
                continue
        span_groups.append([segment])
    for group in span_groups:
        first, second = min(group, key=lambda item: item[0]), max(group, key=lambda item: item[0])
        min_y, max_y = first[0], second[0]
        if max_y - min_y < min_height:
            continue
        min_x, max_x = first[1], first[2]
        has_left_side = any(
            abs(coordinate - min_x) <= tolerance and start <= min_y + tolerance and end >= max_y - tolerance
            for coordinate, start, end in long_vertical
        )
        has_right_side = any(
            abs(coordinate - max_x) <= tolerance and start <= min_y + tolerance and end >= max_y - tolerance
            for coordinate, start, end in long_vertical
        )
        if has_left_side and has_right_side:
            rectangles.append((min_x, min_y, max_x, max_y))
    return rectangles


def detect_drawing_regions(layout: Any, *, max_regions: int = 8) -> list[DrawingRegion]:
    """Return large non-overlapping rectangular frames, ordered top-left to bottom-right.

    Prefer explicit closed LWPOLYLINE frames, then recover frames assembled from
    connected axis-aligned LWPOLYLINE segments. When a drawing has neither, the
    caller must fall back to the full modelspace.
    """
    from ezdxf import bbox

    extent = bbox.extents(layout)
    drawing_width = float(extent.extmax.x - extent.extmin.x)
    drawing_height = float(extent.extmax.y - extent.extmin.y)
    if drawing_width <= 0.0 or drawing_height <= 0.0:
        return []
    min_width, min_height = drawing_width * 0.18, drawing_height * 0.18
    min_area = drawing_width * drawing_height * 0.04
    tolerance = max(drawing_width, drawing_height, 1.0) * 1e-6
    candidates: list[DrawingRegion] = []
    for entity in layout:
        rectangle = _rectangle_from_polyline(entity)
        if rectangle is None:
            continue
        min_x, min_y, max_x, max_y = rectangle
        region = DrawingRegion("", min_x, min_y, max_x, max_y)
        if region.width >= min_width and region.height >= min_height and region.area >= min_area:
            candidates.append(region)
    for min_x, min_y, max_x, max_y in _rectangles_from_segmented_polylines(
        layout, min_width=min_width, min_height=min_height, tolerance=tolerance,
    ):
        region = DrawingRegion("", min_x, min_y, max_x, max_y)
        if region.area >= min_area:
            candidates.append(region)

    selected: list[DrawingRegion] = []
    for candidate in sorted(candidates, key=lambda item: item.area, reverse=True):
        if not any(_iou(candidate, prior) >= 0.9 for prior in selected):
            selected.append(candidate)
    selected.sort(key=lambda item: (-item.max_y, item.min_x))
    return [
        DrawingRegion(f"region_{index:02d}", item.min_x, item.min_y, item.max_x, item.max_y)
        for index, item in enumerate(selected[:max_regions], start=1)
    ]
