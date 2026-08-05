"""Diagnose why a DXF can or cannot be split into main drawing frames.

Run from ``backend/``:
    .venv\\Scripts\\python.exe -m tools.dxf_frame_diagnostics ..\\data\\drawing.dxf
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import ezdxf
from ezdxf import bbox

from rendering.regions import _rectangle_from_polyline, detect_drawing_regions


def _extent(entity: Any) -> list[float] | None:
    try:
        entity_extent = bbox.extents([entity])
    except Exception:
        return None
    if not entity_extent.has_data:
        return None
    return [
        round(float(entity_extent.extmin.x), 4), round(float(entity_extent.extmin.y), 4),
        round(float(entity_extent.extmax.x), 4), round(float(entity_extent.extmax.y), 4),
    ]


def _polyline_report(layout: Any) -> dict[str, object]:
    total = closed = four_point = axis_aligned_rectangles = 0
    examples: list[dict[str, object]] = []
    dimension_counts: Counter[tuple[str, int, int]] = Counter()
    for entity in layout:
        if entity.dxftype() != "LWPOLYLINE":
            continue
        total += 1
        points = list(entity.get_points("xy"))
        if entity.closed:
            closed += 1
        if len(points) == 4:
            four_point += 1
        rectangle = _rectangle_from_polyline(entity)
        if rectangle is not None:
            axis_aligned_rectangles += 1
            min_x, min_y, max_x, max_y = rectangle
            dimension_counts[(entity.dxf.layer or "0", round(max_x - min_x), round(max_y - min_y))] += 1
            if len(examples) < 20:
                examples.append({"extent": [round(value, 4) for value in rectangle], "layer": entity.dxf.layer or "0"})
    return {
        "total": total,
        "closed": closed,
        "four_point": four_point,
        "axis_aligned_rectangle_candidates": axis_aligned_rectangles,
        "candidate_examples": examples,
        "repeated_dimensions": [
            {"layer": layer, "width": width, "height": height, "count": count}
            for (layer, width, height), count in dimension_counts.most_common(30)
        ],
    }


def diagnose(dxf_path: Path) -> dict[str, object]:
    document = ezdxf.readfile(dxf_path)
    layouts: dict[str, object] = {}
    for layout in [document.modelspace(), *document.layouts]:
        # modelspace is included by document.layouts on some ezdxf versions.
        name = layout.name
        if name in layouts:
            continue
        entities = list(layout)
        layout_extent = bbox.extents(entities)
        type_counts = Counter(entity.dxftype() for entity in entities)
        layouts[name] = {
            "entity_count": len(entities),
            "entity_types": dict(type_counts.most_common()),
            "extent": (
                [round(float(layout_extent.extmin.x), 4), round(float(layout_extent.extmin.y), 4), round(float(layout_extent.extmax.x), 4), round(float(layout_extent.extmax.y), 4)]
                if layout_extent.has_data else None
            ),
            "polyline_analysis": _polyline_report(layout),
            "detected_main_frames": [
                {"name": region.name, "cad_extent": [region.min_x, region.min_y, region.max_x, region.max_y]}
                for region in detect_drawing_regions(layout)
            ],
            "largest_entities": [
                {"type": entity.dxftype(), "layer": entity.dxf.layer or "0", "extent": _extent(entity)}
                for entity in sorted(entities, key=lambda item: (lambda values: 0.0 if values is None else (values[2] - values[0]) * (values[3] - values[1]))(_extent(item)), reverse=True)[:10]
            ],
        }
    return {
        "source_dxf": str(dxf_path.resolve()),
        "dxf_version": document.dxfversion,
        "modelspace_name": document.modelspace().name,
        "layouts": layouts,
        "block_count": len(document.blocks),
        "non_anonymous_blocks": [block.name for block in document.blocks if not block.name.startswith("*")][:100],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dxf", type=Path)
    parser.add_argument("--output", type=Path, help="Optional JSON report path.")
    arguments = parser.parse_args()
    if not arguments.input_dxf.is_file():
        parser.error(f"未找到 DXF 文件：{arguments.input_dxf}")
    report = diagnose(arguments.input_dxf)
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
