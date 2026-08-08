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


@dataclass(frozen=True)
class LayoutRegion:
    """A semantic, axis-aligned work area within one main drawing frame."""

    name: str
    kind: str
    region: DrawingRegion
    confidence: float
    evidence: dict[str, float | int | str]


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


def _is_title_frame_layer(layer: str) -> bool:
    """Return whether a layer name commonly stores title blocks or sheet frames."""
    normalized = layer.casefold()
    return "title" in normalized or "图框" in layer or "标题栏" in layer


def _axis_segments_in_region(
    layout: Any,
    region: DrawingRegion,
    *,
    tolerance: float,
) -> tuple[list[tuple[float, float, float]], list[tuple[float, float, float]]]:
    """Collect horizontal and vertical LINE/LWPOLYLINE edges inside one frame."""
    horizontal: list[tuple[float, float, float]] = []
    vertical: list[tuple[float, float, float]] = []

    def add_segment(first: tuple[float, float], second: tuple[float, float]) -> None:
        delta_x, delta_y = second[0] - first[0], second[1] - first[1]
        if abs(delta_y) <= tolerance and abs(delta_x) > tolerance:
            coordinate, start, end = (first[1] + second[1]) / 2, min(first[0], second[0]), max(first[0], second[0])
            if region.min_y - tolerance <= coordinate <= region.max_y + tolerance:
                horizontal.append((coordinate, max(start, region.min_x), min(end, region.max_x)))
        elif abs(delta_x) <= tolerance and abs(delta_y) > tolerance:
            coordinate, start, end = (first[0] + second[0]) / 2, min(first[1], second[1]), max(first[1], second[1])
            if region.min_x - tolerance <= coordinate <= region.max_x + tolerance:
                vertical.append((coordinate, max(start, region.min_y), min(end, region.max_y)))

    for entity in layout:
        entity_type = entity.dxftype()
        if entity_type == "LINE":
            add_segment(
                (float(entity.dxf.start.x), float(entity.dxf.start.y)),
                (float(entity.dxf.end.x), float(entity.dxf.end.y)),
            )
        elif entity_type == "LWPOLYLINE":
            points = [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]
            for first, second in zip(points, points[1:]):
                add_segment(first, second)
            if entity.closed and len(points) > 2:
                add_segment(points[-1], points[0])

    def merge(segments: list[tuple[float, float, float]]) -> list[tuple[float, float, float]]:
        merged: list[tuple[float, float, float]] = []
        for coordinate, start, end in sorted(segments):
            if end - start <= tolerance:
                continue
            if merged:
                previous_coordinate, previous_start, previous_end = merged[-1]
                if abs(coordinate - previous_coordinate) <= tolerance and start <= previous_end + tolerance:
                    merged[-1] = (previous_coordinate, previous_start, max(previous_end, end))
                    continue
            merged.append((coordinate, start, end))
        return merged

    return merge(horizontal), merge(vertical)


def _table_candidates(layout: Any, frame: DrawingRegion) -> list[LayoutRegion]:
    """Find table-like vector grids without treating every rectangle as a table.

    A candidate needs an outer four-sided rectangle plus at least one interior
    full-height and one interior full-width grid divider. This intentionally
    favors precision: unclassified areas remain electrical work areas.
    """
    tolerance = max(frame.width, frame.height, 1.0) * 1e-5
    horizontal, vertical = _axis_segments_in_region(layout, frame, tolerance=tolerance)
    min_width, min_height = frame.width * 0.06, frame.height * 0.06
    min_area = frame.area * 0.005
    long_horizontal = [segment for segment in horizontal if segment[2] - segment[1] >= min_width]
    long_vertical = [segment for segment in vertical if segment[2] - segment[1] >= min_height]
    # A large drawing can contain many short electrical lines. Bound candidate
    # generation to the longest grid-like segments to retain predictable cost.
    long_horizontal = sorted(long_horizontal, key=lambda item: item[2] - item[1], reverse=True)[:120]
    long_vertical = sorted(long_vertical, key=lambda item: item[2] - item[1], reverse=True)[:120]
    candidates: list[LayoutRegion] = []
    seen: list[DrawingRegion] = []
    for top_index, top in enumerate(long_horizontal):
        min_x, max_x = top[1], top[2]
        for bottom in long_horizontal[top_index + 1:]:
            if abs(bottom[1] - min_x) > tolerance * 4 or abs(bottom[2] - max_x) > tolerance * 4:
                continue
            min_y, max_y = min(top[0], bottom[0]), max(top[0], bottom[0])
            candidate = DrawingRegion("", min_x, min_y, max_x, max_y)
            if candidate.width < min_width or candidate.height < min_height or candidate.area < min_area:
                continue
            if candidate.area > frame.area * 0.75:
                continue
            left = any(abs(item[0] - min_x) <= tolerance * 4 and item[1] <= min_y + tolerance and item[2] >= max_y - tolerance for item in long_vertical)
            right = any(abs(item[0] - max_x) <= tolerance * 4 and item[1] <= min_y + tolerance and item[2] >= max_y - tolerance for item in long_vertical)
            if not left or not right:
                continue
            interior_vertical = {
                round(item[0] / tolerance)
                for item in long_vertical
                if min_x + tolerance * 4 < item[0] < max_x - tolerance * 4
                and item[1] <= min_y + candidate.height * 0.15
                and item[2] >= max_y - candidate.height * 0.15
            }
            interior_horizontal = {
                round(item[0] / tolerance)
                for item in long_horizontal
                if min_y + tolerance * 4 < item[0] < max_y - tolerance * 4
                and item[1] <= min_x + candidate.width * 0.15
                and item[2] >= max_x - candidate.width * 0.15
            }
            # A single header divider can also occur in a circuit panel.
            # Component schedules contain repeated cells in both directions.
            if len(interior_vertical) < 2 or len(interior_horizontal) < 2:
                continue
            horizontal_coordinates = [min_y, *(value * tolerance for value in interior_horizontal), max_y]
            vertical_coordinates = [min_x, *(value * tolerance for value in interior_vertical), max_x]
            horizontal_gaps = [second - first for first, second in zip(sorted(horizontal_coordinates), sorted(horizontal_coordinates)[1:])]
            vertical_gaps = [second - first for first, second in zip(sorted(vertical_coordinates), sorted(vertical_coordinates)[1:])]
            gap_ratio = max(max(horizontal_gaps) / max(min(horizontal_gaps), tolerance), max(vertical_gaps) / max(min(vertical_gaps), tolerance))
            # A schematic placed above a schedule can reuse its column edges.
            # The resulting enclosing rectangle has one or more radically
            # taller "rows" than the repeated schedule cells. A ratio above
            # six is treated as a mixed schematic/grid enclosure, not a table.
            if gap_ratio > 6:
                continue
            grid_score = min(1.0, (len(interior_vertical) + len(interior_horizontal)) / 6)
            grid_density = round(
                ((len(interior_vertical) + 1) * (len(interior_horizontal) + 1))
                / max((candidate.width / frame.width) * (candidate.height / frame.height), 0.01),
                3,
            )
            schedule_score = round(
                ((len(interior_vertical) + 1) * (len(interior_horizontal) + 1))
                / max(((candidate.width / frame.width) * (candidate.height / frame.height)) ** 0.5, 0.1)
                / (1 + min(gap_ratio, 60.0) / 20.0),
                3,
            )
            confidence = round(0.70 + 0.30 * grid_score, 3)
            if any(_iou(candidate, prior) >= 0.85 for prior in seen):
                continue
            seen.append(candidate)
            candidates.append(LayoutRegion(
                name="", kind="table", region=candidate, confidence=confidence,
                evidence={
                    "interior_vertical_dividers": len(interior_vertical),
                    "interior_horizontal_dividers": len(interior_horizontal),
                    "grid_score": round(grid_score, 3),
                    "grid_density": grid_density,
                    "max_to_min_grid_gap_ratio": round(gap_ratio, 3),
                    "schedule_score": schedule_score,
                },
            ))
    selected: list[LayoutRegion] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (float(item.evidence["schedule_score"]), float(item.evidence["grid_density"]), item.region.area),
        reverse=True,
    ):
        # Interior grid rows and columns also form valid rectangles. They are
        # table cells, not independent table regions, so retain only the outer
        # table candidate when a candidate is enclosed by one already selected.
        if any(
            prior.region.min_x <= candidate.region.min_x + tolerance
            and prior.region.max_x >= candidate.region.max_x - tolerance
            and prior.region.min_y <= candidate.region.min_y + tolerance
            and prior.region.max_y >= candidate.region.max_y - tolerance
            for prior in selected
        ):
            continue
        # A wide outline can contain both an upper electrical schematic and a
        # lower schedule. Once the denser lower schedule was selected, retain
        # it and reject the larger, less table-like enclosing rectangle.
        if any(
            candidate.region.min_x <= prior.region.min_x + tolerance
            and candidate.region.max_x >= prior.region.max_x - tolerance
            and candidate.region.min_y <= prior.region.min_y + tolerance
            and candidate.region.max_y >= prior.region.max_y - tolerance
            and float(candidate.evidence["schedule_score"]) <= float(prior.evidence["schedule_score"])
            for prior in selected
        ):
            continue
        if any(_iou(candidate.region, prior.region) >= 0.30 for prior in selected):
            continue
        selected.append(candidate)
        if len(selected) >= 16:
            break
    return selected


def _primary_schedule_region(
    candidates: list[LayoutRegion],
    frame: DrawingRegion,
    *,
    tolerance: float,
) -> LayoutRegion | None:
    """Combine one dense, aligned schedule into a single table work area.

    Electrical drawings often place a circuit panel directly above its
    component-quantity schedule and reuse some of the same columns. Candidate
    grids are consequently split at header boundaries.  Group only aligned,
    nearby grid bands and retain the strongest group; isolated title-block
    tables are intentionally not separate recognition regions.
    """
    groups: list[list[LayoutRegion]] = []
    for candidate in sorted(candidates, key=lambda item: item.region.min_y):
        for group in groups:
            reference = group[0].region
            same_columns = (
                abs(candidate.region.min_x - reference.min_x) <= tolerance * 4
                and abs(candidate.region.max_x - reference.max_x) <= tolerance * 4
            )
            group_max_y = max(item.region.max_y for item in group)
            if same_columns and candidate.region.min_y <= group_max_y + frame.height * 0.12:
                group.append(candidate)
                break
        else:
            groups.append([candidate])

    scored_groups: list[tuple[float, DrawingRegion, list[LayoutRegion]]] = []
    for group in groups:
        region = DrawingRegion(
            "",
            min(item.region.min_x for item in group),
            min(item.region.min_y for item in group),
            max(item.region.max_x for item in group),
            max(item.region.max_y for item in group),
        )
        score = sum(float(item.evidence["schedule_score"]) for item in group)
        # A multi-band schedule is more reliable than an isolated title block.
        if len(group) > 1:
            score *= 1.15
        scored_groups.append((score, region, group))
    if not scored_groups:
        return None

    score, region, group = max(scored_groups, key=lambda item: (item[0], item[1].area))
    return LayoutRegion(
        name="",
        kind="table",
        region=region,
        confidence=round(min(0.99, sum(item.confidence for item in group) / len(group)), 3),
        evidence={
            "source": "dense_aligned_schedule_grid",
            "grid_band_count": len(group),
            "schedule_score": round(score, 3),
            "candidate_extents": "; ".join(
                f"[{item.region.min_x:.3f},{item.region.min_y:.3f},{item.region.max_x:.3f},{item.region.max_y:.3f}]"
                for item in group
            ),
        },
    )


def _largest_electrical_region(frame: DrawingRegion, table: DrawingRegion, *, tolerance: float) -> DrawingRegion:
    """Return one surrounding work area; regions may intentionally overlap."""
    choices = [
        DrawingRegion("", frame.min_x, table.max_y, frame.max_x, frame.max_y),
        DrawingRegion("", frame.min_x, frame.min_y, frame.max_x, table.min_y),
        DrawingRegion("", frame.min_x, frame.min_y, table.min_x, frame.max_y),
        DrawingRegion("", table.max_x, frame.min_y, frame.max_x, frame.max_y),
    ]
    valid = [item for item in choices if item.width > tolerance and item.height > tolerance]
    # A schedule can touch a frame edge. In that case the full frame is safer
    # than returning no electrical inference area.
    return max(valid, key=lambda item: item.area) if valid else frame


def _merge_rectangles(regions: list[DrawingRegion], tolerance: float) -> list[DrawingRegion]:
    """Merge adjacent partition cells when their union remains rectangular."""
    pending = list(regions)
    changed = True
    while changed:
        changed = False
        for index, first in enumerate(pending):
            for second_index in range(index + 1, len(pending)):
                second = pending[second_index]
                same_vertical_span = abs(first.min_y - second.min_y) <= tolerance and abs(first.max_y - second.max_y) <= tolerance
                same_horizontal_span = abs(first.min_x - second.min_x) <= tolerance and abs(first.max_x - second.max_x) <= tolerance
                touching_x = abs(first.max_x - second.min_x) <= tolerance or abs(second.max_x - first.min_x) <= tolerance
                touching_y = abs(first.max_y - second.min_y) <= tolerance or abs(second.max_y - first.min_y) <= tolerance
                if same_vertical_span and touching_x:
                    merged = DrawingRegion("", min(first.min_x, second.min_x), first.min_y, max(first.max_x, second.max_x), first.max_y)
                elif same_horizontal_span and touching_y:
                    merged = DrawingRegion("", first.min_x, min(first.min_y, second.min_y), first.max_x, max(first.max_y, second.max_y))
                else:
                    continue
                pending[index] = merged
                pending.pop(second_index)
                changed = True
                break
            if changed:
                break
    return pending


def detect_frame_layout_regions(layout: Any, frame: DrawingRegion) -> list[LayoutRegion]:
    """Return at most one electrical and one table region for a main frame.

    The areas intentionally may overlap. This keeps electrical recognition from
    losing components at a shared schematic/schedule boundary and gives manual
    review exactly two meaningful images rather than fragmented grid cells.
    """
    tolerance = max(frame.width, frame.height, 1.0) * 1e-6
    table = _primary_schedule_region(_table_candidates(layout, frame), frame, tolerance=tolerance)
    if table is None:
        return [LayoutRegion(
            f"{frame.name}_electrical", "electrical", frame, 1.0,
            {"source": "full_frame_without_confirmed_schedule"},
        )]

    table_region = DrawingRegion(
        f"{frame.name}_table", table.region.min_x, table.region.min_y, table.region.max_x, table.region.max_y,
    )
    electrical_base = _largest_electrical_region(frame, table_region, tolerance=tolerance)
    electrical_region = DrawingRegion(
        f"{frame.name}_electrical", electrical_base.min_x, electrical_base.min_y,
        electrical_base.max_x, electrical_base.max_y,
    )
    return [
        LayoutRegion(electrical_region.name, "electrical", electrical_region, 1.0, {
            "source": "largest_area_adjacent_to_primary_schedule",
            "overlap_allowed": True,
        }),
        LayoutRegion(table_region.name, "table", table_region, table.confidence, table.evidence),
    ]


def detect_drawing_regions(layout: Any, *, max_regions: int = 32) -> list[DrawingRegion]:
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
    # Civil/site drawings can contain many sheets arranged over a very large
    # coordinate range. In that case an individual sheet may be smaller than
    # the global 18% threshold even though its title-frame rectangle is clear.
    title_min_width, title_min_height = drawing_width * 0.08, drawing_height * 0.08
    title_min_area = drawing_width * drawing_height * 0.008
    tolerance = max(drawing_width, drawing_height, 1.0) * 1e-6
    candidates: list[DrawingRegion] = []
    for entity in layout:
        rectangle = _rectangle_from_polyline(entity)
        if rectangle is None:
            continue
        min_x, min_y, max_x, max_y = rectangle
        region = DrawingRegion("", min_x, min_y, max_x, max_y)
        is_title_frame = _is_title_frame_layer(entity.dxf.layer or "0")
        meets_general_threshold = region.width >= min_width and region.height >= min_height and region.area >= min_area
        meets_title_threshold = (
            is_title_frame and region.width >= title_min_width and region.height >= title_min_height
            and region.area >= title_min_area
        )
        if meets_general_threshold or meets_title_threshold:
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
