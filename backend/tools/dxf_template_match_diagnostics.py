"""Diagnose why vector DXF template matching did or did not find candidates."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import ezdxf
from ezdxf import bbox

from recognition.vector_template_matcher import Segment, segments_from_dxf


def _entity_summary(path: Path) -> dict[str, object]:
    document = ezdxf.readfile(path)
    layout = document.modelspace()
    entities = list(layout)
    extent = bbox.extents(entities)
    counts = Counter(entity.dxftype() for entity in entities)
    return {
        "dxf_version": document.dxfversion,
        "entity_count": len(entities),
        "entity_types": dict(counts.most_common()),
        "extent": [float(extent.extmin.x), float(extent.extmin.y), float(extent.extmax.x), float(extent.extmax.y)] if extent.has_data else None,
    }


def _length_summary(segments: list[Segment]) -> dict[str, object]:
    lengths = sorted(segment.length for segment in segments)
    if not lengths:
        return {"count": 0}
    return {
        "count": len(lengths), "min": lengths[0], "median": lengths[len(lengths) // 2], "max": lengths[-1],
        "top_lengths": [round(length, 6) for length in lengths[-10:]],
    }


def diagnose(main_dxf: Path, templates: list[Path], *, min_scale: float, max_scale: float) -> dict[str, object]:
    target = segments_from_dxf(main_dxf)
    target_lengths = [segment.length for segment in target]
    results = []
    for template_path in templates:
        segments = segments_from_dxf(template_path)
        if not segments:
            results.append({"template": str(template_path), "error": "模板没有 LINE 或直线型 LWPOLYLINE 线段。"})
            continue
        anchor = max(segments, key=lambda item: item.length)
        compatible = [length for length in target_lengths if min_scale <= length / anchor.length <= max_scale]
        scale_values = [length / anchor.length for length in target_lengths]
        results.append({
            "template": str(template_path.resolve()),
            "entity_summary": _entity_summary(template_path),
            "segment_lengths": _length_summary(segments),
            "longest_anchor": {"length": anchor.length, "angle_deg": round(anchor.angle * 180 / 3.141592653589793, 3)},
            "scale_compatible_target_anchor_count": len(compatible),
            "all_target_scale_range": [min(scale_values), max(scale_values)] if scale_values else None,
            "expected_failure": (
                "主图中没有任何线段长度落在模板最长线段对应的缩放范围内。"
                if not compatible else None
            ),
        })
    return {
        "main_dxf": str(main_dxf.resolve()),
        "main_entity_summary": _entity_summary(main_dxf),
        "main_segment_lengths": _length_summary(target),
        "settings": {"min_scale": min_scale, "max_scale": max_scale},
        "templates": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_dxf", type=Path)
    parser.add_argument("templates", type=Path, nargs="+")
    parser.add_argument("--min-scale", type=float, default=0.02)
    parser.add_argument("--max-scale", type=float, default=2.0)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    report = diagnose(arguments.main_dxf, arguments.templates, min_scale=arguments.min_scale, max_scale=arguments.max_scale)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
