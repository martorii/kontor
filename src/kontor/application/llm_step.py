import time
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ThreadPoolExecutor

import structlog

from kontor.domain.errors import (
    LLMInvalidOutputError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from kontor.domain.llm import LLMOutcome, LLMRunResult
from kontor.domain.recategorization import Candidate
from kontor.domain.rules import RulesConfig, assignable_slugs
from kontor.ports.llm import LLMClient
from kontor.ports.repositories import UnitOfWork

log = structlog.get_logger()

_CALL_ERRORS = (LLMTimeoutError, LLMInvalidOutputError, LLMUnavailableError)


class LLMCategorizationStep:
    """Categorizes the transactions the rules left open (CONTRACT §7.1 to §7.4, §8.4 to §8.7).

    Results are committed in small batches, so an interruption keeps everything done so far.
    """

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        client: LLMClient,
        get_rules: Callable[[], RulesConfig],
        *,
        threshold: float,
        concurrency: int = 1,
        batch_size: int = 10,
    ) -> None:
        self._uow_factory = uow_factory
        self._client = client
        self._get_rules = get_rules
        self._threshold = threshold
        self._concurrency = concurrency
        self._batch_size = batch_size

    def run(self, import_id: int | None = None, dry_run: bool = False) -> LLMRunResult:
        """Run on the uncategorized transactions of one import, or on all of them."""
        if import_id is not None:
            structlog.contextvars.bind_contextvars(import_id=import_id)
        try:
            return self._run(import_id, dry_run)
        finally:
            if import_id is not None:
                structlog.contextvars.unbind_contextvars("import_id")

    def _run(self, import_id: int | None, dry_run: bool) -> LLMRunResult:
        if not self._client.is_healthy():
            log.warning("llm_step_skipped", reason="LM Studio is not reachable")
            return LLMRunResult(dry_run=dry_run, skipped=True)

        slugs = assignable_slugs(self._get_rules().categories)
        with self._uow_factory() as uow:
            candidates = uow.transactions.list_uncategorized(import_id)
        total = len(candidates)
        log.info("llm_step_started", total=total, model=self._client.model_name, dry_run=dry_run)

        outcomes: list[LLMOutcome] = []
        interrupted = False
        done = 0
        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
                for start in range(0, total, self._batch_size):
                    batch = candidates[start : start + self._batch_size]
                    batch_outcomes: list[LLMOutcome] = []
                    for candidate, (outcome, latency) in zip(
                        batch, self._classify(pool, batch, slugs), strict=True
                    ):
                        done += 1
                        self._log_transaction(candidate, outcome, latency, done, total)
                        batch_outcomes.append(outcome)
                    outcomes.extend(batch_outcomes)
                    if not dry_run:
                        self._commit(batch_outcomes)
                    if any(o.error == "unavailable" for o in batch_outcomes):
                        log.warning("llm_step_aborted", reason="LM Studio became unreachable")
                        interrupted = True
                        break
        except Exception:  # the import is already committed; keep what was written
            log.exception("llm_step_interrupted", done=done, total=total)
            interrupted = True

        result = LLMRunResult(
            dry_run=dry_run,
            interrupted=interrupted,
            evaluated=len(outcomes),
            applied=sum(1 for o in outcomes if o.applied),
            suggested=sum(1 for o in outcomes if o.suggestion and not o.applied),
            failed=sum(1 for o in outcomes if o.suggestion is None),
            outcomes=tuple(outcomes),
        )
        log.info(
            "llm_step_finished",
            total=total,
            evaluated=result.evaluated,
            applied=result.applied,
            suggested=result.suggested,
            failed=result.failed,
            interrupted=interrupted,
            dry_run=dry_run,
            duration_s=round(time.monotonic() - started, 1),
        )
        return result

    def _classify(
        self, pool: ThreadPoolExecutor, batch: Sequence[Candidate], slugs: Sequence[str]
    ) -> Iterator[tuple[LLMOutcome, float]]:
        return pool.map(lambda candidate: self._classify_one(candidate, slugs), batch)

    def _classify_one(self, candidate: Candidate, slugs: Sequence[str]) -> tuple[LLMOutcome, float]:
        started = time.monotonic()
        try:
            suggestion = self._client.classify(candidate.prepared.transaction, slugs)
        except LLMUnavailableError:
            return LLMOutcome(candidate.transaction_id, None, False, "unavailable"), _since(started)
        except LLMTimeoutError:
            return LLMOutcome(candidate.transaction_id, None, False, "timeout"), _since(started)
        except LLMInvalidOutputError:
            return LLMOutcome(candidate.transaction_id, None, False, "invalid_output"), _since(
                started
            )
        applied = suggestion.confidence >= self._threshold
        return LLMOutcome(candidate.transaction_id, suggestion, applied), _since(started)

    def _commit(self, outcomes: Sequence[LLMOutcome]) -> None:
        with self._uow_factory() as uow:
            applied_by_import = uow.transactions.apply_llm_outcomes(
                outcomes, self._client.model_name
            )
            uow.imports.move_to_llm_matched(applied_by_import)
            uow.commit()

    @staticmethod
    def _log_transaction(
        candidate: Candidate, outcome: LLMOutcome, latency: float, done: int, total: int
    ) -> None:
        suggestion = outcome.suggestion
        log.info(
            "llm_transaction",
            progress=f"{done}/{total}",
            transaction_id=candidate.transaction_id,
            counterparty=candidate.prepared.transaction.counterparty,
            category=suggestion.category_slug if suggestion else None,
            confidence=round(suggestion.confidence, 3) if suggestion else None,
            outcome="applied"
            if outcome.applied
            else ("suggestion" if suggestion else outcome.error),
            latency_ms=round(latency * 1000),
        )


def _since(started: float) -> float:
    return time.monotonic() - started
