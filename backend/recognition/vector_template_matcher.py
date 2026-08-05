"""Tolerance-aware vector template matching for exploded electrical symbols.

This POC deliberately compares DXF geometry, not raster images. It supports
straight edges plus CIRCLE/ARC primitives normalized into short chord edges.
HATCH entities are ignored: the same contours already occur as LWPOLYLINE
boundaries and would otherwise create duplicate evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import atan2, ceil, cos, hypot, pi, sin
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class Segment:
    """One straight DXF edge represented by two CAD points."""

    start_x: float
    start_y: float
    end_x: float
    end_y: float

    @property
    def length(self) -> float:
        return hypot(self.end_x - self.start_x, self.end_y - self.start_y)

    @property
    def angle(self) -> float:
        return atan2(self.end_y - self.start_y, self.end_x - self.start_x)


@dataclass(frozen=True)
class Circle:
    """One DXF circle represented by a CAD centre and radius."""

    center_x: float
    center_y: float
    radius: float


@dataclass(frozen=True)
class VectorGeometry:
    """Flattened DXF geometry that can participate in template matching."""

    segments: list[Segment]
    circles: list[Circle]


@dataclass(frozen=True)
class VectorTemplateMatch:
    """An auditable candidate match between a DXF template and target geometry."""

    center_x: float
    center_y: float
    scale: float
    rotation_deg: float
    matched_segments: int
    template_segments: int
    mean_endpoint_error: float

    @property
    def confidence(self) -> float:
        """A conservative structural score, not a calibrated ML probability."""
        coverage = self.matched_segments / max(self.template_segments, 1)
        return round(coverage * max(0.0, 1.0 - self.mean_endpoint_error / 0.2), 4)


def _points(entity: Any) -> list[tuple[float, float]]:
    return [(float(point[0]), float(point[1])) for point in entity.get_points("xy")]


def _arc_chords(
    center_x: float,
    center_y: float,
    radius: float,
    start_angle_deg: float,
    end_angle_deg: float,
    *,
    full_circle: bool = False,
) -> list[Segment]:
    """Approximate an ARC/CIRCLE with scale-invariant chord topology."""
    span = 2 * pi if full_circle else (end_angle_deg - start_angle_deg) % 360 * pi / 180
    if radius <= 1e-9 or span <= 1e-9:
        return []
    start = start_angle_deg * pi / 180
    # Fixed angular resolution keeps template/target topology identical across scale.
    steps = max(4, int(ceil(span / (pi / 8))))
    points = [
        (center_x + radius * cos(start + span * index / steps), center_y + radius * sin(start + span * index / steps))
        for index in range(steps + 1)
    ]
    return [Segment(*start_point, *end_point) for start_point, end_point in zip(points, points[1:])]


def _flatten_entities(entities: Iterable[Any]) -> Iterable[Any]:
    """Yield modelspace entities and virtual entities expanded from INSERT blocks."""
    for entity in entities:
        if entity.dxftype() != "INSERT":
            yield entity
            continue
        try:
            virtual_entities = entity.virtual_entities()
        except (AttributeError, TypeError):
            continue
        yield from _flatten_entities(virtual_entities)


def geometry_from_layout(layout: Iterable[Any]) -> VectorGeometry:
    """Extract straight edges and circles, recursively expanding INSERT blocks.

    HATCH is deliberately ignored because it commonly duplicates polyline
    boundaries. Curves are converted to chord edges, preserving their position,
    radius and angular topology under the matcher's uniform transform.
    """
    segments: list[Segment] = []
    circles: list[Circle] = []
    for entity in _flatten_entities(layout):
        entity_type = entity.dxftype()
        if entity_type == "LINE":
            start, end = entity.dxf.start, entity.dxf.end
            candidate = Segment(float(start.x), float(start.y), float(end.x), float(end.y))
            if candidate.length > 1e-9:
                segments.append(candidate)
            continue
        if entity_type == "CIRCLE":
            center = entity.dxf.center
            radius = float(entity.dxf.radius)
            if radius > 1e-9:
                circles.append(Circle(float(center.x), float(center.y), radius))
                segments.extend(_arc_chords(float(center.x), float(center.y), radius, 0, 360, full_circle=True))
            continue
        if entity_type == "ARC":
            center = entity.dxf.center
            segments.extend(_arc_chords(
                float(center.x), float(center.y), float(entity.dxf.radius),
                float(entity.dxf.start_angle), float(entity.dxf.end_angle),
            ))
            continue
        if entity_type != "LWPOLYLINE":
            continue
        points = _points(entity)
        if len(points) < 2:
            continue
        pairs = list(zip(points, points[1:]))
        if entity.closed:
            pairs.append((points[-1], points[0]))
        for start, end in pairs:
            candidate = Segment(start[0], start[1], end[0], end[1])
            if candidate.length > 1e-9:
                segments.append(candidate)
    return VectorGeometry(segments=segments, circles=circles)


def segments_from_layout(layout: Iterable[Any]) -> list[Segment]:
    """Compatibility helper returning the straight subset of flattened geometry."""
    return geometry_from_layout(layout).segments


def geometry_from_dxf(path: Path) -> VectorGeometry:
    """Read flattened matching geometry from a DXF modelspace."""
    import ezdxf

    return geometry_from_layout(ezdxf.readfile(path).modelspace())


def segments_from_dxf(path: Path) -> list[Segment]:
    """Read usable straight geometry from a DXF modelspace."""
    return geometry_from_dxf(path).segments


def infer_scale_candidates(template: list[Segment], target: list[Segment]) -> list[float]:
    """Return scale candidates implied by target edges and the template anchor."""
    if not template:
        return []
    anchor_length = max(item.length for item in template)
    if anchor_length <= 1e-9:
        return []
    return sorted(item.length / anchor_length for item in target if item.length > 1e-9)


def automatic_scale_upper_bound(template: list[Segment], target: list[Segment]) -> float | None:
    """Infer a safe upper scale bound while excluding oversized sheet borders.

    Electrical symbols are normally composed of short-to-medium edges. A small
    number of title-frame or page-border edges can be hundreds of times longer
    and would otherwise make the endpoint tolerance and grid search explode.
    The bound is data-derived: 20 times the target median edge length.
    """
    if not template or not target:
        return None
    anchor_length = max(item.length for item in template)
    lengths = sorted(item.length for item in target if item.length > 1e-9)
    if anchor_length <= 1e-9 or not lengths:
        return None
    median_length = lengths[len(lengths) // 2]
    return 20 * median_length / anchor_length


def automatic_scale_lower_bound(template: list[Segment], endpoint_tolerance: float) -> float | None:
    """Return the smallest scale whose anchor remains spatially distinguishable."""
    if not template:
        return None
    anchor_length = max(item.length for item in template)
    if anchor_length <= 1e-9:
        return None
    # Below this point every template edge falls within the endpoint tolerance
    # and can collapse into an unrelated zero-length drawing artifact.
    return 4 * endpoint_tolerance / anchor_length


def _transform_point(x: float, y: float, *, scale: float, cosine: float, sine: float, offset_x: float, offset_y: float) -> tuple[float, float]:
    return (
        offset_x + scale * (x * cosine - y * sine),
        offset_y + scale * (x * sine + y * cosine),
    )


def _grid_key(x: float, y: float, cell_size: float) -> tuple[int, int]:
    return round(x / cell_size), round(y / cell_size)


def _endpoint_index(segments: list[Segment], *, cell_size: float) -> dict[tuple[int, int], list[int]]:
    index: dict[tuple[int, int], list[int]] = {}
    for position, segment in enumerate(segments):
        for x, y in ((segment.start_x, segment.start_y), (segment.end_x, segment.end_y)):
            index.setdefault(_grid_key(x, y, cell_size), []).append(position)
    return index


def _nearby_segments(
    index: dict[tuple[int, int], list[int]],
    x: float,
    y: float,
    *,
    cell_size: float,
    tolerance: float,
) -> set[int]:
    cell_x, cell_y = _grid_key(x, y, cell_size)
    reach = max(1, int(tolerance / cell_size) + 1)
    return {
        item
        for offset_x in range(-reach, reach + 1)
        for offset_y in range(-reach, reach + 1)
        for item in index.get((cell_x + offset_x, cell_y + offset_y), [])
    }


def _segment_error(expected: Segment, actual: Segment) -> float:
    direct = hypot(expected.start_x - actual.start_x, expected.start_y - actual.start_y) + hypot(expected.end_x - actual.end_x, expected.end_y - actual.end_y)
    reversed_error = hypot(expected.start_x - actual.end_x, expected.start_y - actual.end_y) + hypot(expected.end_x - actual.start_x, expected.end_y - actual.start_y)
    return min(direct, reversed_error) / 2


def _matched_geometry(
    template: list[Segment],
    target: list[Segment],
    endpoint_index: dict[tuple[int, int], list[int]],
    *,
    scale: float,
    cosine: float,
    sine: float,
    offset_x: float,
    offset_y: float,
    cell_size: float,
    tolerance: float,
) -> tuple[int, float]:
    errors: list[float] = []
    for segment in template:
        start_x, start_y = _transform_point(segment.start_x, segment.start_y, scale=scale, cosine=cosine, sine=sine, offset_x=offset_x, offset_y=offset_y)
        end_x, end_y = _transform_point(segment.end_x, segment.end_y, scale=scale, cosine=cosine, sine=sine, offset_x=offset_x, offset_y=offset_y)
        expected = Segment(start_x, start_y, end_x, end_y)
        candidate_indexes = _nearby_segments(endpoint_index, start_x, start_y, cell_size=cell_size, tolerance=tolerance)
        candidate_indexes.update(_nearby_segments(endpoint_index, end_x, end_y, cell_size=cell_size, tolerance=tolerance))
        errors_for_segment = [_segment_error(expected, target[index]) for index in candidate_indexes]
        if errors_for_segment and min(errors_for_segment) <= tolerance:
            errors.append(min(errors_for_segment))
    return len(errors), sum(errors) / len(errors) if errors else float("inf")


def _has_matching_segment(
    template_segment: Segment,
    target: list[Segment],
    endpoint_index: dict[tuple[int, int], list[int]],
    *,
    scale: float,
    cosine: float,
    sine: float,
    offset_x: float,
    offset_y: float,
    cell_size: float,
    tolerance: float,
) -> bool:
    start_x, start_y = _transform_point(template_segment.start_x, template_segment.start_y, scale=scale, cosine=cosine, sine=sine, offset_x=offset_x, offset_y=offset_y)
    end_x, end_y = _transform_point(template_segment.end_x, template_segment.end_y, scale=scale, cosine=cosine, sine=sine, offset_x=offset_x, offset_y=offset_y)
    expected = Segment(start_x, start_y, end_x, end_y)
    candidates = _nearby_segments(endpoint_index, start_x, start_y, cell_size=cell_size, tolerance=tolerance)
    candidates.update(_nearby_segments(endpoint_index, end_x, end_y, cell_size=cell_size, tolerance=tolerance))
    return any(_segment_error(expected, target[index]) <= tolerance for index in candidates)


def match_template(
    template: list[Segment],
    target: list[Segment],
    *,
    min_scale: float | None = 0.02,
    max_scale: float | None = 2.0,
    endpoint_tolerance: float = 0.02,
    min_matched_segments: int | None = None,
) -> list[VectorTemplateMatch]:
    """Find rotated and uniformly scaled template copies in flattened DXF geometry.

    A longest template edge is aligned with each plausible target edge. Every
    remaining template edge must then be found in a local endpoint index. This
    makes the result invariant to translation, rotation, and uniform scale while
    rejecting a one-line-only coincidence. Passing ``None`` for both scale
    bounds evaluates every scale implied by target anchor edges.
    """
    if len(template) < 2 or not target:
        return []
    anchor = max(template, key=lambda item: item.length)
    if anchor.length <= 1e-9:
        return []
    minimum = min_matched_segments or max(3, len(template) - 1)
    automatic_min_scale = automatic_scale_lower_bound(template, endpoint_tolerance) if min_scale is None else min_scale
    automatic_max_scale = automatic_scale_upper_bound(template, target) if max_scale is None else max_scale
    # A cell size tied to actual drawing geometry prevents a scale-derived
    # tolerance from iterating through millions of empty 0.02-unit cells.
    target_lengths = sorted(item.length for item in target if item.length > 1e-9)
    cell_size = max(endpoint_tolerance, target_lengths[len(target_lengths) // 2] if target_lengths else endpoint_tolerance)
    endpoint_index = _endpoint_index(target, cell_size=cell_size)
    template_center_x = sum((item.start_x + item.end_x) / 2 for item in template) / len(template)
    template_center_y = sum((item.start_y + item.end_y) / 2 for item in template) / len(template)
    matches: list[VectorTemplateMatch] = []
    verification_segment = next((item for item in sorted(template, key=lambda item: item.length, reverse=True) if item != anchor), None)

    for candidate in target:
        scale = candidate.length / anchor.length
        if (automatic_min_scale is not None and scale < automatic_min_scale) or (automatic_max_scale is not None and scale > automatic_max_scale):
            continue
        for reversed_target in (False, True):
            target_start_x, target_start_y = (candidate.end_x, candidate.end_y) if reversed_target else (candidate.start_x, candidate.start_y)
            target_angle = candidate.angle + (3.141592653589793 if reversed_target else 0.0)
            rotation = target_angle - anchor.angle
            cosine, sine = cos(rotation), sin(rotation)
            transformed_anchor_x, transformed_anchor_y = _transform_point(anchor.start_x, anchor.start_y, scale=scale, cosine=cosine, sine=sine, offset_x=0.0, offset_y=0.0)
            offset_x, offset_y = target_start_x - transformed_anchor_x, target_start_y - transformed_anchor_y
            tolerance = max(endpoint_tolerance, scale * 0.03)
            if verification_segment is not None and not _has_matching_segment(
                verification_segment, target, endpoint_index,
                scale=scale, cosine=cosine, sine=sine, offset_x=offset_x, offset_y=offset_y,
                cell_size=cell_size, tolerance=tolerance,
            ):
                continue
            matched_segments, mean_error = _matched_geometry(
                template, target, endpoint_index, scale=scale, cosine=cosine, sine=sine,
                offset_x=offset_x, offset_y=offset_y, cell_size=cell_size, tolerance=tolerance,
            )
            if matched_segments < minimum:
                continue
            center_x, center_y = _transform_point(template_center_x, template_center_y, scale=scale, cosine=cosine, sine=sine, offset_x=offset_x, offset_y=offset_y)
            matches.append(VectorTemplateMatch(
                center_x=round(center_x, 4), center_y=round(center_y, 4), scale=round(scale, 6),
                rotation_deg=round(rotation * 180 / 3.141592653589793, 3),
                matched_segments=matched_segments, template_segments=len(template),
                mean_endpoint_error=round(mean_error, 6),
            ))

    matches.sort(key=lambda item: (-item.confidence, item.mean_endpoint_error))
    deduplicated: list[VectorTemplateMatch] = []
    for candidate in matches:
        tolerance = max(endpoint_tolerance * 3, candidate.scale * 0.5)
        if any(hypot(candidate.center_x - prior.center_x, candidate.center_y - prior.center_y) <= tolerance for prior in deduplicated):
            continue
        deduplicated.append(candidate)
    return deduplicated
