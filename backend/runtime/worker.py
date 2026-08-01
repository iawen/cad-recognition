"""Bounded local worker for P1; replaceable with a distributed queue in P3."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from runtime.repository import update_run
from service import analyze_drawing
from tools.logger import logger


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="drawing-recognition")


def submit_analysis(run_id: str, drawing_path: Path) -> None:
    logger.info("Analysis queued run_id=%s drawing_path=%s", run_id, drawing_path)
    _executor.submit(_run_analysis, run_id, drawing_path)


def _run_analysis(run_id: str, drawing_path: Path) -> None:
    logger.info("Analysis started run_id=%s drawing_path=%s", run_id, drawing_path)
    try:
        update_run(run_id, status="running", phase="preflight", progress=10, message="正在校验图纸与转换器配置。")
        update_run(run_id, status="running", phase="vector_parse", progress=45, message="正在解析 DXF 实体、Block 和原生文字。")
        result = analyze_drawing(drawing_path).model_dump()
        update_run(run_id, status="running", phase="fusion", progress=80, message="正在关联文字并组装审计证据。")
        update_run(run_id, status="succeeded", phase="done", progress=100, message="图纸识别完成。", result=result)
        logger.info("Analysis succeeded run_id=%s components=%s texts=%s", run_id, result.summary["component_count"], result.summary["text_count"])
    except Exception as exc:
        logger.exception("Analysis failed run_id=%s drawing_path=%s error=%s", run_id, drawing_path, exc)
        update_run(run_id, status="failed", phase="error", progress=100, message="图纸识别失败。", error=str(exc))