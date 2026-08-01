"""Application logger for the local drawing-recognition service.

Logs are written to the backend console and ``backend/logs``. This module has
no external configuration dependency, so API handlers and worker threads can
always report failures.
"""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_DIRECTORY = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIRECTORY / "drawing-recognition.log"
_HANDLER_MARKER = "drawing_recognition_handler"


def _configure_logger() -> logging.Logger:
    app_logger = logging.getLogger("drawing-recognition")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False
    if any(getattr(handler, _HANDLER_MARKER, False) for handler in app_logger.handlers):
        return app_logger

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] [%(threadName)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    setattr(console_handler, _HANDLER_MARKER, True)

    file_handler = TimedRotatingFileHandler(
        LOG_FILE, when="midnight", interval=1, backupCount=30, encoding="utf-8"
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)
    file_handler.suffix = "%Y-%m-%d"
    setattr(file_handler, _HANDLER_MARKER, True)

    app_logger.addHandler(console_handler)
    app_logger.addHandler(file_handler)
    return app_logger


logger = _configure_logger()
