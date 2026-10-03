from fastapi import FastAPI

from kontor.api.routers import health
from kontor.config import Settings
from kontor.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings)
    app = FastAPI(title="Kontor")
    app.include_router(health.router)
    return app
