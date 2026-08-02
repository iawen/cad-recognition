"""Optional rendered-drawing VLM/OBB detection pipeline.

This pipeline runs only when ``DRAWING_OBB_MODEL`` points to a validated model.
It deliberately remains separate from the deterministic Block path so deployments
without model weights retain the P1 behavior.
"""

from __future__ import annotations

import tempfile
import time
from pathlib import Path
from typing import Any

from cad.coordinates import CoordinateTransform
from domain.models import CadPoint, ComponentCandidate, ComponentEvidence
from recognition.component_catalog import get_component_definition, resolve_component_type
from recognition.obb_detector import ObbDetector
from recognition.vlm_detector import VlmDetector
from rendering.dxf_renderer import render_dxf_to_png
from rendering.tiling import create_tiles
from tools.logger import logger


class VisualDetectionError(RuntimeError):
    """Visual inference failed together with safe task-audit details."""

    def __init__(self, message: str, audit: dict[str, Any]):
        super().__init__(message)
        self.audit = audit


def _drawing_transform(dxf_path: Path, width_px: int, height_px: int) -> CoordinateTransform:
    import ezdxf
    from ezdxf import bbox

    document = ezdxf.readfile(dxf_path)
    extent = bbox.extents(document.modelspace())
    return CoordinateTransform(
        CadPoint(x=float(extent.extmin.x), y=float(extent.extmin.y)),
        CadPoint(x=float(extent.extmax.x), y=float(extent.extmax.y)), width_px, height_px,
    )


def _iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection == 0:
        return 0.0
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / max(first_area + second_area - intersection, 1.0)


def _is_duplicate(
    component_type: str,
    bbox: tuple[float, float, float, float],
    prior: list[tuple[ComponentCandidate, tuple[float, float, float, float]]],
) -> bool:
    return any(item.type == component_type and _iou(bbox, item_bbox) >= 0.4 for item, item_bbox in prior)


def detect_visual_components(
    dxf_path: Path,
    *,
    detector: ObbDetector | VlmDetector | None = None,
    include_audit: bool = False,
) -> list[ComponentCandidate] | tuple[list[ComponentCandidate], dict[str, Any]]:
    """Render, tile, infer, map detections, merge overlaps, and retain audit data."""
    primary = detector or VlmDetector()
    if isinstance(primary, VlmDetector) and not primary.enabled:
        primary = ObbDetector()
    fallback = ObbDetector() if isinstance(primary, VlmDetector) else None
    audit: dict[str, Any] = {
        "enabled": primary.enabled,
        "primary_detector": primary.model_identifier,
        "fallback_detector": fallback.model_identifier if fallback and fallback.enabled else None,
        "tile_requests": [],
        "fallbacks": [],
    }
    if not primary.enabled:
        return ([], audit) if include_audit else []
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow，无法运行视觉检测。") from exc
    with tempfile.TemporaryDirectory(prefix="drawing-vision-") as temp_dir:
        root = Path(temp_dir)
        rendered = render_dxf_to_png(dxf_path, root / "drawing.png")
        with Image.open(rendered) as image:
            transform = _drawing_transform(dxf_path, image.width, image.height)
        candidates: list[tuple[ComponentCandidate, tuple[float, float, float, float]]] = []
        tiles = create_tiles(rendered, root / "tiles")
        audit["tile_count"] = len(tiles)
        active_detector = primary
        started = time.perf_counter()
        raw_detection_count = 0
        for tile in tiles:
            try:
                detections = active_detector.detect(tile.path)
            except RuntimeError as exc:
                if active_detector is primary and fallback and fallback.enabled:
                    logger.warning("VLM tile failed; falling back to OBB tile=%s error=%s", tile.path.name, exc)
                    audit["fallbacks"].append({"tile": tile.path.name, "reason": str(exc), "detector": fallback.model_identifier})
                    active_detector = fallback
                    detections = active_detector.detect(tile.path)
                else:
                    request_metadata = getattr(active_detector, "last_request_metadata", None)
                    if request_metadata:
                        audit["tile_requests"].append(dict(request_metadata))
                    audit.update({
                        "active_detector": active_detector.model_identifier,
                        "failed_tile": tile.path.name,
                        "failure": str(exc),
                        "duration_ms": round((time.perf_counter() - started) * 1000),
                    })
                    raise VisualDetectionError(str(exc), audit) from exc
            request_metadata = getattr(active_detector, "last_request_metadata", None)
            if request_metadata:
                audit["tile_requests"].append(dict(request_metadata))
            for detection in detections:
                raw_detection_count += 1
                component_type = resolve_component_type(detection.label)
                if component_type is None:
                    continue
                definition = get_component_definition(component_type)
                global_center = CadPoint(x=tile.x_offset + detection.center_x, y=tile.y_offset + detection.center_y)
                global_bbox = (
                    tile.x_offset + detection.center_x - detection.width / 2,
                    tile.y_offset + detection.center_y - detection.height / 2,
                    tile.x_offset + detection.center_x + detection.width / 2,
                    tile.y_offset + detection.center_y + detection.height / 2,
                )
                candidate = ComponentCandidate(
                    id=f"vision_{len(candidates) + 1:04d}", type=component_type,
                    cad_center=transform.pixel_to_cad(global_center), rotation_deg=detection.angle_deg,
                    source="vision", confidence=detection.confidence, review_status="pending",
                    evidence=ComponentEvidence(
                        block_name="", layer="", detection_model=detector.model_identifier,
                        catalog_name=definition.display_name if definition else None,
                        catalog_category=definition.category if definition else None,
                        reference_assets=definition.reference_assets() if definition else {},
                        detection_bbox_px=[round(value, 2) for value in global_bbox],
                        detection_tile=tile.path.name,
                    ),
                )
                if not _is_duplicate(component_type, global_bbox, candidates):
                    candidates.append((candidate, global_bbox))
        audit.update({
            "active_detector": active_detector.model_identifier,
            "raw_detection_count": raw_detection_count,
            "merged_detection_count": len(candidates),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        })
        result = [candidate for candidate, _ in candidates]
        return (result, audit) if include_audit else result