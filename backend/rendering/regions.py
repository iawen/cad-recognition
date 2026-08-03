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


def detect_drawing_regions(layout: Any, *, max_regions: int = 8) -> list[DrawingRegion]:
    """Return large non-overlapping rectangular frames, ordered top-left to bottom-right.

    Only explicit, closed, axis-aligned LWPOLYLINE frames are selected. When a
    drawing has no such frames, the caller must fall back to the full modelspace.
    """
    from ezdxf import bbox

    extent = bbox.extents(layout)
    drawing_width = float(extent.extmax.x - extent.extmin.x)
    drawing_height = float(extent.extmax.y - extent.extmin.y)
    if drawing_width <= 0.0 or drawing_height <= 0.0:
        return []
    min_width, min_height = drawing_width * 0.18, drawing_height * 0.18
    min_area = drawing_width * drawing_height * 0.04
    candidates: list[DrawingRegion] = []
    for entity in layout:
        rectangle = _rectangle_from_polyline(entity)
        if rectangle is None:
            continue
        min_x, min_y, max_x, max_y = rectangle
        region = DrawingRegion("", min_x, min_y, max_x, max_y)
        if region.width >= min_width and region.height >= min_height and region.area >= min_area:
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
