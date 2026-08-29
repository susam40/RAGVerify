from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from sqlalchemy import text

from app.api.v1 import api_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.db import create_engine, create_session_factory
from app.core.logging import configure_logging
from app.core.opensearch import ensure_index
from app.models import Base

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)

    engine = create_engine(settings)
    session_factory = create_session_factory(engine)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("SELECT 1"))

    await ensure_index(settings)

    app.state.settings = settings
    app.state.engine = engine
    app.state.session_factory = session_factory

    logger.info(
        "app_started",
        service=settings.app_name,
        env=settings.app_env,
        index=settings.opensearch_index,
    )
    yield

    await engine.dispose()
    logger.info("app_stopped", service=settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
