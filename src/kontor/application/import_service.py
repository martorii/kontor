import hashlib
from collections.abc import Callable
from dataclasses import replace

import structlog

from kontor.application.llm_step import LLMCategorizationStep
from kontor.domain.account import NewAccount
from kontor.domain.errors import DuplicateFileError
from kontor.domain.fingerprint import fingerprint_all
from kontor.domain.imports import ImportCounts, ImportRecord, ImportResult
from kontor.domain.normalization import normalize_counterparty
from kontor.domain.rule_engine import match_rule
from kontor.domain.rules import RulesConfig
from kontor.domain.transaction import PreparedTransaction, RuleCategorization
from kontor.ports.parser import BankParser
from kontor.ports.repositories import UnitOfWork

DEFAULT_CURRENCY = "EUR"

log = structlog.get_logger()


class ImportService:
    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        detect_parser: Callable[[bytes], BankParser],
        get_rules: Callable[[], RulesConfig],
        llm_step: LLMCategorizationStep | None = None,
    ) -> None:
        self._uow_factory = uow_factory
        self._detect_parser = detect_parser
        self._get_rules = get_rules
        self._llm_step = llm_step

    def list_imports(self) -> list[ImportRecord]:
        with self._uow_factory() as uow:
            return uow.imports.list()

    def import_file(self, file_name: str, content: bytes) -> ImportResult:
        """Parse, deduplicate and persist one file in a single database transaction.

        Any failure rolls back the whole file, including an auto-created account.
        """
        file_hash = hashlib.sha256(content).hexdigest()
        parser = self._detect_parser(content)
        statement = parser.parse(content)
        rules = self._get_rules()  # one snapshot for the whole file

        with self._uow_factory() as uow:
            if uow.imports.hash_exists(file_hash):
                raise DuplicateFileError("this file was already imported")

            account = uow.accounts.get_by_iban(statement.iban)
            account_created = account is None
            if account is None:
                first = statement.transactions[0] if statement.transactions else None
                currency = first.currency if first else DEFAULT_CURRENCY
                account = uow.accounts.add(
                    NewAccount(
                        name=f"{parser.bank} {parser.account_type} …{statement.iban[-4:]}",
                        bank=parser.bank,
                        iban=statement.iban,
                        currency=currency,
                        account_type=parser.account_type,
                        parser_format=parser.format_name,
                    )
                )

            import_id = uow.imports.add(account.id, file_name, file_hash)
            structlog.contextvars.bind_contextvars(import_id=import_id)
            try:
                fingerprints = fingerprint_all(str(account.id), statement.transactions)
                existing = uow.transactions.existing_fingerprints(account.id, fingerprints)
                new_rows = [
                    self._categorize(
                        PreparedTransaction(
                            transaction=transaction,
                            counterparty_normalized=normalize_counterparty(
                                transaction.counterparty
                            ),
                            fingerprint=fingerprint,
                        ),
                        rules,
                        account.iban,
                    )
                    for transaction, fingerprint in zip(
                        statement.transactions, fingerprints, strict=True
                    )
                    if fingerprint not in existing
                ]
                uow.transactions.add_many(account.id, import_id, new_rows)
                rule_matched = sum(1 for row in new_rows if row.categorization)
                counts = ImportCounts(
                    new=len(new_rows),
                    duplicates=len(statement.transactions) - len(new_rows),
                    rule_matched=rule_matched,
                    uncategorized=len(new_rows) - rule_matched,
                )
                record = uow.imports.complete(import_id, counts)
                uow.commit()
                log.info(
                    "import_completed",
                    account_id=account.id,
                    account_created=account_created,
                    new=counts.new,
                    duplicates=counts.duplicates,
                    rule_matched=counts.rule_matched,
                    uncategorized=counts.uncategorized,
                )
            finally:
                structlog.contextvars.unbind_contextvars("import_id")

        # The file is committed. The LLM step can only add to it (CONTRACT §8.3, §8.4).
        if self._llm_step is not None and counts.uncategorized:
            llm = self._llm_step.run(import_id=record.id)
            record = replace(
                record,
                counts=replace(
                    counts,
                    llm_matched=llm.applied,
                    uncategorized=counts.uncategorized - llm.applied,
                ),
            )
        return ImportResult(record=record, account_created=account_created)

    @staticmethod
    def _categorize(
        prepared: PreparedTransaction, rules: RulesConfig, account_iban: str
    ) -> PreparedTransaction:
        rule = match_rule(rules.rules, prepared, account_iban)
        if rule is None:
            return prepared
        return replace(
            prepared,
            categorization=RuleCategorization(
                category_slug=rule.category_slug, rule_id=rule.id, rules_hash=rules.file_hash
            ),
        )
