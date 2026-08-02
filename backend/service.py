"""Application service orchestrating the P1 vector-first analysis workflow."""

from __future__ import annotations

import tempfile
from pathlib import Path

from cad.dxf_parser import parse_dxf
from domain.models import DrawingAnalysisResult
from fusion.result_assembler import assemble_vector_result
from fusion.text_association import associate_native_text
from ingest.dwg_converter import convert_dwg_to_dxf
from ingest.file_validation import validate_drawing_file
from recognition.vision_pipeline import VisualDetectionError, detect_visual_components
from rendering.dxf_renderer import render_dxf_to_png
from tools.logger import logger


def analyze_drawing(
    path: Path,
    *,
    max_components: int = 1000,
    render_output_path: Path | None = None,
) -> DrawingAnalysisResult:
    """Validate input, adapt DWG if needed, parse DXF, then assemble evidence."""
    suffix = validate_drawing_file(path)
    temporary_output: tempfile.TemporaryDirectory[str] | None = None
    try:
        dxf_path = path
        if suffix == ".dwg":
            dxf_path, temporary_output = convert_dwg_to_dxf(path)
        parsed = parse_dxf(dxf_path, max_components=max_components)
        if render_output_path is not None:
            render_dxf_to_png(dxf_path, render_output_path)
        parsed.components = associate_native_text(parsed.components, parsed.texts)
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
        result = assemble_vector_result(path, suffix, temporary_output is not None, parsed)
        if visual_audit:
            result.audit["visual_detection"] = visual_audit
        if visual_error:
            result.audit["limitations"].insert(
                0,
                f"视觉识别未执行：{visual_error} 请确认 DRAWING_VLM_MODEL_NAME 配置的是支持图片输入的模型。",
            )
        if render_output_path is not None:
            result.drawing["render_path"] = render_output_path.name
        return result
    finally:
        if temporary_output is not None:
            temporary_output.cleanup()