from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kontor.adapters.db.uow import SqlUnitOfWork
from kontor.adapters.parsers.registry import default_registry
from kontor.adapters.rules.yaml_source import YamlRulesSource
from kontor.api.routers import accounts, health, imports
from kontor.application.accounts import AccountService
from kontor.application.category_sync import sync_categories
from kontor.application.import_service import ImportService
from kontor.application.rules_holder import RulesHolder
from kontor.config import Settings
from kontor.domain.errors import (
    AccountNotFoundError,
    DuplicateFileError,
    DuplicateIbanError,
    MalformedFileError,
    UnknownFormatError,
)
from kontor.logging import configure_logging

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    DuplicateFileError: status.HTTP_409_CONFLICT,
    DuplicateIbanError: status.HTTP_409_CONFLICT,
    AccountNotFoundError: status.HTTP_404_NOT_FOUND,
    UnknownFormatError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    MalformedFileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_ERROR[type(exc)],
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings)
    rules = RulesHolder(YamlRulesSource(Path(settings.rules_path)))

    # The engine connects lazily, so the app starts without a reachable database.
    session_factory = sessionmaker(create_engine(settings.database_url))

    def uow_factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Fail fast: without a valid rules file there is no category tree to sync.
        sync_categories(uow_factory, rules.load().categories)
        yield

    app = FastAPI(title="Kontor", lifespan=lifespan)
    app.state.rules = rules
    app.state.import_service = ImportService(uow_factory, default_registry().detect)
    app.state.account_service = AccountService(uow_factory)

    for error in _STATUS_BY_ERROR:
        app.add_exception_handler(error, _handle_domain_error)
    app.include_router(health.router)
    app.include_router(imports.router)
    app.include_router(accounts.router)
    return app
