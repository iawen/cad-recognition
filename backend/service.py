"""Application service orchestrating the P1 vector-first analysis workflow."""

from __future__ import annotations

import tempfile
from pathlib import Path

from cad.dxf_parser import parse_dxf
from domain.models import DrawingAnalysisResult
from fusion.result_assembler import assemble_vector_result
from fusion.text_association import associate_component_texts
from ingest.dwg_converter import convert_dwg_to_dxf
from ingest.file_validation import validate_drawing_file
from recognition.vision_pipeline import VisualDetectionError, detect_visual_components
from recognition.vision_pipeline import detect_visual_texts
from rendering.dxf_renderer import render_dxf_region_to_png, render_dxf_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions
from tools.logger import logger


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


def analyze_drawing(
    path: Path,
    *,
    max_components: int = 1000,
    render_output_path: Path | None = None,
    render_output_dir: Path | None = None,
) -> DrawingAnalysisResult:
    """Validate input, adapt DWG if needed, parse DXF, then assemble evidence."""
    suffix = validate_drawing_file(path)
    temporary_output: tempfile.TemporaryDirectory[str] | None = None
    try:
        dxf_path = path
        if suffix == ".dwg":
            dxf_path, temporary_output = convert_dwg_to_dxf(path)
        parsed = parse_dxf(dxf_path, max_components=max_components)
        regions = _drawing_regions(dxf_path)
        if render_output_dir is not None:
            base_images = render_dxf_base_maps(dxf_path, render_output_dir)
        else:
            base_images = []
        if render_output_path is not None:
            render_dxf_to_png(dxf_path, render_output_path)
        visual_error: str | None = None
        try:
            visual_response = detect_visual_components(dxf_path, include_audit=True)
            if isinstance(visual_response, tuple):
                visual_components, visual_audit = visual_response
            else:
                # Maintains compatibility with tests and third-party adapters
                # which implement the historical list-only function contract.
                visual_components, visual_audit = visual_response, {}
        except VisualDetectionError as exc:
            visual_components = []
            visual_audit = exc.audit
            visual_error = str(exc)
            logger.warning("Visual recognition skipped source=%s error=%s", path, exc)
        except RuntimeError as exc:
            # Vector results remain usable when an optional external model is
            # unavailable or configured with a text-only model.
            visual_components = []
            visual_audit = {}
            visual_error = str(exc)
            logger.warning("Visual recognition skipped source=%s error=%s", path, exc)
        if visual_components:
            parsed.components.extend(visual_components[:max(0, max_components - len(parsed.components))])
        visual_text_error: str | None = None
        try:
            visual_text_response = detect_visual_texts(dxf_path, include_audit=True)
            if isinstance(visual_text_response, tuple):
                visual_texts, visual_text_audit = visual_text_response
            else:
                visual_texts, visual_text_audit = visual_text_response, {}
        except VisualDetectionError as exc:
            visual_texts, visual_text_audit, visual_text_error = [], exc.audit, str(exc)
            logger.warning("VLM text extraction skipped source=%s error=%s", path, exc)
        except RuntimeError as exc:
            visual_texts, visual_text_audit, visual_text_error = [], {}, str(exc)
            logger.warning("VLM text extraction skipped source=%s error=%s", path, exc)
        parsed.texts.extend(visual_texts)
        _associate_text_per_frame(parsed, regions)
        result = assemble_vector_result(path, suffix, temporary_output is not None, parsed)
        if visual_audit:
            result.audit["visual_detection"] = visual_audit
        if visual_error:
            result.audit["limitations"].insert(
                0,
                f"视觉识别未执行：{visual_error} 请确认 DRAWING_VLM_MODEL_NAME 配置的是支持图片输入的模型。",
            )
        if visual_text_audit:
            result.audit["visual_text_extraction"] = visual_text_audit
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
        return result
    finally:
        if temporary_output is not None:
            temporary_output.cleanup()


def render_dxf_base_maps(dxf_path: Path, output_dir: Path, *, dpi: int = 450) -> list[dict[str, object]]:
    """Persist one high-resolution PNG for every detected modelspace drawing frame."""
    import ezdxf
    from ezdxf import bbox
    from PIL import Image

    document = ezdxf.readfile(dxf_path)
    layout = document.modelspace()
    regions = detect_drawing_regions(layout)
    if not regions:
        extent = bbox.extents(layout)
        regions = [DrawingRegion(
            "modelspace", float(extent.extmin.x), float(extent.extmin.y),
            float(extent.extmax.x), float(extent.extmax.y),
        )]

    output_dir.mkdir(parents=True, exist_ok=True)
    base_images: list[dict[str, object]] = []
    for index, region in enumerate(regions):
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
    logger.info("Rendered drawing base maps source=%s count=%s output_dir=%s", dxf_path, len(base_images), output_dir)
    return base_images