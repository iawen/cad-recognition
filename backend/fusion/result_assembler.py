from __future__ import annotations

from pathlib import Path

from domain.models import DrawingAnalysisResult, ParsedDxfDrawing
from ingest.file_validation import sha256_file


def assemble_vector_result(
    source_path: Path,
    source_format: str,
    converted_to_dxf: bool,
    parsed: ParsedDxfDrawing,
) -> DrawingAnalysisResult:
    """Create the public result while preserving P1 evidence and limitations."""
    return DrawingAnalysisResult(
        drawing={
            "filename": source_path.name,
            "source_format": source_format.lstrip("."),
            "source_sha256": sha256_file(source_path),
            "converted_to_dxf": converted_to_dxf,
            "dxf_version": parsed.dxf_version,
            "units": parsed.units,
        },
        summary={
            "entity_count": sum(parsed.entity_types.values()),
            "component_count": len(parsed.components),
            "text_count": len(parsed.texts),
            "known_block_component_count": sum(component.source == "block" for component in parsed.components),
            "vision_component_count": sum(component.source == "vision" for component in parsed.components),
            "unknown_block_count": sum(parsed.unknown_blocks.values()),
        },
        components=parsed.components,
        texts=parsed.texts,
        audit={
            "entity_types": parsed.entity_types,
            "layers": parsed.layers,
            "unknown_blocks": parsed.unknown_blocks,
            "limitations": [
                "当前版本仅实现 DXF 矢量审计和已知 Block 识别。",
                "未识别的打散符号可由已启用的 VLM 分块识别或已配置的 OBB 基线补充；两者均需实测验证。",
                "当前版本已执行原生 DXF 文字关联，但未执行图像 OCR、连线追踪或 Netlist 生成。",
            ],
        },
    )