"""Detect electrical components and pixel locations from a rendered electrical region."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from recognition.vlm_detector import VlmDetection, VlmDetector


def _iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    if right <= left or bottom <= top:
        return 0.0
    intersection = (right - left) * (bottom - top)
    first_area = (first[2] - first[0]) * (first[3] - first[1])
    second_area = (second[2] - second[0]) * (second[3] - second[1])
    return intersection / max(first_area + second_area - intersection, 1.0)


def _is_duplicate(candidate: dict[str, object], existing: list[dict[str, object]], tile_overlap: int) -> bool:
    candidate_box = tuple(candidate["bbox_px"])  # type: ignore[arg-type]
    center_x, center_y = candidate["center_px"]  # type: ignore[misc]
    for prior in existing:
        if prior["component_type"] != candidate["component_type"]:
            continue
        prior_box = tuple(prior["bbox_px"])  # type: ignore[arg-type]
        prior_x, prior_y = prior["center_px"]  # type: ignore[misc]
        if _iou(candidate_box, prior_box) >= 0.45:
            return True
        if abs(center_x - prior_x) <= tile_overlap / 2 and abs(center_y - prior_y) <= tile_overlap / 2:
            return True
    return False


def _record(detection: VlmDetection, *, offset_x: int, offset_y: int, tile_name: str) -> dict[str, object]:
    xmin = round(detection.center_x - detection.width / 2 + offset_x, 2)
    ymin = round(detection.center_y - detection.height / 2 + offset_y, 2)
    xmax = round(detection.center_x + detection.width / 2 + offset_x, 2)
    ymax = round(detection.center_y + detection.height / 2 + offset_y, 2)
    return {
        "component_type": detection.label,
        "confidence": round(detection.confidence, 3),
        "bbox_px": [xmin, ymin, xmax, ymax],
        "center_px": [round((xmin + xmax) / 2, 2), round((ymin + ymax) / 2, 2)],
        "size_px": [round(xmax - xmin, 2), round(ymax - ymin, 2)],
        "source_tile": tile_name,
    }


def detect_electrical_components(
    image_path: Path,
    output_path: Path,
    *,
    tile_width: int = 1400,
    overlap: int = 180,
) -> dict[str, object]:
    """Run feature-description-guided VLM detection over overlapping image tiles."""
    if not image_path.is_file():
        raise ValueError(f"未找到电气区域图像：{image_path}")
    if tile_width <= overlap:
        raise ValueError("tile_width 必须大于 overlap。")

    from PIL import Image

    detector = VlmDetector()
    if not detector.enabled:
        raise RuntimeError("DRAWING_VLM_ENABLED 未启用，未发送 VLM 请求。")
    if not detector.configured:
        raise RuntimeError("VLM 配置不完整：需要端点、密钥和模型名。")

    with Image.open(image_path) as image:
        width, height = image.size
        horizontal_step = tile_width - overlap
        origins = list(range(0, max(1, width - tile_width + 1), horizontal_step))
        final_origin = max(0, width - tile_width)
        if origins[-1] != final_origin:
            origins.append(final_origin)
        all_components: list[dict[str, object]] = []
        tile_results: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory(prefix="electrical-vlm-") as temp_dir:
            temporary = Path(temp_dir)
            for index, origin_x in enumerate(origins, start=1):
                right = min(width, origin_x + tile_width)
                tile_path = temporary / f"tile_{index:02d}.png"
                image.crop((origin_x, 0, right, height)).save(tile_path)
                detections = detector.detect(tile_path)
                accepted = 0
                for detection in detections:
                    candidate = _record(detection, offset_x=origin_x, offset_y=0, tile_name=tile_path.name)
                    if not _is_duplicate(candidate, all_components, overlap):
                        all_components.append(candidate)
                        accepted += 1
                tile_results.append({
                    "name": tile_path.name,
                    "pixel_extent": [origin_x, 0, right, height],
                    "raw_detection_count": len(detections),
                    "accepted_detection_count": accepted,
                    "request": dict(detector.last_request_metadata),
                })

    counts = Counter(str(item["component_type"]) for item in all_components)
    result: dict[str, object] = {
        "source_image": str(image_path.resolve()),
        "image_size": [width, height],
        "model": detector.model_identifier,
        "detection_method": "VLM with component feature descriptions and overlapping image tiles",
        "tile_width": tile_width,
        "tile_overlap": overlap,
        "tile_count": len(tile_results),
        "component_count": len(all_components),
        "component_counts": [
            {"component_type": component_type, "quantity": quantity}
            for component_type, quantity in sorted(counts.items())
        ],
        "components": all_components,
        "tiles": tile_results,
        "review_required": True,
        "limitations": [
            "检测框是电气区域 PNG 像素坐标，不是 CAD 坐标。",
            "数量由重叠切片去重后的 VLM 检测框统计，必须与原始图纸人工复核。",
            "仅输出组件特征目录允许的类型；未知或低可见度符号可能遗漏。",
        ],
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="已拆分出的电气区域 PNG。")
    parser.add_argument("output", type=Path, help="保存位置和数量结果的 JSON 路径。")
    parser.add_argument("--tile-width", type=int, default=1400)
    parser.add_argument("--overlap", type=int, default=180)
    arguments = parser.parse_args()
    try:
        result = detect_electrical_components(
            arguments.image.resolve(), arguments.output.resolve(),
            tile_width=arguments.tile_width, overlap=arguments.overlap,
        )
    except (RuntimeError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "output": str(arguments.output.resolve()),
        "component_count": result["component_count"],
        "tile_count": result["tile_count"],
        "model": result["model"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
