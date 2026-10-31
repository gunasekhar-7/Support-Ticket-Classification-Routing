from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

_limiter: Limiter = Limiter(key_func=get_remote_address)


def get_limiter() -> Limiter:
    return _limiter


def configure_limiter(storage_uri: str | None = None) -> Limiter:
    global _limiter
    if storage_uri:
        _limiter = Limiter(key_func=get_remote_address, storage_uri=storage_uri)
    return _limiter
