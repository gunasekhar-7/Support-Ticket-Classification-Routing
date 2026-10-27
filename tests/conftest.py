from __future__ import annotations

import pytest
import structlog


@pytest.fixture(autouse=True)
def configure_structlog() -> None:
    structlog.configure(
        processors=[
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
