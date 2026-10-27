from __future__ import annotations

from prometheus_client import Counter, Histogram

# Module-level singletons to avoid duplicate registration
_CLASSIFICATION_REQUESTS: Counter | None = None
_CLASSIFICATION_LATENCY: Histogram | None = None
_CLASSIFICATION_CONFIDENCE: Histogram | None = None

_CLASSIFICATION_V2_REQUESTS: Counter | None = None
_CLASSIFICATION_V2_LATENCY: Histogram | None = None
_CLASSIFICATION_V2_CONFIDENCE: Histogram | None = None


def _get_classification_requests() -> Counter:
    global _CLASSIFICATION_REQUESTS
    if _CLASSIFICATION_REQUESTS is None:
        _CLASSIFICATION_REQUESTS = Counter(
            "ticket_classification_requests_total",
            "Total classification requests",
            ["endpoint", "status"],
        )
    return _CLASSIFICATION_REQUESTS


def _get_classification_latency() -> Histogram:
    global _CLASSIFICATION_LATENCY
    if _CLASSIFICATION_LATENCY is None:
        _CLASSIFICATION_LATENCY = Histogram(
            "ticket_classification_latency_seconds",
            "Classification latency in seconds",
            ["endpoint"],
        )
    return _CLASSIFICATION_LATENCY


def _get_classification_confidence() -> Histogram:
    global _CLASSIFICATION_CONFIDENCE
    if _CLASSIFICATION_CONFIDENCE is None:
        _CLASSIFICATION_CONFIDENCE = Histogram(
            "ticket_classification_confidence",
            "Classification confidence scores",
            ["category"],
        )
    return _CLASSIFICATION_CONFIDENCE


def _get_classification_v2_requests() -> Counter:
    global _CLASSIFICATION_V2_REQUESTS
    if _CLASSIFICATION_V2_REQUESTS is None:
        _CLASSIFICATION_V2_REQUESTS = Counter(
            "ticket_classification_v2_requests_total",
            "Total classification requests (v2)",
            ["endpoint", "status"],
        )
    return _CLASSIFICATION_V2_REQUESTS


def _get_classification_v2_latency() -> Histogram:
    global _CLASSIFICATION_V2_LATENCY
    if _CLASSIFICATION_V2_LATENCY is None:
        _CLASSIFICATION_V2_LATENCY = Histogram(
            "ticket_classification_v2_latency_seconds",
            "Classification latency in seconds (v2)",
            ["endpoint"],
        )
    return _CLASSIFICATION_V2_LATENCY


def _get_classification_v2_confidence() -> Histogram:
    global _CLASSIFICATION_V2_CONFIDENCE
    if _CLASSIFICATION_V2_CONFIDENCE is None:
        _CLASSIFICATION_V2_CONFIDENCE = Histogram(
            "ticket_classification_v2_confidence",
            "Classification confidence scores (v2)",
            ["category"],
        )
    return _CLASSIFICATION_V2_CONFIDENCE


# Public accessors
CLASSIFICATION_REQUESTS = _get_classification_requests()
CLASSIFICATION_LATENCY = _get_classification_latency()
CLASSIFICATION_CONFIDENCE = _get_classification_confidence()

CLASSIFICATION_V2_REQUESTS = _get_classification_v2_requests()
CLASSIFICATION_V2_LATENCY = _get_classification_v2_latency()
CLASSIFICATION_V2_CONFIDENCE = _get_classification_v2_confidence()
