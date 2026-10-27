from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

# Module-level limiter instance (initialized in main.py lifespan)
limiter: Limiter | None = None


def get_limiter() -> Limiter:
    if limiter is None:
        # Fallback for testing or early access
        return Limiter(key_func=get_remote_address)
    return limiter
