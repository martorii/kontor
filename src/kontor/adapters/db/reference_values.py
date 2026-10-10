from sqlalchemy import Engine, text

from kontor.domain.reference import CategoryRef, ReferenceValues


class PostgresReferenceValues:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def load(self) -> ReferenceValues:
        with self._engine.connect() as conn:
            categories = conn.execute(
                text("SELECT slug, name, parent_slug, kind FROM categories ORDER BY slug")
            ).all()
            accounts = conn.execute(text("SELECT name FROM accounts ORDER BY name")).scalars()
            return ReferenceValues(
                categories=tuple(CategoryRef(*row) for row in categories),
                accounts=tuple(accounts),
            )
