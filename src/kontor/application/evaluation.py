import time
from collections.abc import Callable
from datetime import date
from decimal import Decimal

import structlog

from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from kontor.domain.evaluation import EvalCase, EvalMetrics, LabeledExample, compute_metrics
from kontor.domain.reports import TransactionFilter
from kontor.domain.rules import CategoryDef, assignable_slugs
from kontor.domain.transaction import Transaction
from kontor.ports.llm import LLMClient
from kontor.ports.repositories import UnitOfWork

log = structlog.get_logger()

_EXPORT_PAGE = 500
_CALL_ERRORS = (LLMTimeoutError, LLMInvalidOutputError, LLMUnavailableError)


def export_labeled_set(uow_factory: Callable[[], UnitOfWork]) -> list[LabeledExample]:
    """Every manually categorized transaction, as a labeled example (CONTRACT §12.4)."""
    examples: list[LabeledExample] = []
    offset = 0
    with uow_factory() as uow:
        while True:
            page = uow.transactions.search(TransactionFilter(source="manual"), _EXPORT_PAGE, offset)
            examples += [
                LabeledExample(
                    counterparty=t.counterparty,
                    purpose=t.purpose,
                    amount=t.amount,
                    currency=t.currency,
                    category_slug=t.category or "",
                )
                for t in page.items
                if t.category
            ]
            offset += _EXPORT_PAGE
            if offset >= page.total:
                return examples


def evaluate(
    client: LLMClient,
    examples: list[LabeledExample],
    categories: tuple[CategoryDef, ...],
    threshold: float,
    clock: Callable[[], float] = time.perf_counter,
) -> tuple[EvalMetrics, int]:
    """Run the examples through the LLM client. Returns the metrics and the number of examples
    skipped because their category no longer exists in the rules file."""
    slugs = assignable_slugs(categories)
    parents = {c.slug: c.parent_slug for c in categories if c.parent_slug is not None}
    usable = [e for e in examples if e.category_slug in parents]
    cases: list[EvalCase] = []
    for number, example in enumerate(usable, start=1):
        transaction = Transaction(
            booking_date=date.today(),  # not part of the prompt
            amount=Decimal(example.amount),
            currency=example.currency,
            counterparty=example.counterparty,
            purpose=example.purpose,
        )
        started = clock()
        try:
            suggestion = client.classify(transaction, slugs)
        except _CALL_ERRORS as exc:
            log.warning("eval_call_failed", number=number, error=str(exc))
            cases.append(EvalCase(example.category_slug, None, None, clock() - started))
        else:
            cases.append(
                EvalCase(
                    example.category_slug,
                    suggestion.category_slug,
                    suggestion.confidence,
                    clock() - started,
                )
            )
        if number % 25 == 0:
            log.info("eval_progress", done=number, total=len(usable))
    return compute_metrics(cases, parents, threshold), len(examples) - len(usable)
