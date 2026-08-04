"""One-shot live VLM probe for circuit breakers in a rendered drawing region.

The probe sends the user-supplied circuit-breaker reference image and either the
whole drawing region or one selected crop. It writes the prepared image and raw
provider response to the runtime probe directory, but never writes credentials.
"""

from __future__ import annotations

import argparse
import base64
import json
import socket
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image, ImageEnhance, ImageOps

BACKEND_ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = BACKEND_ROOT.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recognition.vlm_detector import VlmDetector

DEFAULT_DRAWING = WORKSPACE_ROOT / "data" / "B电气图_主图框" / "region_01.png"
DEFAULT_REFERENCE = BACKEND_ROOT / "data" / "runtime" / "reference-icons" / "circuit_breaker" / "reference-1.png"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "data" / "runtime" / "vlm-probes"


def _parse_crop(value: str) -> tuple[int, int, int, int]:
    try:
        crop = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("crop 必须为 xmin,ymin,xmax,ymax。") from exc
    if len(crop) != 4:
        raise argparse.ArgumentTypeError("crop 必须包含四个坐标。")
    return crop  # type: ignore[return-value]


def _data_url(path: Path) -> str:
    return f"data:image/png;base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _prepare_image(
    source: Path,
    destination: Path,
    *,
    crop: tuple[int, int, int, int] | None,
    max_edge: int,
    upscale: float,
) -> tuple[tuple[int, int, int, int], float]:
    with Image.open(source) as image:
        crop_box = crop or (0, 0, image.width, image.height)
        left, top, right, bottom = crop_box
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError(f"crop 超出图像范围 {image.size}：{crop_box}")
        prepared = image.crop(crop_box).convert("RGB")
    prepared = ImageOps.autocontrast(prepared, cutoff=0.5)
    prepared = ImageEnhance.Contrast(prepared).enhance(1.25)
    scale = min(upscale, max_edge / max(prepared.width, prepared.height))
    if scale != 1.0:
        prepared = prepared.resize(
            (round(prepared.width * scale), round(prepared.height * scale)),
            Image.Resampling.LANCZOS,
        )
    prepared.save(destination, format="PNG", optimize=True)
    return crop_box, scale


def _payload(detector: VlmDetector, reference: Path, image: Path, *, max_output_tokens: int) -> dict[str, object]:
    prompt = (
        "The first image is a labelled reference showing exactly one circuit_breaker electrical symbol. "
        "The second image is a high-resolution electrical drawing crop around labels such as QF1 or QF2. "
        "In this drawing convention, QF labels can support a circuit-breaker hypothesis, but only report it when the adjacent symbol also visually matches the reference. "
        "Detect every visible circuit breaker in the second image only. Do not report symbols from the reference image and do not report fuses, "
        "switches, contactors, text labels, or wires. "
        "Return exactly this JSON object: "
        '{"components":[{"type":"circuit_breaker","bbox":[xmin,ymin,xmax,ymax],"confidence":number,"rotation_deg":number}]}. '
        "bbox coordinates are pixels in the second image. Return an empty components array if no circuit breaker is visible."
    )
    payload: dict[str, object] = {
        "model": detector.model_name,
        "temperature": detector.temperature,
        "max_tokens": max_output_tokens,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You detect electrical schematic symbols. Return JSON only; never invent a symbol when uncertain."},
            {"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "text", "text": "Reference image: circuit_breaker."},
                {"type": "image_url", "image_url": {"url": _data_url(reference), "detail": "high"}},
                {"type": "text", "text": "Drawing image to inspect."},
                {"type": "image_url", "image_url": {"url": _data_url(image), "detail": "high"}},
            ]},
        ],
    }
    if detector.disable_thinking:
        payload["thinking"] = {"type": "disabled"}
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--drawing", type=Path, default=DEFAULT_DRAWING)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--crop", type=_parse_crop)
    parser.add_argument("--max-edge", type=int, default=4096)
    parser.add_argument("--upscale", type=float, default=1.5, help="Crop enlargement factor before max-edge limiting.")
    parser.add_argument("--max-output-tokens", type=int, default=4096, help="Completion budget including provider reasoning tokens.")
    parser.add_argument("--name", default="circuit-breaker-region-01", help="Output file-name prefix for this probe.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    arguments = parser.parse_args()

    if arguments.max_edge < 512:
        parser.error("max-edge 至少为 512。")
    if not 0.5 <= arguments.upscale <= 4:
        parser.error("upscale 必须在 0.5 到 4 之间。")
    if not 256 <= arguments.max_output_tokens <= 8192:
        parser.error("max-output-tokens 必须在 256 到 8192 之间。")
    drawing, reference = arguments.drawing.resolve(), arguments.reference.resolve()
    if not drawing.is_file() or not reference.is_file():
        parser.error("未找到绘图或断路器参考 PNG。")
    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    prepared_path = output_dir / f"{arguments.name}.png"
    response_path = output_dir / f"{arguments.name}-response.json"
    try:
        crop_box, scale = _prepare_image(
            drawing, prepared_path, crop=arguments.crop, max_edge=arguments.max_edge, upscale=arguments.upscale,
        )
    except ValueError as exc:
        parser.error(str(exc))
    with Image.open(drawing) as source, Image.open(prepared_path) as prepared:
        probe_detector = VlmDetector()
        summary = {
            "model": probe_detector.model_identifier,
            "enabled": probe_detector.enabled,
            "configured": probe_detector.configured,
            "timeout_seconds": probe_detector.timeout_seconds,
            "source_size": list(source.size),
            "crop_box": list(crop_box),
            "prepared_size": list(prepared.size),
            "resize_scale": scale,
            "reference": str(reference),
            "prepared_image": str(prepared_path),
        }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if arguments.dry_run:
        return 0

    detector = VlmDetector()
    if not detector.enabled or not detector.configured:
        parser.error("VLM 未启用或缺少端点、密钥、模型配置。")
    started = time.perf_counter()
    try:
        request = Request(
            f"{detector.base_url}/chat/completions",
            data=json.dumps(_payload(detector, reference, prepared_path, max_output_tokens=arguments.max_output_tokens)).encode("utf-8"),
            headers={"Authorization": f"Bearer {detector.api_key}", "Content-Type": "application/json"}, method="POST",
        )
        with urlopen(request, timeout=detector.timeout_seconds) as http_response:
            response: dict[str, object] = json.loads(http_response.read().decode("utf-8"))
    except HTTPError as exc:
        print(json.dumps({"http_status": exc.code, "response": exc.read().decode("utf-8", errors="replace")[:500]}, ensure_ascii=False))
        return 1
    except URLError as exc:
        print(json.dumps({"error": "VLM 服务不可达", "detail": str(exc.reason)}, ensure_ascii=False))
        return 1
    except (TimeoutError, socket.timeout):
        print(json.dumps({"error": "VLM 请求超时", "timeout_seconds": detector.timeout_seconds}, ensure_ascii=False))
        return 1
    except OSError as exc:
        print(json.dumps({"error": "VLM 请求失败", "detail": str(exc)}, ensure_ascii=False))
        return 1
    except Exception as exc:
        print(json.dumps({"error": "VLM 响应无法解析", "type": type(exc).__name__, "detail": str(exc)[:500]}, ensure_ascii=False))
        return 1

    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    choices = response.get("choices", [])
    message = choices[0].get("message", {}) if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    raw_content = message.get("content", "") if isinstance(message, dict) else ""
    detections = VlmDetector._parse(raw_content, prepared_path)
    reported = []
    for detection in detections:
        reported.append({
            **detection.__dict__,
            "source_region_bbox": [
                round(crop_box[0] + (detection.center_x - detection.width / 2) / scale, 2),
                round(crop_box[1] + (detection.center_y - detection.height / 2) / scale, 2),
                round(crop_box[0] + (detection.center_x + detection.width / 2) / scale, 2),
                round(crop_box[1] + (detection.center_y + detection.height / 2) / scale, 2),
            ],
        })
    print(json.dumps({
        "elapsed_ms": round((time.perf_counter() - started) * 1000),
        "raw_message_content": raw_content,
        "validated_circuit_breakers": reported,
        "saved_response": str(response_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
