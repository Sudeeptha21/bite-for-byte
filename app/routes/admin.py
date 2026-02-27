from fastapi import APIRouter, Depends
from app.middleware.admin_auth import verify_admin

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/metrics", dependencies=[Depends(verify_admin)])
def metrics():
    return {
        "requests": 0,
        "success_rate": 0,
        "error_rate": 0,
        "avg_latency_ms": 0,
        "estimated_cost_usd": 0,
    }
