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
import os
import socket
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from PIL import Image

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recognition.vlm_detector import VlmDetector

DEFAULT_DRAWING = BACKEND_ROOT / "data" / "runtime" / "renders" / "5ac35ce2-bfb3-4435-9600-ed30f3d62781.png"
DEFAULT_REFERENCE = BACKEND_ROOT / "data" / "runtime" / "reference-icons" / "capacitor" / "reference-1.png"
DEFAULT_OUTPUT_DIR = BACKEND_ROOT / "data" / "runtime" / "vlm-probes"
# The crop covers the first complete schematic panel in the supplied 4800x1131 drawing.
DEFAULT_CROP = (540, 40, 1220, 1080)


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


def _build_payload(detector: VlmDetector, reference_path: Path, crop_path: Path) -> dict[str, object]:
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
    return {
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
                    {"type": "image_url", "image_url": {"url": _data_url(reference_path)}},
                    {"type": "text", "text": "Drawing crop to inspect."},
                    {"type": "image_url", "image_url": {"url": _data_url(crop_path)}},
                ],
            },
        ],
    }


def _request_summary(detector: VlmDetector, source: Path, reference: Path, crop: Path, crop_box: tuple[int, int, int, int]) -> dict[str, object]:
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
            "api_key": "redacted",
        }


def _extract_message_content(response: dict[str, object]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message")
    return message.get("content", "") if isinstance(message, dict) else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe VLM image processing with a capacitor reference and drawing crop.")
    parser.add_argument("--drawing", type=Path, default=DEFAULT_DRAWING, help="Large rendered drawing PNG.")
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE, help="Capacitor reference PNG.")
    parser.add_argument("--crop", type=_parse_crop, default=DEFAULT_CROP, help="Crop box: xmin,ymin,xmax,ymax.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Directory for the crop and raw response JSON.")
    arguments = parser.parse_args()

    source = arguments.drawing.resolve()
    reference = arguments.reference.resolve()
    if not source.is_file():
        parser.error(f"未找到大图：{source}")
    if not reference.is_file():
        parser.error(f"未找到电容器参考图：{reference}")

    detector = VlmDetector()
    if not detector.configured:
        parser.error("缺少 VLM_OPENAI_BASE_URL/OPENAI_BASE_URL、API key 或 DRAWING_VLM_MODEL_NAME/VLLM_MODEL_NAME。")

    output_dir = arguments.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    crop_path = output_dir / "capacitor-drawing-crop.png"
    response_path = output_dir / "capacitor-vlm-response.json"
    with Image.open(source) as image:
        left, top, right, bottom = arguments.crop
        if not (0 <= left < right <= image.width and 0 <= top < bottom <= image.height):
            parser.error(f"crop 超出图像范围 {image.size}：{arguments.crop}")
        image.crop(arguments.crop).save(crop_path, format="PNG")

    payload = _build_payload(detector, reference, crop_path)
    summary = _request_summary(detector, source, reference, crop_path, arguments.crop)
    print("=== VLM image probe request (redacted) ===")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
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
    print("\n=== Complete model response ===")
    print(json.dumps(response, ensure_ascii=False, indent=2))
    print("\n=== Local validation result ===")
    print(json.dumps({
        "elapsed_ms": elapsed_ms,
        "raw_message_content": raw_content,
        "validated_detections": [detection.__dict__ for detection in parsed],
        "saved_crop": str(crop_path),
        "saved_response": str(response_path),
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
