from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from core.config import LoggingConfig


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(config: LoggingConfig) -> None:
    log_dir = Path(config.directory)
    log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, config.level.upper(), logging.INFO))
    root_logger.handlers.clear()

    plain_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    json_formatter = JsonFormatter()

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(json_formatter if config.json_console else plain_formatter)

    file_handler = RotatingFileHandler(
        filename=log_dir / config.file_name,
        maxBytes=config.max_bytes,
        backupCount=config.backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(plain_formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    logging.getLogger("discord").setLevel(logging.INFO)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
