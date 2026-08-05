"""Optional rendered-drawing VLM/OBB detection pipeline.

This pipeline runs only when ``DRAWING_OBB_MODEL`` points to a validated model.
It deliberately remains separate from the deterministic Block path so deployments
without model weights retain the P1 behavior.
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Callable

from cad.coordinates import CoordinateTransform
from domain.models import CadPoint, ComponentCandidate, ComponentEvidence, NativeText
from recognition.component_catalog import get_component_definition, resolve_component_type
from recognition.obb_detector import ObbDetector
from recognition.vlm_detector import VlmDetector
from rendering.dxf_renderer import render_dxf_regions_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions
from rendering.tiling import CadTile, create_cad_tiles
from tools.logger import logger


ProgressCallback = Callable[[str, int, str, dict[str, Any]], None]


class VisualDetectionError(RuntimeError):
    """Visual inference failed together with safe task-audit details."""

    def __init__(self, message: str, audit: dict[str, Any]):
        super().__init__(message)
        self.audit = audit


def _drawing_regions(dxf_path: Path) -> list[DrawingRegion]:
    import ezdxf
    from ezdxf import bbox

    document = ezdxf.readfile(dxf_path)
    layout = document.modelspace()
    regions = detect_drawing_regions(layout)
    if regions:
        return regions
    extent = bbox.extents(layout)
    return [DrawingRegion(
        "modelspace", float(extent.extmin.x), float(extent.extmin.y),
        float(extent.extmax.x), float(extent.extmax.y),
    )]


def _region_transform(region: DrawingRegion, width_px: int, height_px: int) -> CoordinateTransform:
    return CoordinateTransform(
        CadPoint(x=region.min_x, y=region.min_y),
        CadPoint(x=region.max_x, y=region.max_y), width_px, height_px,
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
    region_name: str,
    component_type: str,
    bbox: tuple[float, float, float, float],
    prior: list[tuple[str, ComponentCandidate, tuple[float, float, float, float]]],
) -> bool:
    return any(
        prior_region == region_name and item.type == component_type and _iou(bbox, item_bbox) >= 0.4
        for prior_region, item, item_bbox in prior
    )


def _cad_bbox(tile: CadTile, center_x: float, center_y: float, width: float, height: float, image_width: int, image_height: int) -> tuple[float, float, float, float]:
    transform = _region_transform(tile.region, image_width, image_height)
    first = transform.pixel_to_cad(CadPoint(x=center_x - width / 2, y=center_y - height / 2))
    second = transform.pixel_to_cad(CadPoint(x=center_x + width / 2, y=center_y + height / 2))
    return min(first.x, second.x), min(first.y, second.y), max(first.x, second.x), max(first.y, second.y)


def detect_visual_components(
    dxf_path: Path,
    *,
    detector: ObbDetector | VlmDetector | None = None,
    include_audit: bool = False,
    progress_callback: ProgressCallback | None = None,
    frame_contexts: list[tuple[int, DrawingRegion]] | None = None,
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
        candidates: list[tuple[str, ComponentCandidate, tuple[float, float, float, float]]] = []
        regions = frame_contexts or list(enumerate(_drawing_regions(dxf_path)))
        audit["regions"] = []
        active_detector = primary
        started = time.perf_counter()
        raw_detection_count = 0
        vision_dpi = max(150, int(os.getenv("DRAWING_VISION_DPI", "450")))
        for frame_position, (frame_index, region) in enumerate(regions):
            logger.info(
                "VLM component frame started frame=%s frame_index=%s frame_total=%s detector=%s dpi=%s",
                region.name, frame_index + 1, len(regions), active_detector.model_identifier, vision_dpi,
            )
            if progress_callback:
                progress_callback(
                    "vlm_components", 40,
                    f"正在准备主图框 {frame_index + 1}/{len(regions)} 的元器件 VLM 识别。",
                    {"kind": "vlm_component_frame", "frame_index": frame_index, "frame_total": len(regions), "frame_name": region.name},
                )
            tiles = create_cad_tiles(region)
            tile_output_dir = root / region.name / "tiles"
            rendered_paths = render_dxf_regions_to_png(
                dxf_path,
                [(tile_output_dir / tile.name, tile.region) for tile in tiles],
                dpi=vision_dpi,
                max_size_inches=1536 / vision_dpi,
            )
            tile_paths = dict(zip((tile.name for tile in tiles), rendered_paths, strict=True))
            logger.info(
                "VLM component frame CAD-tiled frame=%s tile_count=%s",
                region.name, len(tiles),
            )
            audit["regions"].append({
                "name": region.name,
                "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y],
                "tile_count": len(tiles),
                "tile_mode": "cad_viewport",
            })
            for i, tile in enumerate(tiles):
                tile_path = tile_paths[tile.name]
                tile_started = time.perf_counter()
                logger.info(
                    "VLM component tile started frame=%s tile_index=%s tile_total=%s tile=%s detector=%s",
                    region.name, i + 1, len(tiles), tile_path.name, active_detector.model_identifier,
                )
                if progress_callback:
                    progress_callback(
                        "vlm_components", 55 + round(20 * (frame_position + i / max(len(tiles), 1)) / len(regions)),
                        f"正在识别主图框 {frame_index + 1}/{len(regions)} 的元器件区域 {i + 1}/{len(tiles)}。",
                        {"kind": "vlm_component_tile", "frame_index": frame_index, "frame_total": len(regions), "frame_name": region.name, "tile_index": i, "tile_total": len(tiles), "tile_name": tile_path.name},
                    )
                try:
                    detections = active_detector.detect(tile_path)
                except RuntimeError as exc:
                    if active_detector is primary and fallback and fallback.enabled:
                        logger.warning("VLM tile failed; falling back to OBB tile=%s error=%s", tile_path.name, exc)
                        audit["fallbacks"].append({"tile": tile_path.name, "reason": str(exc), "detector": fallback.model_identifier})
                        active_detector = fallback
                        detections = active_detector.detect(tile_path)
                    else:
                        request_metadata = getattr(active_detector, "last_request_metadata", None)
                        if request_metadata:
                            audit["tile_requests"].append(dict(request_metadata))
                        audit.update({
                            "active_detector": active_detector.model_identifier,
                            "failed_tile": tile_path.name,
                            "failure": str(exc),
                            "duration_ms": round((time.perf_counter() - started) * 1000),
                        })
                        raise VisualDetectionError(str(exc), audit) from exc
                request_metadata = getattr(active_detector, "last_request_metadata", None)
                if request_metadata:
                    audit["tile_requests"].append(dict(request_metadata))
                logger.info(
                    "VLM component tile completed frame=%s tile_index=%s tile_total=%s tile=%s raw_detections=%s elapsed_ms=%s",
                    region.name, i + 1, len(tiles), tile_path.name, len(detections),
                    round((time.perf_counter() - tile_started) * 1000),
                )
                with Image.open(tile_path) as image:
                    image_width, image_height = image.size
                for detection in detections:
                    raw_detection_count += 1
                    component_type = resolve_component_type(detection.label)
                    if component_type is None:
                        continue
                    definition = get_component_definition(component_type)
                    cad_bbox = _cad_bbox(tile, detection.center_x, detection.center_y, detection.width, detection.height, image_width, image_height)
                    tile_transform = _region_transform(tile.region, image_width, image_height)
                    local_bbox = (
                        detection.center_x - detection.width / 2,
                        detection.center_y - detection.height / 2,
                        detection.center_x + detection.width / 2,
                        detection.center_y + detection.height / 2,
                    )
                    candidate = ComponentCandidate(
                        id=f"vision_{len(candidates) + 1:04d}", type=component_type,
                        cad_center=tile_transform.pixel_to_cad(CadPoint(x=detection.center_x, y=detection.center_y)), rotation_deg=detection.angle_deg,
                        source="vision", confidence=detection.confidence, review_status="pending",
                        frame_index=frame_index,
                        evidence=ComponentEvidence(
                            block_name="", layer="", detection_model=active_detector.model_identifier,
                            catalog_name=definition.display_name if definition else None,
                            catalog_category=definition.category if definition else None,
                            reference_assets=definition.reference_assets() if definition else {},
                            detection_bbox_px=[round(value, 2) for value in local_bbox],
                            detection_tile=f"{region.name}/{tile_path.name}",
                        ),
                    )
                    if not _is_duplicate(region.name, component_type, cad_bbox, candidates):
                        candidates.append((region.name, candidate, cad_bbox))
            logger.info("VLM component frame completed frame=%s merged_candidates=%s", region.name, len(candidates))
        audit["tile_count"] = sum(item["tile_count"] for item in audit["regions"])
        audit["vision_dpi"] = vision_dpi
        audit.update({
            "active_detector": active_detector.model_identifier,
            "raw_detection_count": raw_detection_count,
            "merged_detection_count": len(candidates),
            "duration_ms": round((time.perf_counter() - started) * 1000),
        })
        result = [candidate for _, candidate, _ in candidates]
        logger.info(
            "VLM component detection completed source=%s detector=%s raw_detections=%s merged_candidates=%s duration_ms=%s",
            dxf_path, active_detector.model_identifier, raw_detection_count, len(result), audit["duration_ms"],
        )
        return (result, audit) if include_audit else result


def _is_duplicate_text(
    frame_index: int,
    content: str,
    cad_position: CadPoint,
    prior: list[tuple[int, str, CadPoint]],
) -> bool:
    return any(
        prior_frame == frame_index and prior_content == content
        and abs(prior_position.x - cad_position.x) <= 1.0
        and abs(prior_position.y - cad_position.y) <= 1.0
        for prior_frame, prior_content, prior_position in prior
    )


def detect_visual_texts(
    dxf_path: Path,
    *,
    detector: VlmDetector | None = None,
    include_audit: bool = False,
    progress_callback: ProgressCallback | None = None,
    frame_contexts: list[tuple[int, DrawingRegion]] | None = None,
) -> list[NativeText] | tuple[list[NativeText], dict[str, Any]]:
    """Use the VLM to extract text from each DXF frame and map it back to CAD."""
    active_detector = detector or VlmDetector()
    audit: dict[str, Any] = {"enabled": active_detector.enabled, "detector": active_detector.model_identifier, "requests": []}
    if not active_detector.enabled:
        return ([], audit) if include_audit else []
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow，无法运行 VLM 文字提取。") from exc
    with tempfile.TemporaryDirectory(prefix="drawing-vlm-text-") as temp_dir:
        root = Path(temp_dir)
        results: list[NativeText] = []
        prior: list[tuple[int, str, CadPoint]] = []
        vision_dpi = max(150, int(os.getenv("DRAWING_VISION_DPI", "450")))
        regions = frame_contexts or list(enumerate(_drawing_regions(dxf_path)))
        for frame_position, (frame_index, region) in enumerate(regions):
            logger.info(
                "VLM text frame started frame=%s frame_index=%s frame_total=%s detector=%s dpi=%s",
                region.name, frame_index + 1, len(regions), active_detector.model_identifier, vision_dpi,
            )
            if progress_callback:
                progress_callback(
                    "vlm_text", 65,
                    f"正在准备主图框 {frame_index + 1}/{len(regions)} 的关联文字 VLM 提取。",
                    {"kind": "vlm_text_frame", "frame_index": frame_index, "frame_total": len(regions), "frame_name": region.name},
                )
            tiles = create_cad_tiles(region)
            tile_output_dir = root / region.name / "text-tiles"
            rendered_paths = render_dxf_regions_to_png(
                dxf_path,
                [(tile_output_dir / tile.name, tile.region) for tile in tiles],
                dpi=vision_dpi,
                max_size_inches=1536 / vision_dpi,
            )
            tile_paths = dict(zip((tile.name for tile in tiles), rendered_paths, strict=True))
            logger.info("VLM text frame CAD-tiled frame=%s tile_count=%s", region.name, len(tiles))
            for tile_index, tile in enumerate(tiles):
                tile_path = tile_paths[tile.name]
                tile_started = time.perf_counter()
                logger.info(
                    "VLM text tile started frame=%s tile_index=%s tile_total=%s tile=%s detector=%s",
                    region.name, tile_index + 1, len(tiles), tile_path.name, active_detector.model_identifier,
                )
                if progress_callback:
                    progress_callback(
                        "vlm_text", 78 + round(10 * (frame_position + tile_index / max(len(tiles), 1)) / len(regions)),
                        f"正在提取主图框 {frame_index + 1}/{len(regions)} 的关联文字区域 {tile_index + 1}/{len(tiles)}。",
                        {"kind": "vlm_text_tile", "frame_index": frame_index, "frame_total": len(regions), "frame_name": region.name, "tile_index": tile_index, "tile_total": len(tiles), "tile_name": tile_path.name},
                    )
                try:
                    detections = active_detector.extract_texts(tile_path)
                except RuntimeError as exc:
                    audit.update({"failed_tile": tile_path.name, "failure": str(exc)})
                    raise VisualDetectionError(str(exc), audit) from exc
                if active_detector.last_request_metadata:
                    audit["requests"].append(dict(active_detector.last_request_metadata))
                logger.info(
                    "VLM text tile completed frame=%s tile_index=%s tile_total=%s tile=%s raw_texts=%s elapsed_ms=%s",
                    region.name, tile_index + 1, len(tiles), tile_path.name, len(detections),
                    round((time.perf_counter() - tile_started) * 1000),
                )
                with Image.open(tile_path) as image:
                    image_width, image_height = image.size
                tile_transform = _region_transform(tile.region, image_width, image_height)
                for detection in detections:
                    cad_position = tile_transform.pixel_to_cad(CadPoint(x=detection.center_x, y=detection.center_y))
                    if _is_duplicate_text(frame_index, detection.content, cad_position, prior):
                        continue
                    prior.append((frame_index, detection.content, cad_position))
                    results.append(NativeText(
                        id=f"vlm_text_{len(results) + 1:04d}", content=detection.content,
                        entity_type="VLM_TEXT", layer="VLM", source="vlm", confidence=detection.confidence,
                        frame_index=frame_index, component_type=detection.component_type,
                        cad_position=cad_position,
                        detection_bbox_px=[round(value, 2) for value in (
                            detection.center_x - detection.width / 2,
                            detection.center_y - detection.height / 2,
                            detection.center_x + detection.width / 2,
                            detection.center_y + detection.height / 2,
                        )],
                    ))
            logger.info("VLM text frame completed frame=%s retained_texts=%s", region.name, len(results))
        audit.update({"frame_count": len(regions), "text_count": len(results), "vision_dpi": vision_dpi})
        logger.info("VLM text extraction completed source=%s frames=%s texts=%s", dxf_path, len(regions), len(results))
        return (results, audit) if include_audit else results