"""Deterministic DXF-to-PNG rendering for P0 validation and P2 OBB input."""

from __future__ import annotations

import os
from pathlib import Path
from collections.abc import Sequence

from domain.errors import DrawingAnalysisError
from rendering.regions import DrawingRegion
from tools.logger import logger


DEFAULT_TEXT_FONT = "simhei.ttf"


def _apply_text_font_override(document: object, font_file: str) -> None:
    """Use one installed Unicode font for DXF text styles during raster rendering."""
    try:
        from ezdxf.fonts import fonts as dxf_fonts
        from matplotlib.font_manager import FontProperties, findfont

        configured_path = Path(font_file)
        if configured_path.is_file():
            resolved_path = configured_path
        else:
            windows_path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / configured_path.name
            if windows_path.is_file():
                resolved_path = windows_path
            else:
                resolved_path = Path(findfont(FontProperties(family=configured_path.stem), fallback_to_default=False))
        if not resolved_path.is_file():
            logger.warning("Configured render text font is unavailable font=%s", font_file)
            return
        dxf_fonts.font_manager.build([str(resolved_path.parent)], support_dirs=False)
        resolved_name = resolved_path.name
        for text_style in document.styles:  # type: ignore[attr-defined]
            text_style.dxf.font = resolved_name
        logger.info("Applied render text font override font=%s", resolved_name)
    except Exception as exc:
        # Rendering remains available with the source style when the local font
        # cache is incomplete or the document exposes an unexpected style table.
        logger.warning("Could not apply render text font override font=%s error=%s", font_file, exc)


def render_dxf_to_png(dxf_path: Path, output_path: Path, *, dpi: int = 300) -> Path:
    """Render modelspace to PNG, defaulting DXF text styles to a Chinese font."""
    try:
        import ezdxf
        from ezdxf.addons.drawing import matplotlib
    except ImportError as exc:
        raise DrawingAnalysisError("缺少 DXF PNG 渲染组件，无法执行渲染校验。") from exc
    try:
        document = ezdxf.readfile(dxf_path)
        font_file = os.getenv("DRAWING_RENDER_TEXT_FONT", DEFAULT_TEXT_FONT).strip()
        if font_file:
            _apply_text_font_override(document, font_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        matplotlib.qsave(document.modelspace(), str(output_path), dpi=dpi)
        return output_path
    except Exception as exc:
        raise DrawingAnalysisError(f"DXF PNG 渲染失败：{exc}") from exc


def render_dxf_region_to_png(
    dxf_path: Path,
    output_path: Path,
    region: DrawingRegion,
    *,
    dpi: int = 450,
    max_size_inches: float = 8.0,
) -> Path:
    """Render an exact CAD region at high DPI without the full-drawing margin."""
    return render_dxf_regions_to_png(
        dxf_path, [(output_path, region)], dpi=dpi, max_size_inches=max_size_inches,
    )[0]


def render_dxf_regions_to_png(
    dxf_path: Path,
    outputs: Sequence[tuple[Path, DrawingRegion]],
    *,
    dpi: int = 450,
    max_size_inches: float = 8.0,
) -> list[Path]:
    """Render multiple CAD viewports after loading the DXF document once."""
    try:
        import ezdxf
        import matplotlib
        from ezdxf.addons.drawing import Frontend, RenderContext
        from ezdxf.addons.drawing import matplotlib as drawing_matplotlib
    except ImportError as exc:
        raise DrawingAnalysisError("缺少 DXF PNG 渲染组件，无法执行区域渲染。") from exc
    if not outputs:
        return []
    if max_size_inches <= 0:
        raise DrawingAnalysisError("渲染尺寸必须为正数。")
    for _, region in outputs:
        if region.width <= 0 or region.height <= 0:
            raise DrawingAnalysisError("图纸区域范围无效，无法渲染。")
    old_backend = matplotlib.get_backend()
    try:
        document = ezdxf.readfile(dxf_path)
        font_file = os.getenv("DRAWING_RENDER_TEXT_FONT", DEFAULT_TEXT_FONT).strip()
        if font_file:
            _apply_text_font_override(document, font_file)
        matplotlib.use("agg")
        layout = document.modelspace()
        rendered_paths: list[Path] = []
        for output_path, region in outputs:
            figure = drawing_matplotlib.plt.figure(dpi=dpi)
            try:
                axes = figure.add_axes((0, 0, 1, 1))
                backend = drawing_matplotlib.MatplotlibBackend(axes)
                Frontend(RenderContext(document), backend).draw_layout(layout, finalize=True)
                axes.set_xlim(region.min_x, region.max_x)
                axes.set_ylim(region.min_y, region.max_y)
                axes.set_aspect("equal", adjustable="box")
                ratio = region.width / region.height
                if ratio >= 1:
                    figure.set_size_inches(max_size_inches, max_size_inches / ratio, forward=True)
                else:
                    figure.set_size_inches(max_size_inches * ratio, max_size_inches, forward=True)
                output_path.parent.mkdir(parents=True, exist_ok=True)
                figure.savefig(output_path, dpi=dpi, facecolor=axes.get_facecolor(), transparent=True)
                rendered_paths.append(output_path)
            finally:
                drawing_matplotlib.plt.close(figure)
        return rendered_paths
    except DrawingAnalysisError:
        raise
    except Exception as exc:
        raise DrawingAnalysisError(f"DXF 区域 PNG 渲染失败：{exc}") from exc
    finally:
        matplotlib.use(old_backend)