from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

from app.core.config import get_settings


def create_pii_processor(patterns: list[str]) -> Any:
    compiled = [(re.compile(p), "[REDACTED]") for p in patterns]

    def redact_val(val: Any) -> Any:
        if isinstance(val, str):
            for pat, repl in compiled:
                val = pat.sub(repl, val)
        elif isinstance(val, dict):
            return {k: redact_val(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [redact_val(v) for v in val]
        return val

    def pii_processor(logger: Any, method_name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        return {k: redact_val(v) for k, v in event_dict.items()}

    return pii_processor


def setup_logging() -> None:
    settings = get_settings()

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True, key="timestamp"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if settings.pii_redaction_enabled:
        processors.append(create_pii_processor(settings.pii_patterns))

    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty()))

    logging.basicConfig(
        level=settings.log_level, stream=sys.stdout, format="%(message)s", force=True
    )

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
