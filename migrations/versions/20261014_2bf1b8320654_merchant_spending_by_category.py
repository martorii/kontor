"""merchant spending by category

Revision ID: 2bf1b8320654
Revises: ae1591fcb761
Create Date: 2026-10-14 12:00:00.000000

`v_merchant_spending` gains the top-level and subcategory slugs, so top merchants can be
filtered by category (CONTRACT §11.1b). Recreating the view lets the default privileges grant
it to `kontor_agent` again, so the grant is revoked as in ae1591fcb761 (§16.2).
"""

from collections.abc import Sequence

from alembic import op

revision: str = "2bf1b8320654"
down_revision: str | None = "ae1591fcb761"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP VIEW v_merchant_spending")
    op.execute(
        """
CREATE VIEW v_merchant_spending AS
SELECT
    account_id, currency, booking_date, counterparty_normalized, top_slug, sub_slug,
    SUM(-amount) AS spent,
    COUNT(*) AS transaction_count
FROM v_flows
WHERE flow = 'expense'
GROUP BY account_id, currency, booking_date, counterparty_normalized, top_slug, sub_slug
"""
    )
    op.execute("REVOKE SELECT ON v_merchant_spending FROM kontor_agent")


def downgrade() -> None:
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
    op.execute("REVOKE SELECT ON v_merchant_spending FROM kontor_agent")
