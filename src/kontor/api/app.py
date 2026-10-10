from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kontor.adapters.db.uow import SqlUnitOfWork
from kontor.adapters.llm.lmstudio import LMStudioClient
from kontor.adapters.parsers.registry import default_registry
from kontor.adapters.rules.yaml_source import YamlRulesSource
from kontor.api.routers import accounts, categorization, health, imports, reports, transactions
from kontor.application.accounts import AccountService
from kontor.application.categorization import CategorizationService
from kontor.application.category_sync import sync_categories
from kontor.application.import_service import ImportService
from kontor.application.llm_step import LLMCategorizationStep
from kontor.application.reports import ReportService
from kontor.application.review import ReviewService
from kontor.application.rules_holder import RulesHolder
from kontor.config import Settings
from kontor.domain.errors import (
    AccountNotFoundError,
    DuplicateFileError,
    DuplicateIbanError,
    InvalidCategoryError,
    InvalidDateRangeError,
    MalformedFileError,
    MixedCurrenciesError,
    RulesFileError,
    TransactionNotFoundError,
    UnknownFormatError,
)
from kontor.logging import configure_logging
from kontor.ports.llm import LLMClient

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    DuplicateFileError: status.HTTP_409_CONFLICT,
    DuplicateIbanError: status.HTTP_409_CONFLICT,
    AccountNotFoundError: status.HTTP_404_NOT_FOUND,
    TransactionNotFoundError: status.HTTP_404_NOT_FOUND,
    MixedCurrenciesError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidCategoryError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidDateRangeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    UnknownFormatError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    MalformedFileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RulesFileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
}


def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_ERROR[type(exc)],
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def create_app(settings: Settings | None = None, llm_client: LLMClient | None = None) -> FastAPI:
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

    llm_step = LLMCategorizationStep(
        uow_factory,
        llm_client
        or LMStudioClient(
            settings.llm_base_url,
            settings.llm_model,
            settings.llm_timeout_seconds,
            settings.llm_api_key,
        ),
        lambda: rules.current,
        threshold=settings.llm_confidence_threshold,
        concurrency=settings.llm_concurrency,
        batch_size=settings.llm_batch_size,
    )

    app = FastAPI(title="Kontor", lifespan=lifespan)
    app.state.llm_step = llm_step
    app.state.rules = rules
    app.state.import_service = ImportService(
        uow_factory, default_registry().detect, lambda: rules.current, llm_step
    )
    app.state.account_service = AccountService(uow_factory)
    app.state.report_service = ReportService(uow_factory)
    app.state.review_service = ReviewService(uow_factory)
    app.state.categorization_service = CategorizationService(uow_factory, rules)

    for error in _STATUS_BY_ERROR:
        app.add_exception_handler(error, _handle_domain_error)
    app.include_router(health.router)
    app.include_router(imports.router)
    app.include_router(accounts.router)
    app.include_router(categorization.router)
    app.include_router(reports.router)
    app.include_router(transactions.router)
    return app
