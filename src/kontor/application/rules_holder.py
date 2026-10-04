import structlog

from kontor.domain.errors import RulesFileError
from kontor.domain.rules import RulesConfig
from kontor.ports.rules import RulesSource

log = structlog.get_logger()


class RulesHolder:
    """Holds the active rules. A failed reload keeps the previously loaded rules (CONTRACT §6.8)."""

    def __init__(self, source: RulesSource) -> None:
        self._source = source
        self._config: RulesConfig | None = None

    @property
    def current(self) -> RulesConfig:
        if self._config is None:
            raise RulesFileError("rules have not been loaded")
        return self._config

    def load(self) -> RulesConfig:
        """Load for the first time. Raises if the file is invalid (nothing to fall back on)."""
        self._config = self._source.load()
        return self._config

    def reload(self) -> RulesConfig:
        """Validate and activate the file again. Raises on failure, leaving the old rules active."""
        try:
            self._config = self._source.load()
        except RulesFileError as exc:
            log.warning("rules_reload_rejected", error=str(exc))
            raise
        return self._config
