"""Extract component quantities from a table PNG with the configured VLM."""

from __future__ import annotations

import argparse
import base64
import io
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recognition.vlm_detector import VlmDetector, enforce_vlm_request_interval, log_vlm_response_content
from tools.logger import logger


def _prepare_image(image_path: Path, max_long_edge: int) -> tuple[bytes, int, int]:
    from PIL import Image

    with Image.open(image_path) as image:
        rendered = image.convert("RGB")
        if max(rendered.size) > max_long_edge:
            ratio = max_long_edge / max(rendered.size)
            rendered = rendered.resize(
                (round(rendered.width * ratio), round(rendered.height * ratio)),
                Image.Resampling.LANCZOS,
            )
        output = io.BytesIO()
        rendered.save(output, format="JPEG", quality=96, optimize=True)
        return output.getvalue(), rendered.width, rendered.height


def _normalize_components(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("components"), list):
        return []
    normalized: list[dict[str, object]] = []
    for item in payload["components"]:
        if not isinstance(item, dict):
            continue
        try:
            quantity = float(item.get("quantity"))
        except (TypeError, ValueError):
            continue
        if quantity < 0:
            continue
        name = str(item.get("name") or item.get("component_type") or "").strip()
        if not name:
            continue
        try:
            confidence = min(1.0, max(0.0, float(item.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0.0
        normalized.append({
            "name": name,
            "component_type": str(item.get("component_type") or "unknown").strip(),
            "quantity": quantity,
            "unit": str(item.get("unit") or "台").strip(),
            "confidence": confidence,
            "evidence": str(item.get("evidence") or "").strip(),
        })
    return normalized


def _request_quantity_extraction(detector: VlmDetector, prompt: str, *, source_name: str) -> tuple[object, str, int]:
    """Submit a constrained text-only quantity extraction request."""
    payload: dict[str, object] = {
        "model": detector.model_name,
        "temperature": detector.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a precise electrical schedule reader. Return JSON only; do not infer missing values."},
            {"role": "user", "content": prompt},
        ],
    }
    if detector.disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    started = time.perf_counter()
    logger.info(
        "VLM table quantity request started model=%s source=%s timeout_seconds=%s",
        detector.model_identifier, source_name, detector.timeout_seconds,
    )
    try:
        enforce_vlm_request_interval(purpose="table_native_text_quantity_extraction")
        request = Request(
            f"{detector.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {detector.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=detector.timeout_seconds) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("VLM table quantity request failed model=%s source=%s outcome=http_%s", detector.model_identifier, source_name, exc.code)
        raise RuntimeError(f"VLM 数量提取请求失败，HTTP 状态码：{exc.code}。") from exc
    except URLError as exc:
        logger.warning("VLM table quantity request unreachable model=%s source=%s", detector.model_identifier, source_name)
        raise RuntimeError("VLM 数量提取服务不可达。") from exc
    except TimeoutError as exc:
        logger.warning("VLM table quantity request timed out model=%s source=%s timeout_seconds=%s", detector.model_identifier, source_name, detector.timeout_seconds)
        raise RuntimeError("VLM 数量提取请求超时。") from exc
    raw_content = response_body.get("choices", [{}])[0].get("message", {}).get("content", "")
    log_vlm_response_content(
        model=detector.model_identifier,
        purpose="table_native_text_quantity_extraction",
        content=raw_content,
    )
    try:
        decoded = json.loads(raw_content)
    except (TypeError, json.JSONDecodeError):
        decoded = {}
    duration_ms = round((time.perf_counter() - started) * 1000)
    logger.info("VLM table quantity request completed model=%s source=%s duration_ms=%s", detector.model_identifier, source_name, duration_ms)
    return decoded, raw_content, duration_ms


def extract_component_quantities_from_native_texts(texts: list[str], *, table_name: str) -> dict[str, object]:
    """Extract component quantities from native DXF TEXT/MTEXT in one table."""
    detector = VlmDetector()
    if not detector.enabled:
        raise RuntimeError("DRAWING_VLM_ENABLED 未启用，未发送模型请求。")
    if not detector.configured:
        raise RuntimeError("VLM 配置不完整：需要端点、密钥和模型名。")
    source_texts = [text.strip() for text in texts if text and text.strip()]
    if not source_texts:
        return {
            "source": "native_dxf_text", "table_name": table_name, "native_text_count": 0,
            "model": detector.model_identifier, "component_count": 0, "components": [],
            "notes": "确认的表格区域没有可解析的原生 DXF 文字。", "review_required": True,
        }
    prompt = (
        "The following strings were parsed directly from DXF TEXT/MTEXT entities inside an electrical component quantity table. "
        "Extract only explicit component names, models/categories, and numeric quantities. Do not infer missing values. "
        "Keep entries for separate cabinets or circuits separate. Ignore titles, headers, notes, parameter rows without quantities, and unreadable values. "
        "Return strict JSON: {\"components\":[{\"name\":string,\"component_type\":string,\"quantity\":number,\"unit\":string,\"confidence\":number,\"evidence\":string}],\"notes\":string}.\n"
        "DXF text entries:\n" + "\n".join(f"- {text}" for text in source_texts)
    )
    decoded, raw_content, duration_ms = _request_quantity_extraction(detector, prompt, source_name=table_name)
    components = _normalize_components(decoded)
    return {
        "source": "native_dxf_text", "table_name": table_name, "native_text_count": len(source_texts),
        "model": detector.model_identifier, "duration_ms": duration_ms, "component_count": len(components),
        "components": components, "notes": decoded.get("notes", "") if isinstance(decoded, dict) else "",
        "raw_response": raw_content, "review_required": True,
        "limitations": [
            "结果仅使用原生 DXF 文字实体，不使用图像 OCR 或表格截图。",
            "DXF 文字实体的读取顺序不保证等同表格单元格顺序，必须与图纸复核。",
        ],
    }


def extract_component_quantities(
    image_path: Path,
    output_path: Path | None = None,
    *,
    max_long_edge: int = 3600,
) -> dict[str, object]:
    """Call the configured VLM and save a reviewable table extraction result."""
    if not image_path.is_file():
        raise ValueError(f"未找到表格图像：{image_path}")
    detector = VlmDetector()
    if not detector.enabled:
        raise RuntimeError("DRAWING_VLM_ENABLED 未启用，未发送 VLM 请求。")
    if not detector.configured:
        raise RuntimeError("VLM 配置不完整：需要端点、密钥和模型名。")

    image_bytes, width, height = _prepare_image(image_path, max_long_edge)
    logger.info(
        "VLM table image quantity request started model=%s image=%s image_size=%sx%s timeout_seconds=%s",
        detector.model_identifier, image_path.name, width, height, detector.timeout_seconds,
    )
    prompt = """这是电气图纸中的元器件数量说明表。请逐行读取元器件名称、型号或类别和数量。
仅提取表格明确列出的元器件数量；不要把电路图符号、图号、页码、备注、表头或空白单元格计入。
同种元器件在不同柜号或回路列出现时，按表中每一行或每个型号分别列出，不要自行合并，也不要猜测模糊文本。
返回严格 JSON：{\"components\":[{\"name\":string,\"component_type\":string,\"quantity\":number,\"unit\":string,\"confidence\":number,\"evidence\":string}],\"notes\":string}。
quantity 必须是直接可读的数字；不确定时不要返回该项。"""
    payload: dict[str, object] = {
        "model": detector.model_name,
        "temperature": detector.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You are a precise electrical schedule table reader. Return JSON only; do not infer missing values."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")}},
            ]},
        ],
    }
    if detector.disable_thinking:
        payload["thinking"] = {"type": "disabled"}

    started = time.perf_counter()
    try:
        enforce_vlm_request_interval(purpose="table_image_quantity_extraction")
        request = Request(
            f"{detector.base_url}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {detector.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=detector.timeout_seconds) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        logger.warning("VLM table image quantity request failed model=%s image=%s outcome=http_%s", detector.model_identifier, image_path.name, exc.code)
        raise RuntimeError(f"VLM 数量提取请求失败，HTTP 状态码：{exc.code}。") from exc
    except URLError as exc:
        logger.warning("VLM table image quantity request unreachable model=%s image=%s", detector.model_identifier, image_path.name)
        raise RuntimeError("VLM 数量提取服务不可达。") from exc
    except TimeoutError as exc:
        logger.warning("VLM table image quantity request timed out model=%s image=%s timeout_seconds=%s", detector.model_identifier, image_path.name, detector.timeout_seconds)
        raise RuntimeError("VLM 数量提取请求超时。") from exc

    raw_content = response_body.get("choices", [{}])[0].get("message", {}).get("content", "")
    log_vlm_response_content(
        model=detector.model_identifier,
        purpose="table_image_quantity_extraction",
        content=raw_content,
    )
    try:
        decoded = json.loads(raw_content)
    except (TypeError, json.JSONDecodeError):
        decoded = {}
    components = _normalize_components(decoded)
    duration_ms = round((time.perf_counter() - started) * 1000)
    logger.info(
        "VLM table image quantity request completed model=%s image=%s components=%s duration_ms=%s",
        detector.model_identifier, image_path.name, len(components), duration_ms,
    )
    result: dict[str, object] = {
        "source_image": str(image_path.resolve()),
        "image_size_sent": [width, height],
        "model": detector.model_identifier,
        "duration_ms": duration_ms,
        "component_count": len(components),
        "components": components,
        "notes": decoded.get("notes", "") if isinstance(decoded, dict) else "",
        "raw_response": raw_content,
        "review_required": True,
        "limitations": [
            "结果由视觉模型从表格图像读取，必须与原始表格逐项人工核对。",
            "模糊、遮挡或模型无法确认的单元格不会被可靠提取。",
        ],
    }
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="已拆分出的表格 PNG。")
    parser.add_argument("output", type=Path, help="保存 VLM 数量提取 JSON 的路径。")
    parser.add_argument("--max-long-edge", type=int, default=3600)
    arguments = parser.parse_args()
    try:
        result = extract_component_quantities(
            arguments.image.resolve(), arguments.output.resolve(), max_long_edge=arguments.max_long_edge,
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "output": str(arguments.output.resolve()),
        "component_count": result["component_count"],
        "model": result["model"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
