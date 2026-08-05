"""Locate multiple component DXF templates in one primary DXF drawing.

Run from ``backend/``:
    .venv\\Scripts\\python.exe -m tools.match_dxf_component_templates \
        ..\\data\\main.dxf ..\\data\\matches.json \
        ..\\templates\\circuit_breaker.dxf ..\\templates\\fuse.dxf

Each template is compared against flattened primary-DXF geometry: INSERT blocks
are expanded and CIRCLE/ARC contours are normalized into chord edges.
The JSON output contains CAD centres, scale, rotation, segment coverage, error,
and a structural score for each candidate. It is a feasibility matcher: values
are not calibrated model probabilities and should be verified on real drawings.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from domain.errors import DrawingAnalysisError
from recognition.vector_template_matcher import automatic_scale_lower_bound, automatic_scale_upper_bound, geometry_from_dxf, infer_scale_candidates, match_template
from tools.logger import logger


ProgressCallback = Callable[[str, int, str, dict[str, Any]], None]


def _validate_dxf(path: Path, *, label: str) -> None:
    if path.suffix.casefold() != ".dxf":
        raise DrawingAnalysisError(f"{label}必须是 .dxf：{path}")
    if not path.is_file():
        raise DrawingAnalysisError(f"未找到{label}：{path}")


def match_component_templates(
    main_dxf: Path,
    component_dxfs: list[Path],
    *,
    endpoint_tolerance: float = 0.02,
    min_scale: float | None = None,
    max_scale: float | None = None,
    min_confidence: float = 0.8,
    max_matches_per_template: int = 100,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, object]:
    """Match every component template and return auditable CAD candidate locations."""
    _validate_dxf(main_dxf, label="主 DXF 文件")
    if not component_dxfs:
        raise DrawingAnalysisError("至少提供一个元器件 DXF 模板。")
    if endpoint_tolerance <= 0:
        raise DrawingAnalysisError("endpoint_tolerance 必须大于 0。")
    if (min_scale is None) != (max_scale is None):
        raise DrawingAnalysisError("手动缩放时必须同时设置 min_scale 和 max_scale。")
    if min_scale is not None and (min_scale <= 0 or max_scale is None or min_scale > max_scale):
        raise DrawingAnalysisError("缩放范围无效：要求 0 < min_scale <= max_scale。")
    if not 0 <= min_confidence <= 1:
        raise DrawingAnalysisError("min_confidence 必须在 0 到 1 之间。")
    if max_matches_per_template < 1:
        raise DrawingAnalysisError("max_matches_per_template 必须不小于 1。")

    logger.info("Template matching started source=%s template_count=%s", main_dxf, len(component_dxfs))
    target_geometry = geometry_from_dxf(main_dxf)
    target_segments = target_geometry.segments
    logger.info(
        "Template matching source geometry loaded source=%s segments=%s circles=%s",
        main_dxf, len(target_segments), len(target_geometry.circles),
    )
    template_results: list[dict[str, object]] = []
    total_matches = 0
    for template_index, template_path in enumerate(component_dxfs):
        _validate_dxf(template_path, label="元器件 DXF 模板")
        logger.info("Template matching template started template=%s", template_path)
        if progress_callback:
            progress_callback(
                "template_match",
                40 + round(45 * template_index / len(component_dxfs)),
                f"正在匹配模板 {template_index + 1}/{len(component_dxfs)}：{template_path.name}。",
                {"kind": "template_match", "template_index": template_index, "template_total": len(component_dxfs), "template_name": template_path.name},
            )
        template_geometry = geometry_from_dxf(template_path)
        template_segments = template_geometry.segments
        scale_candidates = infer_scale_candidates(template_segments, target_segments)
        inferred_min_scale = automatic_scale_lower_bound(template_segments, endpoint_tolerance) if min_scale is None else min_scale
        inferred_max_scale = automatic_scale_upper_bound(template_segments, target_segments) if max_scale is None else max_scale
        raw_matches = match_template(
            template_segments, target_segments,
            min_scale=min_scale, max_scale=max_scale, endpoint_tolerance=endpoint_tolerance,
        )
        accepted = [item for item in raw_matches if item.confidence >= min_confidence][:max_matches_per_template]
        candidates = [{**asdict(item), "confidence": item.confidence} for item in accepted]
        total_matches += len(candidates)
        logger.info(
            "Template matching template completed template=%s raw_matches=%s accepted_matches=%s",
            template_path, len(raw_matches), len(candidates),
        )
        template_results.append({
            "template_dxf": str(template_path.resolve()),
            "component_name": template_path.stem,
            "template_segment_count": len(template_segments),
            "template_circle_count": len(template_geometry.circles),
            "auto_scale_candidates": {
                "count": len(scale_candidates),
                "minimum": round(scale_candidates[0], 8) if scale_candidates else None,
                "maximum": round(scale_candidates[-1], 8) if scale_candidates else None,
                "considered_minimum": round(inferred_min_scale, 8) if inferred_min_scale is not None else None,
                "considered_maximum": round(inferred_max_scale, 8) if inferred_max_scale is not None else None,
            },
            "raw_match_count": len(raw_matches),
            "accepted_match_count": len(candidates),
            "matches": candidates,
        })

    report = {
        "source_dxf": str(main_dxf.resolve()),
        "target_segment_count": len(target_segments),
        "target_circle_count": len(target_geometry.circles),
        "settings": {
            "scale_mode": "automatic" if min_scale is None else "manual",
            "endpoint_tolerance": endpoint_tolerance,
            "min_scale": min_scale,
            "max_scale": max_scale,
            "min_confidence": min_confidence,
            "max_matches_per_template": max_matches_per_template,
        },
        "template_count": len(template_results),
        "total_accepted_match_count": total_matches,
        "templates": template_results,
    }
    logger.info("Template matching completed source=%s accepted_matches=%s", main_dxf, total_matches)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("main_dxf", type=Path, help="待搜索的主 DXF 文件。")
    parser.add_argument("output_json", type=Path, help="保存元器件匹配位置的 JSON 文件。")
    parser.add_argument("component_dxfs", type=Path, nargs="+", help="一个或多个元器件 DXF 模板。")
    parser.add_argument("--endpoint-tolerance", type=float, default=0.02, help="端点匹配容差，默认 0.02 CAD 单位。")
    parser.add_argument("--min-scale", type=float, help="可选：手动最小模板缩放比例；默认自动推断。")
    parser.add_argument("--max-scale", type=float, help="可选：手动最大模板缩放比例；默认自动推断。")
    parser.add_argument("--min-confidence", type=float, default=0.8, help="输出候选的最小结构分数，默认 0.8。")
    parser.add_argument("--max-matches-per-template", type=int, default=100, help="每个模板最多输出的候选数。")
    arguments = parser.parse_args()

    try:
        report = match_component_templates(
            arguments.main_dxf.resolve(), [path.resolve() for path in arguments.component_dxfs],
            endpoint_tolerance=arguments.endpoint_tolerance, min_scale=arguments.min_scale,
            max_scale=arguments.max_scale, min_confidence=arguments.min_confidence,
            max_matches_per_template=arguments.max_matches_per_template,
        )
    except DrawingAnalysisError as exc:
        parser.error(str(exc))
    arguments.output_json.parent.mkdir(parents=True, exist_ok=True)
    arguments.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "source_dxf": report["source_dxf"],
        "template_count": report["template_count"],
        "total_accepted_match_count": report["total_accepted_match_count"],
        "output_json": str(arguments.output_json.resolve()),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
