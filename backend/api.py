"""FastAPI routes for the vector-first electrical drawing recognition baseline."""

from __future__ import annotations

import asyncio
import json
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from domain.errors import DrawingAnalysisError
from domain.models import CadPoint
from evaluation.audit import audit_drawings
from evaluation.coordinate_validation import validate_coordinate_round_trip
from ingest.file_validation import SUPPORTED_EXTENSIONS
from ingest.dwg_converter import use_realdwg
from recognition.component_catalog import CATALOG_SOURCE, catalog_capabilities
from recognition.reference_icons import reference_icon_summary
from runtime.repository import RENDER_ROOT, UPLOAD_ROOT, create_run, get_run, get_run_path, list_events
from runtime.worker import submit_analysis
from service import analyze_drawing, render_dxf_base_maps
from tools.logger import logger


router = APIRouter()
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
# The checked-in DXF was manually converted from the companion DWG. Keeping the
# sample on the DXF path lets P0/P1 validation run without local ODA installation.
SAMPLE_DRAWING = Path(__file__).resolve().parent.parent / "data" / "B电气图.dxf"

_COMPONENT_COLORS = {
    "circuit_breaker": "#E74C3C", "current_transformer": "#3498DB",
    "voltage_transformer": "#3F51B5", "surge_arrester": "#E67E22",
    "fuse": "#F1C40F", "zero_sequence_current_transformer": "#795548",
    "live_line_indicator": "#1ABC9C", "earthing_switch": "#9B59B6",
    "ammeter": "#2ECC71", "voltmeter": "#3498DB", "thermal_relay": "#E91E63",
    "contactor": "#8C8C8C", "capacitor": "#2ECC71",
    "three_phase_shunt_capacitor_bank": "#27AE60", "transformer": "#5D6D7E",
}


class FeasibilityLogin(BaseModel):
    username: str
    password: str


def _response(data: object, message: str = "ok") -> dict[str, object]:
    """Use the response envelope consumed by the confirmed frontend."""
    return {"code": 0, "message": message, "data": data}


def _frontend_status(status: str) -> str:
    return {"queued": "pending", "running": "processing", "succeeded": "completed", "failed": "failed"}.get(status, "pending")


def _ensure_run_render(run: dict) -> Path | None:
    """Render a historical completed task on first result-page request if needed."""
    render_path = RENDER_ROOT / f"{run['id']}.png"
    if render_path.is_file():
        return render_path
    if run["status"] != "succeeded":
        return None
    source_path = get_run_path(run["id"])
    if source_path is None or not source_path.is_file():
        logger.warning("Cannot render completed task: upload missing run_id=%s", run["id"])
        return None
    try:
        logger.info("Rendering historical task background run_id=%s source=%s", run["id"], source_path)
        RENDER_ROOT.mkdir(parents=True, exist_ok=True)
        analyze_drawing(source_path, render_output_path=render_path)
    except Exception:
        logger.exception("Historical task background rendering failed run_id=%s", run["id"])
        return None
    return render_path if render_path.is_file() else None


def _ensure_base_images(run: dict) -> list[dict]:
    """Create frame-specific PNGs for completed legacy tasks when first viewed."""
    drawing = (run.get("result") or {}).get("drawing", {})
    base_images = drawing.get("base_images", [])
    render_dir = RENDER_ROOT / run["id"]
    if base_images and all((render_dir / item["filename"]).is_file() for item in base_images):
        return base_images
    if run["status"] != "succeeded":
        return []
    source_path = get_run_path(run["id"])
    if source_path is None or not source_path.is_file():
        return []
    try:
        return render_dxf_base_maps(source_path, render_dir)
    except Exception:
        logger.exception("Task base-map rendering failed run_id=%s", run["id"])
        return []


def _render_dimensions(render_path: Path | None) -> tuple[int, int]:
    """Read the rendered PNG dimensions for clients that project annotations."""
    if render_path is None:
        return 0, 0
    try:
        from PIL import Image

        with Image.open(render_path) as image:
            return image.size
    except OSError:
        logger.warning("Cannot read rendered image dimensions path=%s", render_path)
        return 0, 0


def _frontend_task(run: dict) -> dict[str, object]:
    completed_at = run["updated_at"] if run["status"] in {"succeeded", "failed"} else None
    size = get_run_path(run["id"])
    has_persisted_base_images = bool((run.get("result") or {}).get("drawing", {}).get("base_images"))
    base_images = _ensure_base_images(run)
    # Older completed tasks only recorded the legacy whole-drawing PNG. Keep it
    # available while adding regional images lazily; new tasks use region maps.
    render_path = _ensure_run_render(run) if not has_persisted_base_images else None
    image_width, image_height = _render_dimensions(render_path)
    limitations = (run.get("result") or {}).get("audit", {}).get("limitations", [])
    visual_warning = next(
        (item for item in limitations if item.startswith(("视觉识别未执行：", "VLM 文字提取未执行："))),
        None,
    )
    return {
        "taskId": run["id"],
        "fileName": run["filename"],
        "fileSize": size.stat().st_size if size and size.is_file() else 0,
        "status": _frontend_status(run["status"]),
        "progress": run["progress"],
        "createdAt": run["created_at"],
        "completedAt": completed_at,
        "error": run.get("error") if run["status"] == "failed" else None,
        "warning": visual_warning,
        "imageUrl": f"/api/recognition/{run['id']}/drawing" if render_path else "",
        "imageWidth": image_width,
        "imageHeight": image_height,
        "baseImages": [{
            "index": item["index"], "name": item["name"],
            "imageUrl": f"/api/recognition/{run['id']}/drawing/{item['filename']}",
            "imageWidth": item["image_width"], "imageHeight": item["image_height"],
            "cadExtent": item["cad_extent"],
        } for item in base_images],
        "sheets": ([{"index": item["index"], "name": item["name"]} for item in base_images]
                   or [{"index": 0, "name": "模型空间"}]),
    }


def _base_image_for_point(base_images: list[dict], point: dict[str, float]) -> dict | None:
    """Return the persisted drawing frame that contains a CAD point."""
    for image in base_images:
        min_x, min_y, max_x, max_y = image["cad_extent"]
        if min_x <= point["x"] <= max_x and min_y <= point["y"] <= max_y:
            return image
    return None


def _base_image_for_record(base_images: list[dict], record: dict, point: dict[str, float]) -> dict | None:
    """Prefer persisted frame membership; retain coordinate fallback for legacy tasks."""
    frame_index = record.get("frame_index")
    if isinstance(frame_index, int):
        return next((image for image in base_images if image["index"] == frame_index), None)
    return _base_image_for_point(base_images, point)


def _normalized_boxes(result: dict) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    """Project CAD centers into their frame-specific normalized UI boxes."""
    points = [component["cad_center"] for component in result.get("components", [])]
    points.extend(text["cad_position"] for text in result.get("texts", []) if text.get("cad_position"))
    if not points:
        return {}, {}
    min_x, max_x = min(point["x"] for point in points), max(point["x"] for point in points)
    min_y, max_y = min(point["y"] for point in points), max(point["y"] for point in points)
    base_images = result.get("drawing", {}).get("base_images", [])

    def box(record: dict, point: dict[str, float], width: float, height: float) -> dict[str, float]:
        frame = _base_image_for_record(base_images, record, point)
        if frame is not None:
            frame_min_x, frame_min_y, frame_max_x, frame_max_y = frame["cad_extent"]
        else:
            frame_min_x, frame_min_y, frame_max_x, frame_max_y = min_x, min_y, max_x, max_y
        span_x, span_y = max(frame_max_x - frame_min_x, 1.0), max(frame_max_y - frame_min_y, 1.0)
        x = min(max((point["x"] - frame_min_x) / span_x - width / 2, 0.0), 1.0 - width)
        # DXF Y grows upward whereas the canvas Y grows downward.
        y = min(max((frame_max_y - point["y"]) / span_y - height / 2, 0.0), 1.0 - height)
        return {"x": round(x, 6), "y": round(y, 6), "width": width, "height": height}

    component_boxes = {component["id"]: box(component, component["cad_center"], 0.035, 0.035) for component in result.get("components", [])}
    text_boxes = {
        text["id"]: box(text, text["cad_position"], min(0.35, max(0.06, len(text["content"]) * 0.006)), 0.024)
        for text in result.get("texts", []) if text.get("cad_position")
    }
    return component_boxes, text_boxes


def _completed_result(run_id: str) -> dict:
    run = get_run(run_id)
    if run is None:
        logger.warning("Completed result unavailable: run not found run_id=%s", run_id)
        raise HTTPException(404, "识别任务不存在。")
    if run["status"] != "succeeded" or run["result"] is None:
        logger.warning(
            "Completed result unavailable run_id=%s status=%s phase=%s error=%s",
            run_id, run["status"], run["phase"], run.get("error") or "",
        )
        raise HTTPException(409, "识别任务尚未完成。")
    logger.info("Completed result loaded run_id=%s", run_id)
    return run["result"]


@router.post("/api/auth/login")
async def login_for_feasibility(payload: FeasibilityLogin):
    """Provide a local UI gate only; this feasibility service has no user system."""
    username = payload.username.strip()
    if not username or not payload.password:
        raise HTTPException(400, "用户名和密码不能为空。")
    return _response({"token": "local-feasibility-token", "user": {"username": username}})


def _raise_analysis_error(exc: DrawingAnalysisError) -> None:
    message = str(exc)
    status_code = 503 if "ODA File Converter" in message else 422
    raise HTTPException(status_code=status_code, detail=message) from exc


@router.get("/api/drawing-recognition/capabilities")
async def get_drawing_recognition_capabilities():
    """Describe the current P1 baseline so consumers do not infer unsupported features."""
    return {
        "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        "dwg_parser": "realdwg_sidecar" if use_realdwg() else "oda_file_converter",
        "implemented": ["p0_batch_audit", "dxf_audit", "block_component_recognition", "native_text_extraction", "text_component_linking", "persistent_runs", "sse_progress"],
        "optional": ["frame_base_map_rendering", "overlapping_tiling", "frame_vlm_component_detection_when_enabled", "frame_vlm_text_extraction_when_enabled", "obb_detection_when_model_configured"],
        "not_implemented": ["paddleocr", "wire_tracing", "netlist", "human_review_workspace"],
        "component_catalog_source": CATALOG_SOURCE,
        "supported_components": catalog_capabilities(),
        "excel_reference_icons": reference_icon_summary(),
        "sample_available": SAMPLE_DRAWING.is_file(),
    }


@router.post("/api/drawing-recognition/analyze")
async def analyze_uploaded_drawing(file: UploadFile = File(...)):
    """Analyze an uploaded DXF or DWG without retaining the input after completion."""
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, "仅支持上传 .dwg 或 .dxf 文件。")

    with tempfile.TemporaryDirectory(prefix="drawing-upload-") as temp_dir:
        target = Path(temp_dir) / f"upload{suffix}"
        size = 0
        try:
            with target.open("wb") as destination:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(413, "图纸超过 100 MB 上传限制。")
                    destination.write(chunk)
        finally:
            await file.close()

        try:
            result = analyze_drawing(target).model_dump()
        except DrawingAnalysisError as exc:
            _raise_analysis_error(exc)
        result["drawing"]["filename"] = original_name
        result["drawing"]["size_bytes"] = size
        return result


@router.post("/api/upload")
async def upload_for_frontend(file: UploadFile = File(...)):
    """Create the asynchronous task consumed by the confirmed upload page."""
    logger.info("Frontend upload received filename=%s", file.filename)
    response = await create_recognition_run(file)
    logger.info("Frontend upload accepted run_id=%s", response["run_id"])
    return _response({"taskId": response["run_id"]})


@router.get("/api/recognition/{task_id}")
async def get_frontend_task(task_id: str):
    logger.info("Frontend task requested run_id=%s", task_id)
    run = get_run(task_id)
    if run is None:
        logger.warning("Frontend task not found run_id=%s", task_id)
        raise HTTPException(404, "识别任务不存在。")
    logger.info("Frontend task returned run_id=%s status=%s phase=%s", task_id, run["status"], run["phase"])
    return _response(_frontend_task(run))


@router.get("/api/recognition/{task_id}/drawing")
async def get_frontend_drawing(task_id: str):
    """Serve the PNG rendered from the current uploaded drawing."""
    run = get_run(task_id)
    if run is None:
        logger.warning("Frontend drawing not found: run not found run_id=%s", task_id)
        raise HTTPException(404, "识别任务不存在。")
    render_path = RENDER_ROOT / f"{task_id}.png"
    if not render_path.is_file():
        logger.warning("Frontend drawing unavailable run_id=%s status=%s", task_id, run["status"])
        raise HTTPException(404, "当前任务尚未生成图纸底图。")
    logger.info("Frontend drawing returned run_id=%s path=%s", task_id, render_path)
    return FileResponse(render_path, media_type="image/png", filename=f"{task_id}.png")


@router.get("/api/recognition/{task_id}/drawing/{image_name}")
async def get_frontend_base_map(task_id: str, image_name: str):
    """Serve a persisted high-resolution drawing-frame base map."""
    if get_run(task_id) is None:
        raise HTTPException(404, "识别任务不存在。")
    if Path(image_name).name != image_name or not image_name.endswith(".png"):
        raise HTTPException(404, "图纸底图不存在。")
    image_path = RENDER_ROOT / task_id / image_name
    if not image_path.is_file():
        raise HTTPException(404, "当前任务尚未生成图框底图。")
    return FileResponse(image_path, media_type="image/png", filename=image_name)


@router.get("/api/recognition/{task_id}/symbols")
async def get_frontend_symbols(task_id: str):
    logger.info("Frontend symbols requested run_id=%s", task_id)
    result = _completed_result(task_id)
    component_boxes, _ = _normalized_boxes(result)
    base_images = result.get("drawing", {}).get("base_images", [])
    symbols = []
    for component in result.get("components", []):
        attributes = [{"key": key, "value": value} for key, value in component["evidence"].get("attributes", {}).items()]
        if component.get("value"):
            attributes.append({"key": "参数", "value": component["value"]})
        catalog_name = component["evidence"].get("catalog_name")
        catalog_category = component["evidence"].get("catalog_category")
        name = component.get("reference") or catalog_name or component["type"]
        symbols.append({
            "id": component["id"], "name": name, "model": component.get("value"),
            "category": catalog_category or component["type"], "quantity": 1, "attributes": attributes,
            "position": {"x": component["cad_center"]["x"], "y": component["cad_center"]["y"], "sheet": f"页{(_base_image_for_record(base_images, component, component['cad_center']) or {'index': 0})['index'] + 1}"},
            "confidence": component["confidence"], "boundingBox": component_boxes.get(component["id"], {"x": 0, "y": 0, "width": 0.035, "height": 0.035}),
            "color": _COMPONENT_COLORS.get(component["type"], "#8C8C8C"),
        })
    logger.info("Frontend symbols returned run_id=%s count=%s", task_id, len(symbols))
    return _response(symbols)


@router.get("/api/recognition/{task_id}/tables")
async def get_frontend_tables(task_id: str):
    logger.info("Frontend tables requested run_id=%s", task_id)
    _completed_result(task_id)
    # BOM/table extraction is intentionally outside this feasibility-validation scope.
    return _response([])


@router.get("/api/recognition/{task_id}/texts")
async def get_frontend_texts(task_id: str):
    logger.info("Frontend texts requested run_id=%s", task_id)
    result = _completed_result(task_id)
    _, text_boxes = _normalized_boxes(result)
    base_images = result.get("drawing", {}).get("base_images", [])
    texts = []
    for text in result.get("texts", []):
        if text.get("cad_position") is None:
            continue
        content = text["content"]
        text_type = "title" if len(content) < 80 and ("图" in content or "TITLE" in text["layer"].upper()) else "label"
        texts.append({
            "id": text["id"], "content": content, "type": text_type, "layer": text["layer"],
            "source": text.get("source", "dxf"), "confidence": text.get("confidence", 1.0),
            "componentId": text.get("component_id"), "componentType": text.get("component_type"),
            "position": {"x": text["cad_position"]["x"], "y": text["cad_position"]["y"], "sheet": f"页{(_base_image_for_record(base_images, text, text['cad_position']) or {'index': 0})['index'] + 1}"},
            "boundingBox": text_boxes.get(text["id"], {"x": 0, "y": 0, "width": 0.06, "height": 0.024}),
        })
    logger.info("Frontend texts returned run_id=%s count=%s", task_id, len(texts))
    return _response(texts)


@router.post("/api/drawing-recognition/runs")
async def create_recognition_run(file: UploadFile = File(...)):
    """Persist an upload and submit it to the local P1 worker queue."""
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    if not original_name or suffix not in SUPPORTED_EXTENSIONS:
        logger.warning("Run creation rejected filename=%s suffix=%s", original_name, suffix)
        raise HTTPException(400, "仅支持上传 .dwg 或 .dxf 文件。")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    stored_path = UPLOAD_ROOT / f"{uuid.uuid4().hex}{suffix}"
    size = 0
    try:
        with stored_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    stored_path.unlink(missing_ok=True)
                    raise HTTPException(413, "图纸超过 100 MB 上传限制。")
                destination.write(chunk)
    finally:
        await file.close()
    run = create_run(original_name, stored_path)
    submit_analysis(run["id"], stored_path)
    logger.info("Run creation accepted run_id=%s filename=%s size_bytes=%s", run["id"], original_name, size)
    return {"run_id": run["id"], "status": run["status"], "size_bytes": size}


@router.get("/api/drawing-recognition/runs/{run_id}")
async def get_recognition_run(run_id: str):
    run = get_run(run_id)
    if run is None:
        raise HTTPException(404, "识别任务不存在。")
    return run


@router.get("/api/drawing-recognition/runs/{run_id}/events")
async def get_recognition_events(run_id: str):
    if get_run(run_id) is None:
        raise HTTPException(404, "识别任务不存在。")
    return {"run_id": run_id, "events": list_events(run_id)}


@router.get("/api/drawing-recognition/runs/{run_id}/stream")
async def stream_recognition_run(run_id: str):
    if get_run(run_id) is None:
        raise HTTPException(404, "识别任务不存在。")

    async def generate():
        last_event_count = -1
        while True:
            run = get_run(run_id)
            events = list_events(run_id)
            if len(events) != last_event_count:
                yield f"data: {json.dumps({'run': run, 'events': events}, ensure_ascii=False)}\n\n"
                last_event_count = len(events)
            if run and run["status"] in {"succeeded", "failed"}:
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(generate(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


@router.post("/api/drawing-recognition/audit-sample")
async def audit_repository_sample():
    """Run the P0 audit report against the checked-in validation drawing."""
    return audit_drawings([SAMPLE_DRAWING]).model_dump()


@router.get("/api/drawing-recognition/validation/coordinates")
async def validate_coordinates():
    """Expose a deterministic P0 CAD/pixel round-trip validation report."""
    return validate_coordinate_round_trip(
        CadPoint(x=0, y=0), CadPoint(x=100, y=50), 2000, 1000,
        [CadPoint(x=0, y=0), CadPoint(x=100, y=50), CadPoint(x=50, y=25), CadPoint(x=20, y=40)],
    )


@router.post("/api/drawing-recognition/analyze-sample")
async def analyze_repository_sample():
    """Analyze the checked-in manually converted B电气图.dxf sample."""
    try:
        return analyze_drawing(SAMPLE_DRAWING).model_dump()
    except DrawingAnalysisError as exc:
        _raise_analysis_error(exc)