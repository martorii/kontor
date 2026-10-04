from typing import Protocol

from kontor.domain.rules import RulesConfig


class RulesSource(Protocol):
    def load(self) -> RulesConfig:
        """Read and validate the rules. Raises RulesFileError with a readable message."""
        ...
