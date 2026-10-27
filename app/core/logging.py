from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog
from pythonjsonlogger import jsonlogger

from app.core.config import get_settings


class PIIRedactingFormatter(jsonlogger.JsonFormatter):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        settings = get_settings()
        self.patterns = [
            (re.compile(pattern), "[REDACTED]")
            for pattern in settings.pii_patterns
        ]

    def add_fields(self, log_record: dict[str, Any], record: logging.LogRecord, message_dict: dict[str, Any]) -> None:
        super().add_fields(log_record, record, message_dict)
        if "message" in log_record:
            log_record["message"] = self._redact(str(log_record["message"]))
        for key, value in log_record.items():
            if isinstance(value, str):
                log_record[key] = self._redact(value)

    def _redact(self, text: str) -> str:
        for pattern, replacement in self.patterns:
            text = pattern.sub(replacement, text)
        return text


def setup_logging() -> None:
    settings = get_settings()

    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)
    pre_chain = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        timestamper,
        structlog.processors.format_exc_info,
    ]

    if settings.log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())

    if settings.pii_redaction_enabled:
        formatter = PIIRedactingFormatter(
            "%(timestamp)s %(level)s %(logger)s %(message)s",
            rename_fields={"level": "severity", "logger": "component"},
        )
    else:
        formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(level)s %(logger)s %(message)s",
            rename_fields={"level": "severity", "logger": "component"},
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *pre_chain,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
