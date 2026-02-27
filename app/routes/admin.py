from fastapi import APIRouter, Depends
from app.middleware.admin_auth import verify_admin
from app.db import fetchone

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics", dependencies=[Depends(verify_admin)])
def metrics():
    row = fetchone(
        """
        SELECT
            COUNT(*)::int AS requests,
            COALESCE(AVG(latency_ms), 0)::int AS avg_latency_ms,
            COALESCE(SUM(CASE WHEN status_code BETWEEN 200 AND 399 THEN 1 ELSE 0 END), 0)::int AS success_count,
            COALESCE(SUM(CASE WHEN status_code >= 400 THEN 1 ELSE 0 END), 0)::int AS error_count,
            COALESCE(SUM(estimated_cost_usd), 0) AS estimated_cost_usd
        FROM requests_log
        """
    )

    if not row:
        return {
            "requests": 0,
            "success_rate": 0,
            "error_rate": 0,
            "avg_latency_ms": 0,
            "estimated_cost_usd": 0,
        }

    requests, avg_latency_ms, success_count, error_count, estimated_cost_usd = row
    success_rate = round((success_count / requests) * 100, 2) if requests else 0
    error_rate = round((error_count / requests) * 100, 2) if requests else 0

    return {
        "requests": requests,
        "success_rate": success_rate,
        "error_rate": error_rate,
        "avg_latency_ms": avg_latency_ms,
        "estimated_cost_usd": float(estimated_cost_usd or 0),
    }
