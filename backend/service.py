"""Application service orchestrating the P1 vector-first analysis workflow."""

from __future__ import annotations

import tempfile
from math import hypot
from pathlib import Path
from typing import Any, Callable

from cad.dxf_parser import parse_dxf
from domain.models import DrawingAnalysisResult
from fusion.result_assembler import assemble_vector_result
from ingest.dwg_converter import convert_dwg_to_dxf
from ingest.file_validation import validate_drawing_file
from recognition.vision_pipeline import VisualDetectionError, detect_visual_components
from recognition.template_detector import detect_template_components, load_component_templates, template_matching_enabled
from rendering.dxf_renderer import render_dxf_region_to_png, render_dxf_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions, detect_frame_layout_regions
from tools.extract_table_component_quantities import (
    extract_component_quantities,
    extract_component_quantities_from_native_texts,
)
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


def _native_texts_in_region(texts: list, region: DrawingRegion) -> list[str]:
    """Return native DXF strings in visual reading order inside one table region."""
    positioned = [
        text for text in texts
        if text.cad_position is not None
        and region.min_x <= text.cad_position.x <= region.max_x
        and region.min_y <= text.cad_position.y <= region.max_y
    ]
    positioned.sort(key=lambda text: (-text.cad_position.y, text.cad_position.x))
    return [text.content for text in positioned]


def _native_text_assessment(texts: list, entity_count: int) -> dict[str, object]:
    """Assess whether native DXF text can support UI display or table extraction."""
    normalized = [text.content.strip() for text in texts if text.content and text.content.strip()]
    meaningful = [text for text in normalized if len(text) >= 2]
    unique_meaningful = sorted(set(meaningful))
    usable = bool(meaningful)
    reason = (
        "未找到 TEXT/MTEXT 实体。"
        if not normalized else
        "仅提取到单字符或空白 TEXT/MTEXT，不能作为元器件文字或数量表依据。"
        if not usable else
        "检测到可用的原生 DXF 文字实体。"
    )
    return {
        "usable": usable,
        "entity_count": entity_count,
        "native_text_count": len(normalized),
        "meaningful_text_count": len(meaningful),
        "unique_meaningful_text_count": len(unique_meaningful),
        "reason": reason,
    }


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


def _layout_region_work(frame_index: int, frame_total: int, frame: DrawingRegion, layout_regions: list) -> dict[str, Any]:
    """Serialize one frame's persisted semantic regions for live clients."""
    return {
        "kind": "frame_layout_regions",
        "frame_index": frame_index,
        "frame_total": frame_total,
        "frame_name": frame.name,
        "layout_regions": [
            {
                "id": f"{frame_index}:{item.name}", "frameIndex": frame_index,
                "frameName": frame.name, "kind": item.kind, "name": item.name,
                "cadExtent": [item.region.min_x, item.region.min_y, item.region.max_x, item.region.max_y],
                "confidence": item.confidence, "evidence": item.evidence,
            }
            for item in layout_regions
        ],
    }


def _table_quantity_work(extraction: dict[str, object], frame_index: int, frame_total: int, frame_name: str) -> dict[str, Any]:
    """Serialize a completed table extraction for immediate sidebar display."""
    return {
        "kind": "table_quantities",
        "frame_index": frame_index,
        "frame_total": frame_total,
        "frame_name": frame_name,
        "table": extraction,
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
        native_text_assessment = _native_text_assessment(parsed.texts, sum(parsed.entity_types.values()))
        logger.info(
            "Drawing analysis native DXF parsed source=%s entities=%s blocks=%s texts=%s unknown_blocks=%s",
            dxf_path, sum(parsed.entity_types.values()), len(parsed.components), len(parsed.texts), sum(parsed.unknown_blocks.values()),
        )
        if native_text_assessment["usable"]:
            logger.info(
                "Drawing analysis native text assessment usable=true native_texts=%s meaningful_texts=%s unique_meaningful_texts=%s",
                native_text_assessment["native_text_count"], native_text_assessment["meaningful_text_count"],
                native_text_assessment["unique_meaningful_text_count"],
            )
        else:
            logger.warning(
                "Drawing analysis native text assessment usable=false entities=%s native_texts=%s reason=%s",
                native_text_assessment["entity_count"], native_text_assessment["native_text_count"],
                native_text_assessment["reason"],
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
        template_matching_is_enabled = template_matching_enabled()
        templates = load_component_templates()
        logger.info(
            "Drawing analysis vector template stage configured source=%s enabled=%s template_count=%s",
            dxf_path, template_matching_is_enabled, len(templates),
        )
        visual_components: list = []
        visual_audits: list[dict[str, object]] = []
        table_extractions: list[dict[str, object]] = []
        table_extraction_errors: list[dict[str, object]] = []
        visual_error: str | None = None
        layout_regions_by_frame: dict[int, list] = {}
        layout_image_paths: dict[tuple[int, str], str] = {}
        layout_image_files: dict[tuple[int, str], Path] = {}
        for frame_index, region in enumerate(regions):
            layout_regions = detect_frame_layout_regions(layout, region)
            layout_regions_by_frame[frame_index] = layout_regions
            electrical_regions = [item.region for item in layout_regions if item.kind == "electrical"]
            table_regions = [item for item in layout_regions if item.kind == "table"]
            logger.info(
                "Drawing analysis layout split completed frame=%s electrical_regions=%s table_regions=%s",
                region.name, len(electrical_regions), len(table_regions),
            )
            if render_output_dir is not None:
                for layout_region in layout_regions:
                    category = "electrical_regions" if layout_region.kind == "electrical" else "table_regions"
                    image_path = render_output_dir / "layout-regions" / category / f"{layout_region.name}.png"
                    logger.info(
                        "Drawing analysis layout region rendering started frame=%s region=%s kind=%s output=%s",
                        region.name, layout_region.name, layout_region.kind, image_path,
                    )
                    render_dxf_region_to_png(dxf_path, image_path, layout_region.region, dpi=450, max_size_inches=10.0)
                    relative_path = image_path.relative_to(render_output_dir).as_posix()
                    layout_image_paths[(frame_index, layout_region.name)] = relative_path
                    layout_image_files[(frame_index, layout_region.name)] = image_path
                    logger.info(
                        "Drawing analysis layout region rendering completed frame=%s region=%s kind=%s output=%s",
                        region.name, layout_region.name, layout_region.kind, relative_path,
                    )
            if progress_callback:
                progress_callback(
                    "frame_layout_regions", 39 + round(14 * frame_index / max(len(regions), 1)),
                    f"主图框 {frame_index + 1}/{len(regions)} 已定位 {len(electrical_regions)} 个电气区域和 {len(table_regions)} 个表格区域。",
                    _layout_region_work(frame_index, len(regions), region, layout_regions),
                )
            native_component_count = sum(item.frame_index == frame_index for item in parsed.components)
            native_text_count = sum(item.frame_index == frame_index for item in parsed.texts)
            logger.info(
                "Drawing analysis frame started frame=%s frame_index=%s frame_total=%s native_components=%s native_texts=%s",
                region.name, frame_index + 1, len(regions), native_component_count, native_text_count,
            )
            if progress_callback:
                progress_callback(
                    "frame_vector_parse", 38 + round(14 * frame_index / max(len(regions), 1)),
                    f"正在解析主图框 {frame_index + 1}/{len(regions)} 的实体、Block、文字和版面区域。",
                    {"kind": "frame_vector_parse", "frame_index": frame_index, "frame_total": len(regions), "frame_name": region.name,
                     "table_region_count": len(table_regions), "electrical_region_count": len(electrical_regions)},
                )
            template_components = []
            for electrical_position, electrical_region in enumerate(electrical_regions):
                matches = detect_template_components(
                    layout, electrical_region, frame_index, templates, progress_callback=progress_callback,
                    progress_start=40 + round(14 * frame_index / max(len(regions), 1)),
                    progress_span=max(1, round(12 / max(len(regions), 1))),
                )
                for candidate in matches:
                    candidate.id = f"template_{frame_index + 1}_{len(template_components) + 1:04d}"
                    if not _is_duplicate_vector_candidate(candidate, parsed.components, electrical_region):
                        parsed.components.append(candidate)
                        template_components.append(candidate)

            vector_components = [
                item for item in parsed.components
                if item.frame_index == frame_index
                and any(electrical.min_x <= item.cad_center.x <= electrical.max_x and electrical.min_y <= item.cad_center.y <= electrical.max_y for electrical in electrical_regions)
            ]
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
            else:
                logger.info("Drawing analysis VLM fallback started frame=%s reason=no_reliable_vector_candidate", region.name)
                try:
                    visual_response = detect_visual_components(
                        dxf_path, include_audit=True, progress_callback=progress_callback,
                        frame_contexts=[(frame_index, electrical_region) for electrical_region in electrical_regions],
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

            # Quantity extraction is deliberately table-only. The prior VLM
            # text detector ran over schematic tiles and produced labels rather
            # than a reviewable component schedule.
            for table_region in table_regions:
                native_table_texts = _native_texts_in_region(parsed.texts, table_region.region)
                logger.info(
                    "Drawing analysis table quantity extraction started frame=%s table=%s native_texts=%s",
                    region.name, table_region.name, len(native_table_texts),
                )
                if progress_callback:
                    progress_callback(
                        "table_quantity_extraction", 90 + round(8 * frame_index / max(len(regions), 1)),
                        f"正在提取主图框 {frame_index + 1}/{len(regions)} 的元器件数量表。",
                        {"kind": "table_quantity_extraction", "frame_index": frame_index,
                         "frame_total": len(regions), "frame_name": region.name, "table_name": table_region.name},
                    )
                try:
                    if native_table_texts:
                        extraction = extract_component_quantities_from_native_texts(
                            native_table_texts, table_name=table_region.name,
                        )
                    else:
                        table_image_path = layout_image_files.get((frame_index, table_region.name))
                        if table_image_path is None:
                            with tempfile.TemporaryDirectory(prefix="drawing-table-region-") as temp_dir:
                                table_image_path = Path(temp_dir) / f"{table_region.name}.png"
                                render_dxf_region_to_png(
                                    dxf_path, table_image_path, table_region.region, dpi=450, max_size_inches=10.0,
                                )
                                extraction = extract_component_quantities(table_image_path)
                        else:
                            extraction = extract_component_quantities(table_image_path)
                        extraction["source"] = "table_region_vlm_image"
                        extraction["table_image_path"] = layout_image_paths.get((frame_index, table_region.name))
                        logger.info(
                            "Drawing analysis table quantity VLM fallback completed frame=%s table=%s image=%s components=%s",
                            region.name, table_region.name, table_image_path.name, extraction.get("component_count", 0),
                        )
                    extraction.pop("raw_response", None)
                    extraction["frame_index"] = frame_index
                    extraction["frame_name"] = region.name
                    extraction["table_name"] = table_region.name
                    extraction["cad_extent"] = [
                        table_region.region.min_x, table_region.region.min_y,
                        table_region.region.max_x, table_region.region.max_y,
                    ]
                    table_extractions.append(extraction)
                    logger.info(
                        "Drawing analysis table quantity extraction completed frame=%s table=%s source=%s native_texts=%s components=%s",
                        region.name, table_region.name, extraction.get("source", "unknown"),
                        extraction.get("native_text_count", len(native_table_texts)), extraction["component_count"],
                    )
                    if progress_callback:
                        progress_callback(
                            "table_quantities", 91 + round(8 * frame_index / max(len(regions), 1)),
                            f"主图框 {frame_index + 1}/{len(regions)} 的数量表已提取 {extraction['component_count']} 条元器件记录。",
                            _table_quantity_work(extraction, frame_index, len(regions), region.name),
                        )
                except RuntimeError as exc:
                    table_extraction_errors.append({"frame_index": frame_index, "table_name": table_region.name, "error": str(exc)})
                    logger.warning("Table quantity extraction skipped source=%s frame=%s table=%s error=%s", path, region.name, table_region.name, exc)
        if visual_components:
            parsed.components.extend(visual_components[:max(0, max_components - len(parsed.components))])
        logger.info(
            "Drawing analysis native text parsing completed source=%s components=%s native_texts=%s",
            path, len(parsed.components), len(parsed.texts),
        )
        result = assemble_vector_result(path, suffix, temporary_output is not None, parsed)
        result.audit["native_text_extraction"] = native_text_assessment
        if not native_text_assessment["usable"]:
            result.audit["limitations"].insert(
                0, f"原生 DXF 文字不可用：{native_text_assessment['reason']}"
            )
        result.audit["template_detection"] = {
            "enabled": template_matching_is_enabled,
            "configured_template_count": len(templates),
            "matched_component_count": sum(item.source == "template" for item in parsed.components),
            "vlm_fallback_frame_count": len(visual_audits),
        }
        if visual_audits:
            result.audit["visual_detection"] = {"frames": visual_audits}
        if visual_error:
            result.audit["limitations"].insert(
                0,
                f"部分电气区域元器件 VLM 识别未完成：{visual_error}。这不影响已完成的表格区域 VLM 提取；请检查模型服务响应与超时设置。",
            )
        if table_extraction_errors:
            result.audit["table_quantity_extraction"] = {"errors": table_extraction_errors}
            result.audit["limitations"].insert(0, "VLM 表格数量提取未完成：请确认图像模型配置及表格可读性。")
        result.drawing["frames"] = [
            {"index": index, "name": region.name, "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y],
             "layout_regions": [
                 {"name": item.name, "kind": item.kind,
                  "cad_extent": [item.region.min_x, item.region.min_y, item.region.max_x, item.region.max_y],
                  "confidence": item.confidence, "evidence": item.evidence,
                  "image_path": layout_image_paths.get((index, item.name))}
                 for item in layout_regions_by_frame.get(index, [])
             ]}
            for index, region in enumerate(regions)
        ]
        if render_output_path is not None:
            result.drawing["render_path"] = render_output_path.name
        if base_images:
            result.drawing["base_images"] = base_images
        result.drawing["tables"] = table_extractions
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