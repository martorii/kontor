from collections.abc import Callable

import structlog

from kontor.application.rules_holder import RulesHolder
from kontor.domain.recategorization import RerunResult, plan_rerun
from kontor.ports.repositories import UnitOfWork

log = structlog.get_logger()


class CategorizationService:
    def __init__(self, uow_factory: Callable[[], UnitOfWork], rules: RulesHolder) -> None:
        self._uow_factory = uow_factory
        self._rules = rules

    def rerun(self, dry_run: bool) -> RerunResult:
        """Re-apply the rules to every transaction that is not manually categorized (§7.8).

        The file is validated first. If it is invalid this raises and the active rules stay
        unchanged. A dry run neither writes nor activates the new rules.
        """
        config = self._rules.validate()
        with self._uow_factory() as uow:
            candidates = uow.transactions.list_for_recategorization()
            evaluated, changes = plan_rerun(candidates, config.rules)
            if not dry_run:
                # New categories must exist before transactions can reference them.
                uow.categories.upsert_all(config.categories)
                uow.transactions.apply_rule_changes(changes, config.file_hash)
                uow.commit()
        if not dry_run:
            self._rules.activate(config)
        log.info(
            "categorization_rerun",
            dry_run=dry_run,
            evaluated=evaluated,
            changed=len(changes),
            rules_hash=config.file_hash,
        )
        return RerunResult(
            rules_hash=config.file_hash, dry_run=dry_run, evaluated=evaluated, changes=changes
        )
