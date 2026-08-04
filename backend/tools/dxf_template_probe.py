"""Inspect DXF reference-template geometry and a target drawing.

Temporary POC utility for evaluating whether a supplied component DXF is suitable
for vector-template matching against a full electrical drawing.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import bbox

from recognition.vector_template_matcher import match_template, segments_from_dxf


def _extent(entity: Any) -> list[float] | None:
    try:
        entity_bbox = bbox.extents([entity])
    except Exception:
        return None
    if not entity_bbox.has_data:
        return None
    return [
        round(float(entity_bbox.extmin.x), 4),
        round(float(entity_bbox.extmin.y), 4),
        round(float(entity_bbox.extmax.x), 4),
        round(float(entity_bbox.extmax.y), 4),
    ]


def inspect_dxf(path: Path) -> dict[str, object]:
    """Return factual modelspace geometry statistics for a DXF file."""
    document = ezdxf.readfile(path)
    modelspace = document.modelspace()
    entities = list(modelspace)
    drawing_extent = bbox.extents(entities)
    type_counts = Counter(entity.dxftype() for entity in entities)
    layer_counts = Counter((entity.dxf.layer or "0") for entity in entities)
    examples = [
        {
            "type": entity.dxftype(),
            "layer": entity.dxf.layer or "0",
            "extent": _extent(entity),
        }
        for entity in entities[:20]
    ]
    return {
        "path": str(path),
        "dxf_version": document.dxfversion,
        "modelspace_extent": (
            [
                round(float(drawing_extent.extmin.x), 4),
                round(float(drawing_extent.extmin.y), 4),
                round(float(drawing_extent.extmax.x), 4),
                round(float(drawing_extent.extmax.y), 4),
            ]
            if drawing_extent.has_data
            else None
        ),
        "entity_types": dict(type_counts.most_common()),
        "layers": dict(layer_counts.most_common()),
        "block_names": [block.name for block in document.blocks if not block.name.startswith("*")],
        "examples": examples,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--tolerance", type=float, default=0.02)
    arguments = parser.parse_args()
    template_segments = segments_from_dxf(arguments.reference)
    target_segments = segments_from_dxf(arguments.target)
    matches = match_template(template_segments, target_segments, endpoint_tolerance=arguments.tolerance)
    print(json.dumps({
        "reference": inspect_dxf(arguments.reference),
        "target": inspect_dxf(arguments.target),
        "matching": {
            "template_segment_count": len(template_segments),
            "target_segment_count": len(target_segments),
            "endpoint_tolerance": arguments.tolerance,
            "match_count": len(matches),
            "matches": [match.__dict__ | {"confidence": match.confidence} for match in matches[:50]],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
