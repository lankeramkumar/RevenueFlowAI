"""Request tracing, structured logs, and Prometheus-format metrics.

- Every request gets an X-Request-ID (accepted from the caller if it is a
  sane token, otherwise generated). It is bound to structlog's context, so
  every log line emitted while handling that request carries it, and it is
  echoed back in the response header.
- One access-log event per request: method, route template, status, duration.
- Metrics are kept in-process and rendered in Prometheus text format at
  /metrics. Each process exports its own; the worker has its own registry.
"""

import re
import threading
import time
import uuid
from collections import defaultdict
from typing import Any

import structlog
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "x-request-id"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,128}$")

DURATION_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class _Registry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._hist: dict[tuple[str, tuple[tuple[str, str], ...]], list[float]] = {}
        self._hist_sum: dict[tuple[str, tuple[tuple[str, str], ...]], float] = defaultdict(float)
        self._hist_count: dict[tuple[str, tuple[tuple[str, str], ...]], int] = defaultdict(int)

    @staticmethod
    def _key(name: str, labels: dict[str, str]) -> tuple[str, tuple[tuple[str, str], ...]]:
        return name, tuple(sorted(labels.items()))

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        with self._lock:
            self._counters[self._key(name, labels)] += value

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = self._key(name, labels)
        with self._lock:
            buckets = self._hist.setdefault(key, [0.0] * len(DURATION_BUCKETS))
            for i, bound in enumerate(DURATION_BUCKETS):
                if value <= bound:
                    buckets[i] += 1
            self._hist_sum[key] += value
            self._hist_count[key] += 1

    def render(self) -> str:
        def fmt(labels: tuple[tuple[str, str], ...], extra: tuple[tuple[str, str], ...] = ()) -> str:
            pairs = labels + extra
            if not pairs:
                return ""
            body = ",".join(f'{k}="{v.replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
                            for k, v in pairs)
            return "{" + body + "}"

        lines: list[str] = []
        with self._lock:
            counter_names = sorted({name for name, _ in self._counters})
            for name in counter_names:
                lines.append(f"# TYPE {name} counter")
                for (n, labels), value in sorted(self._counters.items()):
                    if n == name:
                        lines.append(f"{name}{fmt(labels)} {value:g}")
            hist_names = sorted({name for name, _ in self._hist})
            for name in hist_names:
                lines.append(f"# TYPE {name} histogram")
                for (n, labels), buckets in sorted(self._hist.items()):
                    if n != name:
                        continue
                    for bound, count in zip(DURATION_BUCKETS, buckets, strict=True):
                        lines.append(f"{name}_bucket{fmt(labels, (('le', str(bound)),))} {count:g}")
                    total = self._hist_count[(n, labels)]
                    lines.append(f"{name}_bucket{fmt(labels, (('le', '+Inf'),))} {total}")
                    lines.append(f"{name}_sum{fmt(labels)} {self._hist_sum[(n, labels)]:.6f}")
                    lines.append(f"{name}_count{fmt(labels)} {self._hist_count[(n, labels)]}")
        return "\n".join(lines) + "\n"

    def reset(self) -> None:
        with self._lock:
            self._counters.clear()
            self._hist.clear()
            self._hist_sum.clear()
            self._hist_count.clear()


registry = _Registry()


def route_template(scope: Scope) -> str:
    """The matched route's template (e.g. /api/v1/imports/{job_id}), so metric
    labels stay low-cardinality. Unmatched requests share one label.
    """
    route = scope.get("route")
    path = getattr(route, "path", None)
    return str(path) if path else "unmatched"


def configure_logging(json_output: bool = True) -> None:
    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        (structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()),
    ]
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(20),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._log = structlog.get_logger("http")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = dict(scope.get("headers", [])).get(REQUEST_ID_HEADER.encode(), b"").decode()
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex
        method = scope["method"]
        started = time.perf_counter()
        status_code = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers: list[tuple[bytes, bytes]] = list(message.get("headers", []))
                headers.append((REQUEST_ID_HEADER.encode(), request_id.encode()))
                message = {**message, "headers": headers}
            await send(message)

        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            elapsed = time.perf_counter() - started
            route = route_template(scope)
            registry.inc("http_requests_total", method=method, route=route, status=str(status_code))
            registry.observe("http_request_duration_seconds", elapsed, method=method, route=route)
            self._log.info(
                "http.request", method=method, route=route, status=status_code,
                duration_ms=round(elapsed * 1000, 2),
            )
            structlog.contextvars.clear_contextvars()

