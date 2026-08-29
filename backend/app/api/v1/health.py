from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import select

from app.core.opensearch import ping_opensearch
from app.models import Document, IngestionJob

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "service": request.app.state.settings.app_name,
    }


@router.get("/ready")
async def ready(request: Request) -> JSONResponse:
    settings = request.app.state.settings
    checks: dict[str, str] = {}

    try:
        async with request.app.state.session_factory() as session:
            await session.execute(select(Document.id).limit(1))
            await session.execute(select(IngestionJob.id).limit(1))
        checks["postgres"] = "ok"
    except Exception as exc:
        checks["postgres"] = f"error: {exc}"

    checks["opensearch"] = "ok" if await ping_opensearch(settings) else "error: unreachable"

    ready_ok = all(value == "ok" for value in checks.values())
    payload = {
        "status": "ok" if ready_ok else "degraded",
        "checks": checks,
        "index": settings.opensearch_index,
    }
    return JSONResponse(status_code=200 if ready_ok else 503, content=payload)
