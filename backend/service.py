"""Application service orchestrating the P1 vector-first analysis workflow."""

from __future__ import annotations

import tempfile
from math import hypot
from pathlib import Path
from typing import Any, Callable

from cad.dxf_parser import parse_dxf
from domain.models import DrawingAnalysisResult
from fusion.result_assembler import assemble_vector_result
from fusion.text_association import associate_component_texts
from ingest.dwg_converter import convert_dwg_to_dxf
from ingest.file_validation import validate_drawing_file
from recognition.vision_pipeline import VisualDetectionError, detect_visual_components
from recognition.vision_pipeline import detect_visual_texts
from recognition.template_detector import detect_template_components, load_component_templates
from rendering.dxf_renderer import render_dxf_region_to_png, render_dxf_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions
from tools.logger import logger


ProgressCallback = Callable[[str, int, str, dict[str, Any]], None]


def _drawing_regions(dxf_path: Path) -> list[DrawingRegion]:
    """Return the frame partition used by rendering, VLM inference, and text association."""
    import ezdxf
    from ezdxf import bbox

    layout = ezdxf.readfile(dxf_path).modelspace()
    regions = detect_drawing_regions(layout)
    if regions:
        return regions
    extent = bbox.extents(layout)
    return [DrawingRegion(
        "modelspace", float(extent.extmin.x), float(extent.extmin.y),
        float(extent.extmax.x), float(extent.extmax.y),
    )]


def _frame_index(point: object, regions: list[DrawingRegion]) -> int | None:
    if point is None:
        return None
    x, y = point.x, point.y  # type: ignore[attr-defined]
    for index, region in enumerate(regions):
        if region.min_x <= x <= region.max_x and region.min_y <= y <= region.max_y:
            return index
    return None


def _associate_text_per_frame(parsed: object, regions: list[DrawingRegion]) -> None:
    """Associate only component-relevant text within the same drawing frame."""
    components_by_frame: dict[int | None, list] = {}
    texts_by_frame: dict[int | None, list] = {}
    for component in parsed.components:  # type: ignore[attr-defined]
        component.frame_index = _frame_index(component.cad_center, regions)
        components_by_frame.setdefault(component.frame_index, []).append(component)
    for text in parsed.texts:  # type: ignore[attr-defined]
        text.frame_index = _frame_index(text.cad_position, regions)
        texts_by_frame.setdefault(text.frame_index, []).append(text)
    retained_texts: list = []
    for frame_index, components in components_by_frame.items():
        _, associated = associate_component_texts(components, texts_by_frame.get(frame_index, []))
        retained_texts.extend(associated)
    parsed.texts = retained_texts  # type: ignore[attr-defined]


def _is_duplicate_vector_candidate(candidate: object, existing: list, region: DrawingRegion) -> bool:
    """Prefer a known INSERT over an equivalent template match in one frame."""
    tolerance = max(region.width, region.height, 1.0) * 0.002
    return any(
        item.type == candidate.type
        and hypot(item.cad_center.x - candidate.cad_center.x, item.cad_center.y - candidate.cad_center.y) <= tolerance
        for item in existing
    )


def _recognized_component_work(components: list, frame_index: int, frame_total: int, frame_name: str) -> dict[str, Any]:
    """Serialize the cumulative per-frame component result for live clients."""
    return {
        "kind": "frame_components",
        "frame_index": frame_index,
        "frame_total": frame_total,
        "frame_name": frame_name,
        "components": [component.model_dump(mode="json") for component in components],
    }


def analyze_drawing(
    path: Path,
    *,
    max_components: int = 1000,
    render_output_path: Path | None = None,
    render_output_dir: Path | None = None,
    progress_callback: ProgressCallback | None = None,
) -> DrawingAnalysisResult:
    """Validate input, adapt DWG if needed, parse DXF, then assemble evidence."""
    suffix = validate_drawing_file(path)
    logger.info("Drawing analysis started source=%s suffix=%s", path, suffix)
    temporary_output: tempfile.TemporaryDirectory[str] | None = None
    try:
        dxf_path = path
        if suffix == ".dwg":
            logger.info("Drawing analysis converting DWG source=%s", path)
            dxf_path, temporary_output = convert_dwg_to_dxf(path)
            logger.info("Drawing analysis DWG conversion completed source=%s dxf=%s", path, dxf_path)
        parsed = parse_dxf(dxf_path, max_components=max_components)
        logger.info(
            "Drawing analysis native DXF parsed source=%s entities=%s blocks=%s texts=%s unknown_blocks=%s",
            dxf_path, sum(parsed.entity_types.values()), len(parsed.components), len(parsed.texts), sum(parsed.unknown_blocks.values()),
        )
        regions = _drawing_regions(dxf_path)
        logger.info("Drawing analysis frames detected source=%s frame_count=%s", dxf_path, len(regions))
        if progress_callback:
            progress_callback(
                "frame_detection", 35, f"已识别 {len(regions)} 个主图框，准备渲染与视觉识别。",
                {"kind": "drawing_frames", "frame_total": len(regions)},
            )
        if render_output_path is not None:
            render_dxf_to_png(dxf_path, render_output_path)
        # Produce the frame-specific base maps before frame recognition so the
        # streamed result page can show each detected frame while recognition
        # continues. The final result reuses this manifest instead of rendering
        # the same frames again.
        base_images: list[dict[str, object]] = []
        if render_output_dir is not None:
            logger.info("Drawing analysis progressive base-map rendering started source=%s output_dir=%s", dxf_path, render_output_dir)
            base_images = render_dxf_base_maps(
                dxf_path, render_output_dir, regions=regions, progress_callback=progress_callback,
            )
        # Parse the DXF once, then assign every native Block/text record to its
        # owning frame. Each subsequent recognition decision is frame-local.
        for component in parsed.components:
            component.frame_index = _frame_index(component.cad_center, regions)
        for text in parsed.texts:
            text.frame_index = _frame_index(text.cad_position, regions)

        import ezdxf

        layout = ezdxf.readfile(dxf_path).modelspace()
        templates = load_component_templates()
        logger.info("Drawing analysis vector template stage configured source=%s template_count=%s", dxf_path, len(templates))
        visual_components: list = []
        visual_texts: list = []
        visual_audits: list[dict[str, object]] = []
        visual_text_audits: list[dict[str, object]] = []
        visual_error: str | None = None
        visual_text_error: str | None = None
        for frame_index, region in enumerate(regions):
            native_component_count = sum(item.frame_index == frame_index for item in parsed.components)
            native_text_count = sum(item.frame_index == frame_index for item in parsed.texts)
            logger.info(
                "Drawing analysis frame started frame=%s frame_index=%s frame_total=%s native_components=%s native_texts=%s",
                region.name, frame_index + 1, len(regions), native_component_count, native_text_count,
            )
            if progress_callback:
                progress_callback(
                    "frame_vector_parse", 38 + round(14 * frame_index / max(len(regions), 1)),
                    f"正在解析主图框 {frame_index + 1}/{len(regions)} 的实体、Block 和原生文字。",
                    {"kind": "frame_vector_parse", "frame_index": frame_index, "frame_total": len(regions), "frame_name": region.name},
                )
            template_components = detect_template_components(
                layout, region, frame_index, templates, progress_callback=progress_callback,
                progress_start=40 + round(14 * frame_index / max(len(regions), 1)),
                progress_span=max(1, round(12 / max(len(regions), 1))),
            )
            for candidate in template_components:
                if not _is_duplicate_vector_candidate(candidate, parsed.components, region):
                    parsed.components.append(candidate)

            vector_components = [item for item in parsed.components if item.frame_index == frame_index]
            # VLM is the fallback for a frame that has no reliable native Block
            # or configured template result. This avoids unnecessary visual
            # requests when the vector layer has already supplied evidence.
            if vector_components:
                logger.info(
                    "Drawing analysis VLM fallback skipped frame=%s vector_components=%s sources=%s",
                    region.name, len(vector_components), sorted({item.source for item in vector_components}),
                )
                if progress_callback:
                    progress_callback(
                        "frame_components", 53 + round(35 * (frame_index + 1) / max(len(regions), 1)),
                        f"主图框 {frame_index + 1}/{len(regions)} 已识别 {len(vector_components)} 个元器件。",
                        _recognized_component_work(parsed.components, frame_index, len(regions), region.name),
                    )
                continue
            logger.info("Drawing analysis VLM fallback started frame=%s reason=no_reliable_vector_candidate", region.name)
            try:
                visual_response = detect_visual_components(
                    dxf_path, include_audit=True, progress_callback=progress_callback,
                    frame_contexts=[(frame_index, region)],
                )
                if isinstance(visual_response, tuple):
                    frame_components, frame_audit = visual_response
                else:
                    frame_components, frame_audit = visual_response, {}
                visual_components.extend(frame_components)
                visual_audits.append(frame_audit)
                logger.info("Drawing analysis VLM component stage completed frame=%s detections=%s", region.name, len(frame_components))
            except VisualDetectionError as exc:
                visual_audits.append(exc.audit)
                visual_error = str(exc)
                logger.warning("Visual recognition skipped source=%s frame=%s error=%s", path, region.name, exc)
            except RuntimeError as exc:
                visual_error = str(exc)
                logger.warning("Visual recognition skipped source=%s frame=%s error=%s", path, region.name, exc)
            if progress_callback:
                recognized_components = [*parsed.components, *visual_components]
                frame_component_count = sum(item.frame_index == frame_index for item in recognized_components)
                progress_callback(
                    "frame_components", 53 + round(35 * (frame_index + 1) / max(len(regions), 1)),
                    f"主图框 {frame_index + 1}/{len(regions)} 已识别 {frame_component_count} 个元器件。",
                    _recognized_component_work(recognized_components, frame_index, len(regions), region.name),
                )
            try:
                visual_text_response = detect_visual_texts(
                    dxf_path, include_audit=True, progress_callback=progress_callback,
                    frame_contexts=[(frame_index, region)],
                )
                if isinstance(visual_text_response, tuple):
                    frame_texts, frame_audit = visual_text_response
                else:
                    frame_texts, frame_audit = visual_text_response, {}
                visual_texts.extend(frame_texts)
                visual_text_audits.append(frame_audit)
                logger.info("Drawing analysis VLM text stage completed frame=%s texts=%s", region.name, len(frame_texts))
            except VisualDetectionError as exc:
                visual_text_audits.append(exc.audit)
                visual_text_error = str(exc)
                logger.warning("VLM text extraction skipped source=%s frame=%s error=%s", path, region.name, exc)
            except RuntimeError as exc:
                visual_text_error = str(exc)
                logger.warning("VLM text extraction skipped source=%s frame=%s error=%s", path, region.name, exc)
        if visual_components:
            parsed.components.extend(visual_components[:max(0, max_components - len(parsed.components))])
        parsed.texts.extend(visual_texts)
        _associate_text_per_frame(parsed, regions)
        logger.info(
            "Drawing analysis text association completed source=%s components=%s retained_texts=%s",
            path, len(parsed.components), len(parsed.texts),
        )
        result = assemble_vector_result(path, suffix, temporary_output is not None, parsed)
        result.audit["template_detection"] = {
            "configured_template_count": len(templates),
            "matched_component_count": sum(item.source == "template" for item in parsed.components),
            "vlm_fallback_frame_count": len(visual_audits),
        }
        if visual_audits:
            result.audit["visual_detection"] = {"frames": visual_audits}
        if visual_error:
            result.audit["limitations"].insert(
                0,
                f"视觉识别未执行：{visual_error} 请确认 DRAWING_VLM_MODEL_NAME 配置的是支持图片输入的模型。",
            )
        if visual_text_audits:
            result.audit["visual_text_extraction"] = {"frames": visual_text_audits}
        if visual_text_error:
            result.audit["limitations"].insert(0, f"VLM 文字提取未执行：{visual_text_error}")
        result.drawing["frames"] = [
            {"index": index, "name": region.name, "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y]}
            for index, region in enumerate(regions)
        ]
        if render_output_path is not None:
            result.drawing["render_path"] = render_output_path.name
        if base_images:
            result.drawing["base_images"] = base_images
        logger.info(
            "Drawing analysis completed source=%s components=%s texts=%s frames=%s",
            path, len(result.components), len(result.texts), len(regions),
        )
        return result
    finally:
        if temporary_output is not None:
            temporary_output.cleanup()


def render_dxf_base_maps(
    dxf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 450,
    progress_callback: ProgressCallback | None = None,
    regions: list[DrawingRegion] | None = None,
) -> list[dict[str, object]]:
    """Persist one high-resolution PNG for every detected modelspace drawing frame."""
    import ezdxf
    from ezdxf import bbox
    from PIL import Image

    document = ezdxf.readfile(dxf_path)
    layout = document.modelspace()
    detected_regions = regions or detect_drawing_regions(layout)
    if not detected_regions:
        extent = bbox.extents(layout)
        detected_regions = [DrawingRegion(
            "modelspace", float(extent.extmin.x), float(extent.extmin.y),
            float(extent.extmax.x), float(extent.extmax.y),
        )]

    output_dir.mkdir(parents=True, exist_ok=True)
    base_images: list[dict[str, object]] = []
    for index, region in enumerate(detected_regions):
        image_path = output_dir / f"{region.name}.png"
        render_dxf_region_to_png(dxf_path, image_path, region, dpi=dpi, max_size_inches=10.0)
        with Image.open(image_path) as image:
            width, height = image.size
        base_images.append({
            "index": index,
            "name": f"主图框 {index + 1}",
            "filename": image_path.name,
            "image_width": width,
            "image_height": height,
            "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y],
        })
        if progress_callback:
            progress_callback(
                "frame_render", 36 + round(3 * (index + 1) / max(len(detected_regions), 1)),
                f"已生成主图框底图 {index + 1}/{len(detected_regions)}。",
                {
                    "kind": "frame_render", "frame_index": index, "frame_total": len(detected_regions),
                    "frame_name": region.name, "base_images": list(base_images),
                },
            )
    logger.info("Rendered drawing base maps source=%s count=%s output_dir=%s", dxf_path, len(base_images), output_dir)
    return base_images