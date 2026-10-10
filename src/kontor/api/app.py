from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path

import structlog
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from kontor.adapters.db.query_executor import PostgresQueryExecutor
from kontor.adapters.db.schema_introspector import PostgresSchemaIntrospector
from kontor.adapters.db.uow import SqlUnitOfWork
from kontor.adapters.llm.lmstudio import LMStudioClient
from kontor.adapters.llm.lmstudio_agent import LMStudioAgentLLM
from kontor.adapters.parsers.registry import default_registry
from kontor.adapters.rules.yaml_source import YamlRulesSource
from kontor.api.routers import (
    accounts,
    agent,
    categorization,
    health,
    imports,
    reports,
    transactions,
)
from kontor.application.accounts import AccountService
from kontor.application.agent import AgentService
from kontor.application.agent_context import load_notes
from kontor.application.agent_conversations import ConversationStore
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
    ConversationNotFoundError,
    DuplicateFileError,
    DuplicateIbanError,
    InvalidCategoryError,
    InvalidDateRangeError,
    LLMTimeoutError,
    LLMUnavailableError,
    MalformedFileError,
    MixedCurrenciesError,
    RulesFileError,
    TransactionNotFoundError,
    UnknownFormatError,
)
from kontor.logging import configure_logging
from kontor.ports.agent_llm import AgentLLM
from kontor.ports.llm import LLMClient

log = structlog.get_logger()

_STATUS_BY_ERROR: dict[type[Exception], int] = {
    DuplicateFileError: status.HTTP_409_CONFLICT,
    DuplicateIbanError: status.HTTP_409_CONFLICT,
    AccountNotFoundError: status.HTTP_404_NOT_FOUND,
    TransactionNotFoundError: status.HTTP_404_NOT_FOUND,
    ConversationNotFoundError: status.HTTP_404_NOT_FOUND,
    MixedCurrenciesError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidCategoryError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    InvalidDateRangeError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    UnknownFormatError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    MalformedFileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    RulesFileError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    # Only the agent lets these reach the API; the categorizer handles them itself.
    LLMUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMTimeoutError: status.HTTP_503_SERVICE_UNAVAILABLE,
}


def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS_BY_ERROR[type(exc)],
        content={"error": type(exc).__name__, "detail": str(exc)},
    )


def create_app(
    settings: Settings | None = None,
    llm_client: LLMClient | None = None,
    agent_llm: AgentLLM | None = None,
) -> FastAPI:
    settings = settings or Settings()
    configure_logging(settings)
    rules = RulesHolder(YamlRulesSource(Path(settings.rules_path)))

    # The engine connects lazily; the lifespan below is the first thing that needs the database.
    engine = create_engine(settings.database_url)
    session_factory = sessionmaker(engine)

    def uow_factory() -> SqlUnitOfWork:
        return SqlUnitOfWork(session_factory)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Fail fast: without a valid rules file there is no category tree to sync.
        sync_categories(uow_factory, rules.load().categories)
        # The agent sees the schema as it is at startup; migrations only run before a start.
        schema = PostgresSchemaIntrospector(engine).introspect()
        app.state.agent_service = AgentService(
            resolved_agent_llm,
            PostgresQueryExecutor(
                engine, settings.agent_statement_timeout_seconds, settings.agent_max_rows
            ),
            schema,
            load_notes(),
            ConversationStore(
                settings.agent_max_turns,
                timedelta(minutes=settings.agent_conversation_ttl_minutes),
            ),
            max_retries=settings.agent_max_retries,
            summary_rows=settings.agent_summary_rows,
        )
        log.info(
            "agent_ready",
            model=app.state.agent_service.model_name,
            prompt_hash=app.state.agent_service.prompt_hash,
            relations=len(schema.relations),
        )
        yield

    if llm_client is None:
        settings.require_categorizer_llm()
        llm_client = LMStudioClient(
            settings.categorizer_llm_base_url,
            settings.categorizer_llm_model,
            settings.categorizer_llm_timeout_seconds,
            settings.categorizer_llm_api_key,
        )
    if agent_llm is None:
        settings.require_agent_llm()
        agent_llm = LMStudioAgentLLM(
            settings.agent_llm_base_url,
            settings.agent_llm_model,
            settings.agent_llm_timeout_seconds,
            settings.agent_llm_api_key,
        )
    resolved_agent_llm: AgentLLM = agent_llm
    llm_step = LLMCategorizationStep(
        uow_factory,
        llm_client,
        lambda: rules.current,
        threshold=settings.categorizer_llm_confidence_threshold,
        concurrency=settings.categorizer_llm_concurrency,
        batch_size=settings.categorizer_llm_batch_size,
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
    app.include_router(agent.router)
    return app
