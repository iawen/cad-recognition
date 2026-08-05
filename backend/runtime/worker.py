"""Bounded local worker for P1; replaceable with a distributed queue in P3."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from runtime.repository import RENDER_ROOT, update_run
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
        update_run(run_id, status="running", phase="vector_parse", progress=25, message="正在解析 DXF 实体、Block 和原生文字。")

        def report_work(phase: str, progress: int, message: str, work: dict[str, Any]) -> None:
            update_run(run_id, status="running", phase=phase, progress=progress, message=message, work=work)

        render_dir = RENDER_ROOT / run_id
        result = analyze_drawing(drawing_path, render_output_dir=render_dir, progress_callback=report_work).model_dump()
        update_run(run_id, status="running", phase="fusion", progress=94, message="正在关联文字并组装审计证据。")
        update_run(run_id, status="succeeded", phase="done", progress=100, message="图纸识别完成。", result=result)
        logger.info(
            "Analysis succeeded run_id=%s components=%s texts=%s base_map_count=%s",
            run_id, result["summary"]["component_count"], result["summary"]["text_count"],
            len(result.get("drawing", {}).get("base_images", [])),
        )
    except Exception as exc:
        logger.exception("Analysis failed run_id=%s drawing_path=%s error=%s", run_id, drawing_path, exc)
        update_run(run_id, status="failed", phase="error", progress=100, message="图纸识别失败。", error=str(exc))