r"""Render main frames and their vector-detected electrical/table subregions.

Run from ``backend/``:
    .venv\Scripts\python.exe -m tools.split_dxf_layout_regions \
      ..\data\B电气图.dxf ..\data\B电气图_版面分区验证 --overwrite

The output directory contains ``frames/``, ``electrical_regions/``, and
``table_regions/`` PNG files plus a ``layout-regions.json`` manifest for visual,
CAD-coordinate, and rule evidence review. A frame with no confirmed table grid
is retained as one electrical area.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.errors import DrawingAnalysisError
from rendering.dxf_renderer import render_dxf_regions_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions, detect_frame_layout_regions


def _frames(document: object) -> tuple[list[DrawingRegion], bool]:
    from ezdxf import bbox

    layout = document.modelspace()  # type: ignore[attr-defined]
    frames = detect_drawing_regions(layout)
    if frames:
        return frames, False
    extent = bbox.extents(layout)
    if not extent.has_data:
        raise DrawingAnalysisError("DXF 模型空间没有可渲染实体。")
    return [DrawingRegion(
        "modelspace", float(extent.extmin.x), float(extent.extmin.y),
        float(extent.extmax.x), float(extent.extmax.y),
    )], True


def split_dxf_layout_regions(
    dxf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 450,
    max_size_inches: float = 10.0,
    overwrite: bool = False,
    frame_index: int | None = None,
) -> dict[str, object]:
    """Render every main frame plus its electrical/table layout subregions."""
    if dxf_path.suffix.casefold() != ".dxf" or not dxf_path.is_file():
        raise DrawingAnalysisError(f"未找到 DXF 文件：{dxf_path}")
    if output_dir.exists():
        if not overwrite and any(output_dir.iterdir()):
            raise DrawingAnalysisError(f"输出目录非空：{output_dir}；如需覆盖请使用 --overwrite。")
        if overwrite:
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        import ezdxf
        from PIL import Image
    except ImportError as exc:
        raise DrawingAnalysisError("缺少 DXF 版面分区验证所需依赖。") from exc

    document = ezdxf.readfile(dxf_path)
    layout = document.modelspace()
    frames, used_modelspace_fallback = _frames(document)
    original_frame_indexes = list(range(len(frames)))
    if frame_index is not None:
        if not 0 <= frame_index < len(frames):
            raise DrawingAnalysisError(f"主图框索引超出范围：{frame_index}，共 {len(frames)} 个主图框。")
        frames = [frames[frame_index]]
        original_frame_indexes = [frame_index]
    frame_outputs = [(output_dir / "frames" / f"{frame.name}.png", frame) for frame in frames]
    render_dxf_regions_to_png(dxf_path, frame_outputs, dpi=dpi, max_size_inches=max_size_inches)

    frame_manifest: list[dict[str, object]] = []

    def write_manifest(*, complete: bool) -> dict[str, object]:
        manifest = {
            "source_dxf": str(dxf_path.resolve()),
            "used_modelspace_fallback": used_modelspace_fallback,
            "frame_count": len(frame_manifest),
            "subregion_count": sum(len(frame["subregions"]) for frame in frame_manifest),
            "render": {"dpi": dpi, "max_size_inches": max_size_inches},
            "complete": complete,
            "frames": frame_manifest,
        }
        (output_dir / "layout-regions.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
        )
        return manifest

    for selected_index, frame in enumerate(frames):
        subregions = detect_frame_layout_regions(layout, frame)
        serialized_subregions: list[dict[str, object]] = []
        frame_image_path = output_dir / "frames" / f"{frame.name}.png"
        with Image.open(frame_image_path) as image:
            frame_width_px, frame_height_px = image.size
        region_outputs: list[tuple[Path, DrawingRegion]] = []
        for subregion in subregions:
            filename = f"{subregion.name}.png"
            category = "electrical_regions" if subregion.kind == "electrical" else "table_regions"
            output_path = output_dir / category / filename
            region_outputs.append((output_path, subregion.region))
        # Direct CAD viewport rendering preserves line/text detail. Cropping a
        # low-resolution full-frame PNG made the smaller review regions blurry.
        render_dxf_regions_to_png(dxf_path, region_outputs, dpi=dpi, max_size_inches=max_size_inches)
        for subregion, (output_path, _) in zip(subregions, region_outputs):
            with Image.open(output_path) as image:
                subregion_image_size = image.size
                category = "electrical_regions" if subregion.kind == "electrical" else "table_regions"
                filename = output_path.name
                serialized_subregions.append({
                    "name": subregion.name,
                    "kind": subregion.kind,
                    "filename": f"{category}/{filename}",
                    "cad_extent": [subregion.region.min_x, subregion.region.min_y, subregion.region.max_x, subregion.region.max_y],
                    "image_size": list(subregion_image_size),
                    "confidence": subregion.confidence,
                    "evidence": subregion.evidence,
                })
        frame_manifest.append({
            "index": original_frame_indexes[selected_index],
            "name": frame.name,
            "filename": f"frames/{frame.name}.png",
            "cad_extent": [frame.min_x, frame.min_y, frame.max_x, frame.max_y],
            "image_size": [frame_width_px, frame_height_px],
            "subregions": serialized_subregions,
        })
        # Preserve completed frame artifacts and their coordinate contract even
        # when a later, very large frame takes a long time to render.
        write_manifest(complete=False)

    return write_manifest(complete=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dxf", type=Path, help="待拆分的 DXF 文件。")
    parser.add_argument("output_dir", type=Path, help="保存主图框和版面子区域的目录。")
    parser.add_argument("--dpi", type=int, default=450)
    parser.add_argument("--max-size-inches", type=float, default=10.0)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--frame-index", type=int, help="仅验证指定的 0 起始主图框索引。")
    arguments = parser.parse_args()
    try:
        manifest = split_dxf_layout_regions(
            arguments.input_dxf.resolve(), arguments.output_dir.resolve(), dpi=arguments.dpi,
            max_size_inches=arguments.max_size_inches, overwrite=arguments.overwrite,
            frame_index=arguments.frame_index,
        )
    except DrawingAnalysisError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "frame_count": manifest["frame_count"],
        "subregion_count": manifest["subregion_count"],
        "output_dir": str(arguments.output_dir.resolve()),
        "manifest": str(arguments.output_dir.resolve() / "layout-regions.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
