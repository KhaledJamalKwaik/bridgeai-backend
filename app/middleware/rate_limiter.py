from typing import Dict
import time
import asyncio

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings


class RateLimitRecord:
    __slots__ = ("tokens", "last_refill")

    def __init__(self, tokens: float, last_refill: float):
        self.tokens = tokens
        self.last_refill = last_refill


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory token-bucket rate limiter per client IP.

    Note: This is process-local and not suitable for multi-process/multi-host production.
    For production use, replace with a Redis-backed limiter (e.g. `slowapi` or `redis-rate-limit`).
    """

    def __init__(self, app):
        super().__init__(app)
        self._records: Dict[str, RateLimitRecord] = {}
        self._lock = asyncio.Lock()
        self._capacity = float(settings.RATE_LIMIT_REQUESTS)
        self._period = float(settings.RATE_LIMIT_PERIOD)
        # refill rate: tokens per second
        self._rate = self._capacity / self._period if self._period > 0 else self._capacity

    async def dispatch(self, request: Request, call_next):
        client = request.client
        if client is None:
            # fallback for unknown client
            key = "unknown"
        else:
            key = client.host

        now = time.time()

        async with self._lock:
            rec = self._records.get(key)
            if rec is None:
                rec = RateLimitRecord(tokens=self._capacity - 1.0, last_refill=now)
                self._records[key] = rec
                allowed = True
            else:
                # refill
                elapsed = now - rec.last_refill
                refill = elapsed * self._rate
                if refill > 0:
                    rec.tokens = min(self._capacity, rec.tokens + refill)
                    rec.last_refill = now

                if rec.tokens >= 1.0:
                    rec.tokens -= 1.0
                    allowed = True
                else:
                    allowed = False

        if not allowed:
            retry_after = max(1, int((1.0 - rec.tokens) / self._rate)) if self._rate > 0 else 1
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded",
                    "retry_after_seconds": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
