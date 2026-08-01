"""OpenAI-compatible VLM adapter for feasibility validation.

The adapter is deliberately opt-in. It reads endpoint credentials from the local
``.env`` file but never returns them in API responses, task records, or logs.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from recognition.component_catalog import supported_component_types

SUPPORTED_COMPONENT_TYPES = supported_component_types()
_ENABLED_VALUES = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class VlmDetection:
    label: str
    confidence: float
    center_x: float
    center_y: float
    width: float
    height: float
    angle_deg: float


class VlmDetector:
    """Detect electrical symbols in one image tile via a multimodal model."""

    def __init__(self) -> None:
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        self.enabled = os.getenv("DRAWING_VLM_ENABLED", "").casefold() in _ENABLED_VALUES
        self.base_url = (os.getenv("VLLM_OPENAI_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").rstrip("/")
        self.api_key = os.getenv("VLLM_OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("VLLM_MODEL_NAME") or os.getenv("MODEL_NAME")

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key and self.model_name)

    @property
    def model_identifier(self) -> str:
        return self.model_name or "unconfigured-vlm"

    def detect(self, image_path: Path) -> list[VlmDetection]:
        if not self.enabled:
            return []
        if not self.configured:
            raise RuntimeError("已启用 DRAWING_VLM_ENABLED，但缺少模型端点、密钥或模型名配置。")

        image_data = base64.b64encode(image_path.read_bytes()).decode("ascii")
        mime_type = "image/png" if image_path.suffix.casefold() == ".png" else "image/jpeg"
        payload = {
            "model": self.model_name,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "You detect electrical schematic symbols. Return JSON only; never invent a symbol when uncertain.",
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": self._prompt()},
                        {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
                    ],
                },
            ],
        }
        try:
            request = Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=90) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"VLM 请求失败，HTTP 状态码：{exc.code}。") from exc
        except URLError as exc:
            raise RuntimeError("VLM 服务不可达。") from exc
        except TimeoutError as exc:
            raise RuntimeError("VLM 请求超时。") from exc

        content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        return self._parse(content, image_path)

    @staticmethod
    def _prompt() -> str:
        labels = ", ".join(SUPPORTED_COMPONENT_TYPES)
        return (
            "Find only visible electrical symbols in this image tile. Allowed types: " + labels + ". "
            "Return exactly this JSON object: {\"components\":[{\"type\":string,\"bbox\":[xmin,ymin,xmax,ymax],"
            "\"confidence\":number,\"rotation_deg\":number}]}. bbox coordinates are pixels in this tile; "
            "use 0<=xmin<xmax and 0<=ymin<ymax. Return an empty components array if no allowed symbol is visible."
        )

    @staticmethod
    def _parse(content: str, image_path: Path) -> list[VlmDetection]:
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return []
        try:
            from PIL import Image
            with Image.open(image_path) as image:
                image_width, image_height = image.size
        except Exception:
            return []

        detections: list[VlmDetection] = []
        for item in decoded.get("components", []):
            label, bbox = item.get("type"), item.get("bbox")
            if label not in SUPPORTED_COMPONENT_TYPES or not isinstance(bbox, list) or len(bbox) != 4:
                continue
            try:
                xmin, ymin, xmax, ymax = (float(value) for value in bbox)
                confidence = min(max(float(item.get("confidence", 0)), 0), 1)
                rotation = float(item.get("rotation_deg", 0))
            except (TypeError, ValueError):
                continue
            xmin, xmax = max(0, xmin), min(float(image_width), xmax)
            ymin, ymax = max(0, ymin), min(float(image_height), ymax)
            if xmin >= xmax or ymin >= ymax:
                continue
            detections.append(VlmDetection(
                label=label, confidence=confidence, center_x=(xmin + xmax) / 2, center_y=(ymin + ymax) / 2,
                width=xmax - xmin, height=ymax - ymin, angle_deg=rotation,
            ))
        return detections