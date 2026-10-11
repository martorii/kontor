from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CategoryRef:
    """A category as the agent sees it. Only top-level categories have a kind."""

    slug: str
    name: str
    parent_slug: str | None
    kind: str | None


@dataclass(frozen=True, slots=True)
class ReferenceValues:
    """Values the agent filters on, so it does not have to guess them."""

    categories: tuple[CategoryRef, ...]
    accounts: tuple[str, ...]
