from alembic import context
from sqlalchemy import create_engine

from kontor.adapters.db.models import Base
from kontor.config import Settings

target_metadata = Base.metadata


def run_migrations() -> None:
    engine = create_engine(Settings().database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations()
