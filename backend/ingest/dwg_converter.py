from __future__ import annotations

import os
import shutil
import shlex
import subprocess
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from domain.errors import DrawingAnalysisError
from tools.logger import logger


_ENABLED_VALUES = {"1", "true", "yes", "on"}


def use_realdwg() -> bool:
    """Return whether DWG ingestion must use the configured RealDWG sidecar."""
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    return os.getenv("DRAWING_USE_REALDWG", "").casefold() in _ENABLED_VALUES


def _find_converter() -> str | None:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    configured = os.getenv("ODA_FILE_CONVERTER") or os.getenv("DWG_CONVERTER")
    if configured and Path(configured).is_file():
        logger.info("DWG converter resolved from local environment path=%s", configured)
        return configured
    if configured:
        logger.warning("Configured DWG converter path does not exist path=%s", configured)
    converter = shutil.which("ODAFileConverter") or shutil.which("ODAFileConverter.exe")
    if converter:
        logger.info("DWG converter resolved from PATH path=%s", converter)
    else:
        logger.error("DWG converter unavailable: ODA_FILE_CONVERTER is unset and ODAFileConverter is not on PATH.")
    return converter


def convert_dwg_to_dxf(dwg_path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    """Convert a DWG using an ODA adapter and retain the temporary output."""
    if use_realdwg():
        return convert_dwg_with_realdwg(dwg_path)
    converter = _find_converter()
    if not converter:
        raise DrawingAnalysisError(
            "无法解析 DWG：未配置 ODA File Converter。请设置 ODA_FILE_CONVERTER 为 "
            "ODAFileConverter.exe 的绝对路径，或先转换为 DXF 后上传。"
        )

    temp_dir = tempfile.TemporaryDirectory(prefix="drawing-recognition-")
    root = Path(temp_dir.name)
    input_dir, output_dir = root / "input", root / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    shutil.copy2(dwg_path, input_dir / dwg_path.name)
    command = [converter, str(input_dir), str(output_dir), "ACAD2018", "DXF", "0", "1"]
    logger.info("DWG conversion started source=%s target_format=DXF", dwg_path)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as exc:
        temp_dir.cleanup()
        raise DrawingAnalysisError("DWG 转换超时（120 秒）") from exc
    if completed.returncode != 0:
        temp_dir.cleanup()
        message = (completed.stderr or completed.stdout or "未知转换错误").strip()
        logger.error("DWG conversion failed source=%s return_code=%s message=%s", dwg_path, completed.returncode, message[:500])
        raise DrawingAnalysisError(f"DWG 转换失败：{message[:500]}")

    candidates = list(output_dir.rglob("*.dxf")) + list(output_dir.rglob("*.DXF"))
    if not candidates:
        temp_dir.cleanup()
        logger.error("DWG conversion produced no DXF source=%s", dwg_path)
        raise DrawingAnalysisError("DWG 转换未生成 DXF 文件，请检查转换器版本和输入图纸。")
    logger.info("DWG conversion succeeded source=%s dxf=%s", dwg_path, candidates[0])
    return candidates[0], temp_dir


def convert_dwg_with_realdwg(dwg_path: Path) -> tuple[Path, tempfile.TemporaryDirectory[str]]:
    """Use a RealDWG-backed sidecar to open DWG directly and export interoperable DXF.

    RealDWG is a commercial C++/.NET SDK and is intentionally isolated from the
    Python worker. ``REALDWG_PARSER_COMMAND`` must point at an installed sidecar
    executable; input DWG and output DXF paths are appended as its final args.
    """
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    configured_command = os.getenv("REALDWG_PARSER_COMMAND", "").strip()
    if not configured_command:
        raise DrawingAnalysisError(
            "已启用 DRAWING_USE_REALDWG，但未配置 REALDWG_PARSER_COMMAND。"
            "请部署 RealDWG .NET/C++ 侧车并配置其可执行命令，或将该开关设为 false。"
        )
    command = shlex.split(configured_command, posix=False)
    if not command:
        raise DrawingAnalysisError("REALDWG_PARSER_COMMAND 无效。")

    temp_dir = tempfile.TemporaryDirectory(prefix="drawing-realdwg-")
    root = Path(temp_dir.name)
    output_path = root / f"{dwg_path.stem}.dxf"
    command.extend([str(dwg_path), str(output_path)])
    logger.info("RealDWG sidecar started source=%s", dwg_path)
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
    except FileNotFoundError as exc:
        temp_dir.cleanup()
        raise DrawingAnalysisError("RealDWG 侧车命令不存在，请检查 REALDWG_PARSER_COMMAND。") from exc
    except subprocess.TimeoutExpired as exc:
        temp_dir.cleanup()
        raise DrawingAnalysisError("RealDWG 解析超时（120 秒）。") from exc
    if completed.returncode != 0 or not output_path.is_file():
        temp_dir.cleanup()
        message = (completed.stderr or completed.stdout or "未生成 DXF 输出").strip()
        raise DrawingAnalysisError(f"RealDWG 解析失败：{message[:500]}")
    logger.info("RealDWG sidecar succeeded source=%s dxf=%s", dwg_path, output_path)
    return output_path, temp_dir