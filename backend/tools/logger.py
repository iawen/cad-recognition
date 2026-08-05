"""Application logger for the local drawing-recognition service.

Logs are written to the backend console and ``backend/logs``. This module has
no external configuration dependency, so API handlers and worker threads can
always report failures.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path


LOG_DIRECTORY = Path(__file__).resolve().parents[1] / "logs"
LOG_FILE = LOG_DIRECTORY / "drawing-recognition.log"
_CONSOLE_HANDLER_MARKER = "drawing_recognition_console_handler"
_FILE_HANDLER_MARKER = "drawing_recognition_file_handler"


def _configure_logger() -> logging.Logger:
    app_logger = logging.getLogger("drawing-recognition")
    app_logger.setLevel(logging.INFO)
    app_logger.propagate = False

    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] [%(threadName)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    if not any(getattr(handler, _CONSOLE_HANDLER_MARKER, False) for handler in app_logger.handlers):
        # Use stdout so CLI tools and PowerShell display operational progress.
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(formatter)
        setattr(console_handler, _CONSOLE_HANDLER_MARKER, True)
        app_logger.addHandler(console_handler)

    if not any(getattr(handler, _FILE_HANDLER_MARKER, False) for handler in app_logger.handlers):
        file_handler = TimedRotatingFileHandler(
            LOG_FILE, when="midnight", interval=1, backupCount=30, encoding="utf-8"
        )
        file_handler.setLevel(logging.INFO)
        file_handler.setFormatter(formatter)
        file_handler.suffix = "%Y-%m-%d"
        setattr(file_handler, _FILE_HANDLER_MARKER, True)
        app_logger.addHandler(file_handler)
    return app_logger


logger = _configure_logger()
