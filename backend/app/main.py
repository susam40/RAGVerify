from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from app.api.v1 import api_router
from app.api.v1.health import router as health_router
from app.core.config import get_settings
from app.core.logging import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    app.state.settings = settings
    logger.info("app_started", service=settings.app_name, env=settings.app_env)
    yield
    logger.info("app_stopped", service=settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)
    app.include_router(health_router)
    app.include_router(api_router)
    return app


app = create_app()
