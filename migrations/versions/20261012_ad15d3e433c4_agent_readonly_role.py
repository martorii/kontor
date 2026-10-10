"""agent read-only role

Revision ID: ad15d3e433c4
Revises: c4e8a1f6d302
Create Date: 2026-10-12 12:00:00.000000

The role `kontor_agent` can SELECT every table and view in `public` except
`alembic_version` (CONTRACT §16.2, §16.3). It is NOLOGIN: the API switches to it with
`SET LOCAL ROLE` inside each agent query, so it needs no password of its own.

Roles are cluster-wide while grants are per database. Several databases on one server (the
integration tests create one per run) share the role, so creating and dropping it tolerate
that it already exists or is still in use.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ad15d3e433c4"
down_revision: str | None = "c4e8a1f6d302"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
DO $$
BEGIN
    CREATE ROLE kontor_agent NOLOGIN;
EXCEPTION WHEN duplicate_object THEN
    NULL;
END
$$
"""
    )
    op.execute("GRANT kontor_agent TO CURRENT_USER")
    op.execute("GRANT USAGE ON SCHEMA public TO kontor_agent")
    op.execute("GRANT SELECT ON ALL TABLES IN SCHEMA public TO kontor_agent")
    op.execute("REVOKE ALL ON alembic_version FROM kontor_agent")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO kontor_agent")


def downgrade() -> None:
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM kontor_agent"
    )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM kontor_agent")
    op.execute("REVOKE USAGE ON SCHEMA public FROM kontor_agent")
    op.execute(
        """
DO $$
BEGIN
    DROP ROLE kontor_agent;
EXCEPTION WHEN dependent_objects_still_exist THEN
    RAISE NOTICE 'kontor_agent still has privileges in another database; keeping it';
END
$$
"""
    )
