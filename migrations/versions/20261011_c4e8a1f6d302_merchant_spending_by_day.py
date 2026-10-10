"""merchant spending by day

Revision ID: c4e8a1f6d302
Revises: b7d2e41c9a58
Create Date: 2026-10-11 12:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4e8a1f6d302"
down_revision: str | None = "b7d2e41c9a58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP VIEW v_merchant_spending")
    op.execute(
        """
CREATE VIEW v_merchant_spending AS
SELECT
    account_id, currency, booking_date, counterparty_normalized,
    SUM(-amount) AS spent,
    COUNT(*) AS transaction_count
FROM v_flows
WHERE flow = 'expense'
GROUP BY account_id, currency, booking_date, counterparty_normalized
"""
    )


def downgrade() -> None:
    op.execute("DROP VIEW v_merchant_spending")
    op.execute(
        """
CREATE VIEW v_merchant_spending AS
SELECT
    account_id, currency, year, month, counterparty_normalized,
    SUM(-amount) AS spent,
    COUNT(*) AS transaction_count
FROM v_flows
WHERE flow = 'expense'
GROUP BY account_id, currency, year, month, counterparty_normalized
"""
    )
