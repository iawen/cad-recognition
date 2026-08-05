"""Standalone application entry point for electrical drawing recognition.

Run from the ``backend`` directory with:
``uv run python -m main``
"""

import time

import uvicorn
from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api import router
from tools.logger import logger


app = FastAPI(
    title="Electrical Drawing Recognition",
    version="0.1.0",
    description="Vector-first electrical DWG/DXF component recognition service.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_http_request(request: Request, call_next):
    """Record every request outcome so frontend failures are traceable."""
    started_at = time.perf_counter()
    client = request.client.host if request.client else "unknown"
    logger.info("HTTP request method=%s path=%s client=%s", request.method, request.url.path, client)
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("HTTP unhandled_error method=%s path=%s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "服务器内部错误，请查看后端日志。"})
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "HTTP response method=%s path=%s status=%s elapsed_ms=%.1f",
        request.method, request.url.path, response.status_code, elapsed_ms,
    )
    return response


@app.get("/api/health")
async def health():
    logger.info("Health check requested.")
    return {"status": "ok", "service": "drawing-recognition", "version": app.version}


app.include_router(router, tags=["Drawing Recognition"])


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)