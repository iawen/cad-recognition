"""Per-frame DXF vector-template component detection.

Runtime vector templates are discovered from categorized DXF files below
``backend/data/runtime/reference-icons/<component_type>/``. The directory name
provides the catalog component type, so a filename alone is never used for
classification. ``DRAWING_TEMPLATE_MANIFEST`` remains available as an optional
supplement for templates stored elsewhere.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from domain.models import CadPoint, ComponentCandidate, ComponentEvidence
from recognition.component_catalog import get_component_definition, supported_component_types
from recognition.vector_template_matcher import geometry_from_dxf, geometry_from_layout, match_template
from rendering.regions import DrawingRegion
from tools.logger import logger


ProgressCallback = Callable[[str, int, str, dict[str, Any]], None]
_REFERENCE_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "data" / "runtime" / "reference-icons"


@dataclass(frozen=True)
class ComponentTemplate:
    component_type: str
    path: Path
    name: str
    min_confidence: float = 0.9


def _reference_icon_templates(valid_types: set[str]) -> list[ComponentTemplate]:
    """Load typed DXF files from ``reference-icons/<component_type>/``."""
    if not _REFERENCE_TEMPLATE_ROOT.is_dir():
        logger.info("Template reference directory unavailable path=%s", _REFERENCE_TEMPLATE_ROOT)
        return []
    templates: list[ComponentTemplate] = []
    for path in sorted(_REFERENCE_TEMPLATE_ROOT.rglob("*.dxf")):
        relative_path = path.relative_to(_REFERENCE_TEMPLATE_ROOT)
        component_type = relative_path.parts[0] if len(relative_path.parts) > 1 else ""
        if component_type not in valid_types or not path.is_file():
            continue
        templates.append(ComponentTemplate(component_type, path.resolve(), path.stem))
    logger.info(
        "Template reference directory scanned path=%s configured_templates=%s",
        _REFERENCE_TEMPLATE_ROOT, len(templates),
    )
    return templates


def _manifest_templates(manifest_path: Path, valid_types: set[str]) -> list[ComponentTemplate]:
    """Load valid, explicitly typed supplemental DXF templates from a manifest."""
    if not manifest_path.is_file():
        logger.info("Template manifest unavailable path=%s", manifest_path)
        return []
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8")).get("templates", [])
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Template manifest unreadable path=%s error=%s", manifest_path, exc)
        return []
    templates: list[ComponentTemplate] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        component_type = entry.get("component_type")
        raw_path = entry.get("path")
        if component_type not in valid_types or not isinstance(raw_path, str):
            continue
        path = Path(raw_path)
        if not path.is_absolute():
            path = (manifest_path.parent / path).resolve()
        if path.suffix.casefold() != ".dxf" or not path.is_file():
            continue
        try:
            minimum = min(max(float(entry.get("min_confidence", 0.9)), 0.0), 1.0)
        except (TypeError, ValueError):
            minimum = 0.9
        templates.append(ComponentTemplate(component_type, path, str(entry.get("name") or path.stem), minimum))
    logger.info("Template manifest loaded path=%s configured_templates=%s", manifest_path, len(templates))
    return templates


def load_component_templates() -> list[ComponentTemplate]:
    """Load categorized runtime DXF templates and optional manifest additions."""
    valid_types = set(supported_component_types())
    templates = _reference_icon_templates(valid_types)
    manifest_value = os.getenv("DRAWING_TEMPLATE_MANIFEST")
    if manifest_value:
        templates.extend(_manifest_templates(Path(manifest_value), valid_types))

    # The same template may be reached through a symlink or an explicit
    # manifest entry. Match it only once to avoid duplicate candidates.
    unique_templates: list[ComponentTemplate] = []
    seen_paths: set[Path] = set()
    for template in templates:
        resolved_path = template.path.resolve()
        if resolved_path in seen_paths:
            continue
        seen_paths.add(resolved_path)
        unique_templates.append(template)
    logger.info("Vector template loading completed configured_templates=%s", len(unique_templates))
    return unique_templates


def _intersects_region(entity: Any, region: DrawingRegion) -> bool:
    """Return whether a modelspace entity has extents overlapping one frame."""
    try:
        from ezdxf import bbox

        extent = bbox.extents([entity], fast=True)
        return not (
            float(extent.extmax.x) < region.min_x or float(extent.extmin.x) > region.max_x
            or float(extent.extmax.y) < region.min_y or float(extent.extmin.y) > region.max_y
        )
    except Exception:
        point = getattr(entity.dxf, "insert", None) or getattr(entity.dxf, "center", None)
        return point is not None and region.min_x <= point.x <= region.max_x and region.min_y <= point.y <= region.max_y


def _within_region(entities: Iterable[Any], region: DrawingRegion) -> list[Any]:
    return [entity for entity in entities if _intersects_region(entity, region)]


def detect_template_components(
    layout: Iterable[Any],
    region: DrawingRegion,
    frame_index: int,
    templates: list[ComponentTemplate],
    *,
    progress_callback: ProgressCallback | None = None,
    progress_start: int = 40,
    progress_span: int = 15,
) -> list[ComponentCandidate]:
    """Locate configured templates in one drawing frame.

    Only high-confidence vector matches become candidates. Callers may use an
    empty result as the signal to run visual fallback for this frame.
    """
    if not templates:
        logger.info("Template matching skipped frame=%s reason=no_configured_templates", region.name)
        return []
    geometry = geometry_from_layout(_within_region(layout, region))
    if not geometry.segments:
        logger.info("Template matching skipped frame=%s reason=no_usable_geometry", region.name)
        return []
    logger.info(
        "Template matching frame started frame=%s frame_index=%s segments=%s circles=%s template_count=%s",
        region.name, frame_index, len(geometry.segments), len(geometry.circles), len(templates),
    )
    candidates: list[ComponentCandidate] = []
    for index, template in enumerate(templates):
        if progress_callback:
            progress_callback(
                "template_match", progress_start + round(progress_span * index / len(templates)),
                f"正在匹配主图框 {frame_index + 1} 的模板 {index + 1}/{len(templates)}：{template.name}。",
                {
                    "kind": "template_match", "frame_index": frame_index,
                    "template_index": index, "template_total": len(templates), "template_name": template.name,
                },
            )
        template_geometry = geometry_from_dxf(template.path)
        logger.info(
            "Template matching started frame=%s template_index=%s template_count=%s template=%s type=%s segments=%s",
            region.name, index + 1, len(templates), template.name, template.component_type, len(template_geometry.segments),
        )
        raw_matches = match_template(
            template_geometry.segments, geometry.segments, min_scale=None, max_scale=None,
        )
        accepted_count = 0
        for match in raw_matches:
            if match.confidence < template.min_confidence:
                continue
            accepted_count += 1
            definition = get_component_definition(template.component_type)
            candidates.append(ComponentCandidate(
                id=f"template_{frame_index + 1}_{len(candidates) + 1:04d}",
                type=template.component_type,
                cad_center=CadPoint(x=match.center_x, y=match.center_y),
                rotation_deg=match.rotation_deg,
                source="template",
                confidence=match.confidence,
                review_status="approved",
                frame_index=frame_index,
                evidence=ComponentEvidence(
                    block_name=template.path.name,
                    layer="DXF_TEMPLATE",
                    detection_model="dxf_vector_template",
                    catalog_name=definition.display_name if definition else None,
                    catalog_category=definition.category if definition else None,
                    reference_assets=definition.reference_assets() if definition else {},
                    attributes={
                        "template_name": template.name,
                        "template_scale": str(match.scale),
                        "matched_segments": f"{match.matched_segments}/{match.template_segments}",
                    },
                ),
            ))
        logger.info(
            "Template matching completed frame=%s template=%s raw_matches=%s accepted_matches=%s minimum_confidence=%s",
            region.name, template.name, len(raw_matches), accepted_count, template.min_confidence,
        )
    logger.info("Template matching frame completed frame=%s accepted_components=%s", region.name, len(candidates))
    return candidates
