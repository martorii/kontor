from typing import Protocol

from kontor.domain.reference import ReferenceValues


class ReferenceValuesSource(Protocol):
    def load(self) -> ReferenceValues:
        """The current category tree and account names. Read per question: both can change."""
        ...
