"""Overlapping image tiling with retained global pixel offsets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from rendering.regions import DrawingRegion


@dataclass(frozen=True)
class ImageTile:
    path: Path
    x_offset: int
    y_offset: int
    width: int
    height: int


@dataclass(frozen=True)
class CadTile:
    """A directly rendered visual tile with an exact CAD viewport."""

    name: str
    region: DrawingRegion
    column: int
    row: int


def _tile_starts(minimum: float, maximum: float, tile_span: float, overlap_span: float) -> list[float]:
    if maximum <= minimum:
        raise ValueError("CAD 范围必须具有正宽度和正高度。")
    if tile_span <= 0 or not 0 <= overlap_span < tile_span:
        raise ValueError("CAD 切片范围或重叠范围无效。")
    if maximum - minimum <= tile_span:
        return [minimum]

    starts = [minimum]
    stride = tile_span - overlap_span
    while True:
        next_start = starts[-1] + stride
        if next_start + tile_span >= maximum:
            final_start = maximum - tile_span
            if final_start > starts[-1]:
                starts.append(final_start)
            return starts
        starts.append(next_start)


def create_cad_tiles(
    region: DrawingRegion,
    *,
    tile_size: int = 1536,
    overlap: int = 192,
    reference_long_edge_px: int = 3600,
) -> list[CadTile]:
    """Plan overlapping CAD viewports for direct DXF rendering.

    ``reference_long_edge_px`` preserves the spatial density of the previous
    frame-render-then-crop pipeline, whose longest frame edge was rendered at
    approximately 3600 pixels before 1536-pixel crops were made.
    """
    if tile_size <= 0 or reference_long_edge_px <= 0 or not 0 <= overlap < tile_size:
        raise ValueError("CAD 切片像素参数无效。")
    pixels_per_cad_unit = reference_long_edge_px / max(region.width, region.height)
    tile_span = tile_size / pixels_per_cad_unit
    overlap_span = overlap / pixels_per_cad_unit
    x_starts = _tile_starts(region.min_x, region.max_x, tile_span, overlap_span)
    y_starts = _tile_starts(region.min_y, region.max_y, tile_span, overlap_span)

    tiles: list[CadTile] = []
    for row, min_y in enumerate(y_starts):
        for column, min_x in enumerate(x_starts):
            max_x = min(min_x + tile_span, region.max_x)
            max_y = min(min_y + tile_span, region.max_y)
            tiles.append(CadTile(
                name=f"tile_{column}_{row}.png",
                region=DrawingRegion(
                    f"{region.name}_tile_{column}_{row}", min_x, min_y, max_x, max_y,
                ),
                column=column,
                row=row,
            ))
    return tiles


def create_tiles(image_path: Path, output_dir: Path, *, tile_size: int = 1536, overlap: int = 192) -> list[ImageTile]:
    """Create overlapping PNG tiles and preserve their full-image offsets."""
    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError("缺少 Pillow，无法切分渲染图。") from exc
    if not 0 <= overlap < tile_size:
        raise ValueError("overlap 必须小于 tile_size。")
    output_dir.mkdir(parents=True, exist_ok=True)
    with Image.open(image_path) as image:
        width, height = image.size
        stride = tile_size - overlap
        tiles: list[ImageTile] = []
        for y in range(0, height, stride):
            for x in range(0, width, stride):
                right, bottom = min(x + tile_size, width), min(y + tile_size, height)
                tile_path = output_dir / f"tile_{x}_{y}.png"
                image.crop((x, y, right, bottom)).save(tile_path)
                tiles.append(ImageTile(tile_path, x, y, right - x, bottom - y))
        return tiles