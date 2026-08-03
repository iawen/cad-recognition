"""Manual integration probe for VLM image input and capacitor recognition.

The probe deliberately calls the configured OpenAI-compatible vision endpoint once.
It sends one labelled capacitor reference plus a cropped region from the supplied
rendered drawing, saves the crop and complete response JSON locally, and prints
a redacted request summary plus the full model response.

Run from ``backend/``:
    .venv\\Scripts\\python.exe tools\\vlm_capacitor_probe.py
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
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recognition.vlm_detector import VlmDetector

DEFAULT_DRAWING = BACKEND_ROOT / "data" / "runtime" / "renders" / "5ac35ce2-bfb3-4435-9600-ed30f3d62781.png"
DEFAULT_REFERENCE = BACKEND_ROOT / "data" / "runtime" / "reference-icons" / "capacitor" / "reference-1.png"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "data" / "runtime" / "vlm-probes"
# The first probe included title blocks and large blank regions. This tighter
# crop targets the actual 10 kV single-line diagram in the supplied drawing.
DEFAULT_CROP = (760, 350, 1100, 600)
DEFAULT_SCALE = 4


def _data_url(image_path: Path) -> str:
    mime_type = "image/png" if image_path.suffix.casefold() == ".png" else "image/jpeg"
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _parse_crop(value: str) -> tuple[int, int, int, int]:
    try:
        coordinates = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("crop 必须为 xmin,ymin,xmax,ymax。") from exc
    if len(coordinates) != 4:
        raise argparse.ArgumentTypeError("crop 必须包含四个坐标：xmin,ymin,xmax,ymax。")
    return coordinates  # type: ignore[return-value]


def _image_content(image_path: Path, detail: str) -> dict[str, object]:
    return {"type": "image_url", "image_url": {"url": _data_url(image_path), "detail": detail}}


def _build_payload(
    detector: VlmDetector,
    reference_path: Path,
    crop_path: Path,
    *,
    detail: str,
    extra_request: dict[str, object],
    max_output_tokens: int | None,
) -> dict[str, object]:
    prompt = (
        "The first image is a labelled reference showing exactly one capacitor symbol. "
        "The second image is a cropped electrical schematic drawing. Detect every visible capacitor "
        "symbol in the second image only. Do not report symbols from the reference image. "
        "Return exactly this JSON object: "
        '{"components":[{"type":"capacitor","bbox":[xmin,ymin,xmax,ymax],'
        '"confidence":number,"rotation_deg":number}]}. '
        "bbox coordinates are pixels in the second image; use 0<=xmin<xmax and 0<=ymin<ymax. "
        "Return an empty components array if no capacitor is visible."
    )
    payload: dict[str, object] = {
        "model": detector.model_name,
        "temperature": detector.temperature,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": "You detect electrical schematic symbols. Return JSON only; never invent a symbol when uncertain.",
            },
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "text", "text": "Reference image: capacitor."},
                    _image_content(reference_path, detail),
                    {"type": "text", "text": "Drawing crop to inspect."},
                    _image_content(crop_path, detail),
                ],
            },
        ],
    }
    if max_output_tokens is not None:
        payload["max_tokens"] = max_output_tokens
    payload.update(extra_request)
    return payload


def _request_summary(
    detector: VlmDetector,
    source: Path,
    reference: Path,
    crop: Path,
    crop_box: tuple[int, int, int, int],
    *,
    scale: int,
    detail: str,
    extra_request: dict[str, object],
    max_output_tokens: int | None,
) -> dict[str, object]:
    with Image.open(source) as source_image, Image.open(reference) as reference_image, Image.open(crop) as crop_image:
        return {
            "endpoint": detector.base_url,
            "model": detector.model_identifier,
            "temperature": detector.temperature,
            "timeout_seconds": detector.timeout_seconds,
            "source_image": {"path": str(source), "size": list(source_image.size)},
            "crop": {"path": str(crop), "box": list(crop_box), "size": list(crop_image.size)},
            "reference": {"label": "capacitor", "path": str(reference), "size": list(reference_image.size)},
            "response_format": "json_object",
            "image_detail": detail,
            "upscale_factor": scale,
            "max_output_tokens": max_output_tokens,
            "extra_request": extra_request,
            "api_key": "redacted",
        }


def _extract_message_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    return message.get("content", "") if isinstance(message, dict) else ""


def _parse_json_object(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError("request-extra 必须是 JSON 对象。") from exc
    if not isinstance(decoded, dict):
        raise argparse.ArgumentTypeError("request-extra 必须是 JSON 对象。")
    return decoded


def _prepare_crop(source: Path, crop_path: Path, crop_box: tuple[int, int, int, int], scale: int) -> None:
    with Image.open(source) as image:
        left, top, right, bottom = crop_box
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            raise ValueError(f"crop 超出图像范围 {image.size}：{crop_box}")
        cropped = image.crop(crop_box).convert("RGB")
    # CAD linework benefits from a tighter contrast range before enlargement.
    cropped = ImageOps.autocontrast(cropped, cutoff=0.5)
    cropped = ImageEnhance.Contrast(cropped).enhance(1.35)
    if scale > 1:
        cropped = cropped.resize((cropped.width * scale, cropped.height * scale), Image.Resampling.LANCZOS)
    cropped.save(crop_path, format="PNG", optimize=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe VLM image processing with a capacitor reference and drawing crop.")
    parser.add_argument("--drawing", type=Path, default=DEFAULT_DRAWING, help="Large rendered drawing PNG.")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE, help="Capacitor reference PNG.")
    parser.add_argument("--crop", type=_parse_crop, default=DEFAULT_CROP, help="Crop box: xmin,ymin,xmax,ymax.")
    parser.add_argument("--scale", type=int, default=DEFAULT_SCALE, help="Crop upscaling factor for vision input (default: 4).")
    parser.add_argument("--image-detail", choices=("low", "high", "auto"), default="high", help="OpenAI-compatible image detail hint.")
    parser.add_argument("--temperature", type=float, default=None, help="Override the configured VLM temperature for this probe only.")
    parser.add_argument("--max-output-tokens", type=int, default=512, help="Maximum completion tokens; use 0 to omit the parameter.")
    parser.add_argument(
        "--request-extra",
        type=_parse_json_object,
        default={},
        help='Provider-specific JSON request fields, e.g. {"thinking":{"type":"disabled"}}.',
    )
    parser.add_argument(
        "--disable-thinking",
        action="store_true",
        help='Add the OpenAI-compatible extension {"thinking":{"type":"disabled"}}.',
    )
    parser.add_argument("--dry-run", action="store_true", help="Prepare and report the crop without calling the VLM endpoint.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for the crop and raw response JSON.")
    arguments = parser.parse_args()

    source = arguments.drawing.resolve()
    reference = arguments.reference.resolve()
    if not source.is_file():
        parser.error(f"未找到大图：{source}")
    if not reference.is_file():
        parser.error(f"未找到电容器参考图：{reference}")
    if arguments.scale < 1 or arguments.scale > 8:
        parser.error("scale 必须在 1 到 8 之间。")
    if arguments.max_output_tokens < 0:
        parser.error("max-output-tokens 不能小于 0。")
    if arguments.disable_thinking and "thinking" in arguments.request_extra:
        parser.error("disable-thinking 不能与 request-extra 中的 thinking 同时使用。")

    detector = VlmDetector()
    if not detector.configured:
        parser.error("缺少 VLM_OPENAI_BASE_URL/OPENAI_BASE_URL、API key 或 DRAWING_VLM_MODEL_NAME/VLLM_MODEL_NAME。")
    if arguments.temperature is not None:
        detector.temperature = arguments.temperature

    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    crop_path = output_dir / "capacitor-drawing-crop.png"
    response_path = output_dir / "capacitor-vlm-response.json"
    try:
        _prepare_crop(source, crop_path, arguments.crop, arguments.scale)
    except ValueError as exc:
        parser.error(str(exc))

    max_output_tokens = arguments.max_output_tokens or None
    if arguments.disable_thinking:
        arguments.request_extra = {**arguments.request_extra, "thinking": {"type": "disabled"}}
    payload = _build_payload(
        detector, reference, crop_path,
        detail=arguments.image_detail,
        extra_request=arguments.request_extra,
        max_output_tokens=max_output_tokens,
    )
    summary = _request_summary(
        detector, source, reference, crop_path, arguments.crop,
        scale=arguments.scale,
        detail=arguments.image_detail,
        extra_request=arguments.request_extra,
        max_output_tokens=max_output_tokens,
    )
    print("=== VLM image probe request (redacted) ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if arguments.dry_run:
        print("\n=== Dry run complete: no model request sent ===")
        return 0
    print("\n=== Calling model ===")
    started = time.perf_counter()
    try:
        request = Request(
            f"{detector.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Authorization": f"Bearer {detector.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=detector.timeout_seconds) as http_response:
            response: dict[str, object] = json.loads(http_response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(json.dumps({"http_status": exc.code, "response": error_body}, ensure_ascii=False, indent=2))
        return 1
    except URLError as exc:
        print(json.dumps({"error": "VLM 服务不可达", "detail": str(exc.reason)}, ensure_ascii=False, indent=2))
        return 1
    except (TimeoutError, socket.timeout):
        print(json.dumps({"error": "VLM 请求超时", "timeout_seconds": detector.timeout_seconds}, ensure_ascii=False, indent=2))
        return 1
    except OSError as exc:
        print(json.dumps({"error": "VLM 请求失败", "detail": str(exc)}, ensure_ascii=False, indent=2))
        return 1

    elapsed_ms = round((time.perf_counter() - started) * 1000)
    response_path.write_text(json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
    raw_content = _extract_message_content(response)
    parsed = VlmDetector._parse(raw_content, crop_path)
    message = response.get("choices", [{}])[0].get("message", {}) if isinstance(response.get("choices"), list) else {}
    reasoning = message.get("reasoning_content", "") if isinstance(message, dict) else ""
    print("\n=== Complete model response ===")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    print("\n=== Local validation result ===")
    print(json.dumps({
        "elapsed_ms": elapsed_ms,
        "raw_message_content": raw_content,
        "reasoning_character_count": len(reasoning) if isinstance(reasoning, str) else 0,
        "validated_detections": [detection.__dict__ for detection in parsed],
        "saved_crop": str(crop_path),
        "saved_response": str(response_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
