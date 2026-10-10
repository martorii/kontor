"""drop income vs. expenses view

Revision ID: b7d2e41c9a58
Revises: a1f3c9d27b40
Create Date: 2026-10-10 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7d2e41c9a58"
down_revision: str | None = "a1f3c9d27b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP VIEW v_monthly_income_expenses")


def downgrade() -> None:
    op.execute(
        """
CREATE VIEW v_monthly_income_expenses AS
SELECT
    account_id, currency, year, month,
    COALESCE(SUM(amount) FILTER (WHERE flow = 'income'), 0) AS income,
    COALESCE(SUM(-amount) FILTER (WHERE flow = 'expense'), 0) AS expenses,
    COUNT(*) FILTER (WHERE uncategorized AND flow <> 'excluded') AS uncategorized_count
FROM v_flows
WHERE flow <> 'excluded'
GROUP BY account_id, currency, year, month
"""
    )
