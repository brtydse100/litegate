"""Low-cardinality request metrics and secret-safe structured access logs."""

from __future__ import annotations

from collections import defaultdict
import json
import logging
import re
from threading import Lock
from time import perf_counter
from uuid import uuid4

from fastapi import Request

from app.version import VERSION

_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_lock = Lock()
_requests: dict[tuple[str, str, int], int] = defaultdict(int)
_duration_sum: dict[tuple[str, str], float] = defaultdict(float)
_duration_count: dict[tuple[str, str], int] = defaultdict(int)
_logger = logging.getLogger("litegate.request")


def request_id(value: str | None) -> str:
    """Accept a bounded trace ID or replace it with an unguessable local ID."""
    candidate = (value or "").strip()
    return candidate if _REQUEST_ID.fullmatch(candidate) else uuid4().hex


def route_path(request: Request) -> str:
    """Use the route template so user-controlled IDs never become metric labels."""
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if not isinstance(path, str):
        return "unmatched"
    # Included FastAPI routers expose their local path in the request scope.
    # Restore the public /api prefix without falling back to concrete user IDs.
    if request.url.path.startswith("/api/") and not path.startswith("/api/"):
        return f"/api{path}"
    return path


def record_request(method: str, path: str, status: int, duration: float) -> None:
    with _lock:
        _requests[(method, path, status)] += 1
        _duration_sum[(method, path)] += duration
        _duration_count[(method, path)] += 1


def log_request(*, request_id_value: str, method: str, path: str, status: int, duration: float, client: str) -> None:
    # Headers, query strings, bodies, and credentials are intentionally absent.
    _logger.info(
        json.dumps(
            {
                "event": "http_request",
                "request_id": request_id_value,
                "method": method,
                "path": path,
                "status": status,
                "duration_ms": round(duration * 1000, 2),
                "client": client,
            },
            separators=(",", ":"),
        )
    )


def observe(request: Request, status: int, started: float, request_id_value: str) -> None:
    duration = max(0.0, perf_counter() - started)
    method = request.method.upper()
    path = route_path(request)
    record_request(method, path, status, duration)
    client = request.client.host if request.client else "unknown"
    log_request(
        request_id_value=request_id_value,
        method=method,
        path=path,
        status=status,
        duration=duration,
        client=client,
    )


def _labels(method: str, path: str, status: int | None = None) -> str:
    values = [f'method="{method}"', f'path="{path}"']
    if status is not None:
        values.append(f'status="{status}"')
    return "{" + ",".join(values) + "}"


def render_metrics() -> str:
    with _lock:
        requests = dict(_requests)
        duration_sum = dict(_duration_sum)
        duration_count = dict(_duration_count)

    lines = [
        "# HELP litegate_info LiteGate build information.",
        "# TYPE litegate_info gauge",
        f'litegate_info{{version="{VERSION}"}} 1',
        "# HELP litegate_http_requests_total Completed HTTP requests.",
        "# TYPE litegate_http_requests_total counter",
    ]
    for (method, path, status), count in sorted(requests.items()):
        lines.append(f"litegate_http_requests_total{_labels(method, path, status)} {count}")
    lines.extend(
        [
            "# HELP litegate_http_request_duration_seconds Request duration by route.",
            "# TYPE litegate_http_request_duration_seconds summary",
        ]
    )
    for method, path in sorted(duration_count):
        labels = _labels(method, path)
        lines.append(
            f"litegate_http_request_duration_seconds_sum{labels} "
            f"{duration_sum[(method, path)]:.6f}"
        )
        lines.append(
            f"litegate_http_request_duration_seconds_count{labels} "
            f"{duration_count[(method, path)]}"
        )
    return "\n".join(lines) + "\n"
