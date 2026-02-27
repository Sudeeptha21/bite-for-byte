import time
from starlette.middleware.base import BaseHTTPMiddleware
from app.db import log_request


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start = time.time()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            latency_ms = int((time.time() - start) * 1000)
            try:
                log_request(
                    endpoint=request.url.path,
                    status_code=status_code,
                    latency_ms=latency_ms,
                    provider="local",
                    token_usage=None,
                    estimated_cost_usd=None,
                )
            except Exception:
                pass
