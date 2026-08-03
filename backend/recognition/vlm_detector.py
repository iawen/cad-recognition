"""OpenAI-compatible VLM adapter for feasibility validation.

The adapter is deliberately opt-in. It reads endpoint credentials from the local
``.env`` file but never returns them in API responses, task records, or logs.
"""

from __future__ import annotations

import base64
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv

from recognition.component_catalog import supported_component_types
from recognition.reference_icons import vlm_reference_images

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
        # A generic configured LLM may be text-only. Keep an explicit visual-model
        # override so enabling diagram recognition cannot accidentally call it.
        self.model_name = (
            os.getenv("DRAWING_VLM_MODEL_NAME")
            or os.getenv("VLLM_MODEL_NAME")
            or os.getenv("MODEL_NAME")
        )
        self.temperature = float(os.getenv("DRAWING_VLM_TEMPERATURE", "1"))
        self.timeout_seconds = max(5, int(os.getenv("DRAWING_VLM_TIMEOUT_SECONDS", "30")))
        # Reasoning tokens add latency/cost but do not improve a constrained
        # image-to-JSON detector. Enable only for providers that support this
        # OpenAI-compatible request extension.
        self.disable_thinking = os.getenv("DRAWING_VLM_DISABLE_THINKING", "false").casefold() in _ENABLED_VALUES
        self.use_excel_references = os.getenv("DRAWING_VLM_USE_EXCEL_REFERENCES", "true").casefold() in _ENABLED_VALUES
        # A full 15-image catalogue plus a dense drawing tile is unnecessarily
        # large for most gateways. Users can increase this after a model probe.
        self.reference_limit = max(0, int(os.getenv("DRAWING_VLM_REFERENCE_LIMIT", "4")))
        # Contains no endpoint URL, authorization header, or prompt/image data.
        self.last_request_metadata: dict[str, object] = {}

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
        references = self._reference_content()
        content: list[dict[str, object]] = [{"type": "text", "text": self._prompt(bool(references))}]
        content.extend(references)
        content.extend([
            {"type": "text", "text": "This final image is the drawing tile to detect."},
            {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_data}"}},
        ])
        payload = {
            "model": self.model_name,
            # The configured TokenHub model rejects temperature=0 and requires
            # exactly 1. Keep an override for providers with other constraints.
            "temperature": self.temperature,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": "You detect electrical schematic symbols. Return JSON only; never invent a symbol when uncertain.",
                },
                {
                    "role": "user",
                    "content": content,
                },
            ],
        }
        if self.disable_thinking:
            payload["thinking"] = {"type": "disabled"}
        self.last_request_metadata = {
            "model": self.model_identifier,
            "tile": image_path.name,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "thinking_disabled": self.disable_thinking,
            "reference_icon_count": len(references) // 2,
            "started_at_unix_ms": round(time.time() * 1000),
        }
        started = time.perf_counter()
        try:
            request = Request(
                f"{self.base_url}/chat/completions",
                data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                method="POST",
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                provider_message = exc.read().decode("utf-8", errors="replace")
            except OSError:
                provider_message = ""
            finally:
                exc.close()
            provider_message = re.sub(r"\s+", " ", provider_message).strip()[:500]
            self.last_request_metadata.update({"duration_ms": round((time.perf_counter() - started) * 1000), "outcome": f"http_{exc.code}"})
            detail = f" 服务响应：{provider_message}" if provider_message else ""
            raise RuntimeError(f"VLM 请求失败，HTTP 状态码：{exc.code}。{detail}") from exc
        except URLError as exc:
            self.last_request_metadata.update({"duration_ms": round((time.perf_counter() - started) * 1000), "outcome": "unreachable"})
            raise RuntimeError("VLM 服务不可达。") from exc
        except TimeoutError as exc:
            self.last_request_metadata.update({"duration_ms": round((time.perf_counter() - started) * 1000), "outcome": "timeout"})
            raise RuntimeError("VLM 请求超时。") from exc

        content = body.get("choices", [{}])[0].get("message", {}).get("content", "")
        detections = self._parse(content, image_path)
        self.last_request_metadata.update({
            "duration_ms": round((time.perf_counter() - started) * 1000),
            "outcome": "ok",
            "valid_detection_count": len(detections),
        })
        return detections

    def _reference_content(self) -> list[dict[str, object]]:
        if not self.use_excel_references or self.reference_limit == 0:
            return []
        try:
            references = vlm_reference_images(max_per_type=1)[:self.reference_limit]
        except RuntimeError:
            # A reference cache failure must not block a configured VLM from
            # processing the actual drawing tile.
            return []
        content: list[dict[str, object]] = []
        for index, (component_type, image_bytes) in enumerate(references, start=1):
            encoded = base64.b64encode(image_bytes).decode("ascii")
            content.extend([
                {"type": "text", "text": f"Reference image {index} shows exactly one {component_type} symbol."},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded}"}},
            ])
        return content

    @staticmethod
    def _prompt(has_references: bool = False) -> str:
        labels = ", ".join(SUPPORTED_COMPONENT_TYPES)
        reference_instruction = (
            " The preceding labelled images are visual references only; use them to distinguish the allowed classes."
            if has_references else ""
        )
        return (
            "Find only visible electrical symbols in this image tile. Allowed types: " + labels + ". "
            + reference_instruction + " "
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