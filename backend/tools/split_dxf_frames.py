"""Split a DXF drawing into independently rendered main-frame PNG images.

Run from ``backend/``:
    .venv\\Scripts\\python.exe -m tools.split_dxf_frames ..\\data\\drawing.dxf ..\\data\\drawing_frames

The output directory receives ``region_01.png`` etc. and a ``frames.json``
manifest containing the CAD extents and rendered pixel sizes used for validation.
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
from rendering.dxf_renderer import render_dxf_region_to_png
from rendering.regions import DrawingRegion, detect_drawing_regions


def _drawing_regions(dxf_path: Path) -> tuple[list[DrawingRegion], bool]:
    """Return detected frames, or a modelspace fallback when no frame is found."""
    import ezdxf
    from ezdxf import bbox

    document = ezdxf.readfile(dxf_path)
    layout = document.modelspace()
    regions = detect_drawing_regions(layout)
    if regions:
        return regions, False
    extent = bbox.extents(layout)
    if not extent.has_data:
        raise DrawingAnalysisError("DXF 模型空间没有可渲染实体。")
    return [DrawingRegion(
        "modelspace", float(extent.extmin.x), float(extent.extmin.y),
        float(extent.extmax.x), float(extent.extmax.y),
    )], True


def split_dxf_frames(
    dxf_path: Path,
    output_dir: Path,
    *,
    dpi: int = 450,
    max_size_inches: float = 10.0,
    overwrite: bool = False,
) -> dict[str, object]:
    """Detect main frames, render each one to PNG, and return a JSON manifest."""
    if dxf_path.suffix.casefold() != ".dxf":
        raise DrawingAnalysisError("输入文件必须是 .dxf。")
    if not dxf_path.is_file():
        raise DrawingAnalysisError(f"未找到 DXF 文件：{dxf_path}")
    if dpi < 72:
        raise DrawingAnalysisError("dpi 必须不小于 72。")
    if max_size_inches <= 0:
        raise DrawingAnalysisError("max_size_inches 必须大于 0。")
    if output_dir.exists():
        if not overwrite and any(output_dir.iterdir()):
            raise DrawingAnalysisError(f"输出目录非空：{output_dir}；如需覆盖请使用 --overwrite。")
        if overwrite:
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    regions, used_modelspace_fallback = _drawing_regions(dxf_path)
    images: list[dict[str, object]] = []
    for index, region in enumerate(regions, start=1):
        filename = f"region_{index:02d}.png"
        image_path = output_dir / filename
        render_dxf_region_to_png(
            dxf_path, image_path, region, dpi=dpi, max_size_inches=max_size_inches,
        )
        try:
            from PIL import Image
            with Image.open(image_path) as image:
                width_px, height_px = image.size
        except Exception as exc:
            raise DrawingAnalysisError(f"无法读取已生成的 PNG：{image_path}") from exc
        images.append({
            "index": index - 1,
            "name": f"主图框 {index}",
            "filename": filename,
            "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y],
            "image_width": width_px,
            "image_height": height_px,
        })

    manifest = {
        "source_dxf": str(dxf_path.resolve()),
        "frame_count": len(images),
        "used_modelspace_fallback": used_modelspace_fallback,
        "render": {"dpi": dpi, "max_size_inches": max_size_inches},
        "frames": images,
    }
    (output_dir / "frames.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dxf", type=Path, help="待拆分的 DXF 文件。")
    parser.add_argument("output_dir", type=Path, help="保存每个主图框 PNG 的目录。")
    parser.add_argument("--dpi", type=int, default=450, help="每个主图框 PNG 的渲染 DPI，默认 450。")
    parser.add_argument("--max-size-inches", type=float, default=10.0, help="最长边的最大英寸数，默认 10。")
    parser.add_argument("--overwrite", action="store_true", help="清空已有输出目录后重新生成。")
    parser.add_argument("--dry-run", action="store_true", help="仅输出检测到的主图框范围，不渲染或写入文件。")
    arguments = parser.parse_args()
    input_dxf = arguments.input_dxf.resolve()
    output_dir = arguments.output_dir.resolve()
    try:
        if arguments.dry_run:
            regions, used_modelspace_fallback = _drawing_regions(input_dxf)
            print(json.dumps({
                "frame_count": len(regions),
                "used_modelspace_fallback": used_modelspace_fallback,
                "frames": [
                    {"index": index, "name": region.name, "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y]}
                    for index, region in enumerate(regions)
                ],
            }, ensure_ascii=False, indent=2))
            return 0
        manifest = split_dxf_frames(
            input_dxf, output_dir, dpi=arguments.dpi,
            max_size_inches=arguments.max_size_inches, overwrite=arguments.overwrite,
        )
    except DrawingAnalysisError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "frame_count": manifest["frame_count"],
        "used_modelspace_fallback": manifest["used_modelspace_fallback"],
        "output_dir": str(output_dir),
        "manifest": str(output_dir / "frames.json"),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
