"""reporting views

Revision ID: a1f3c9d27b40
Revises: 62bc01c53e8c
Create Date: 2026-10-05 18:00:00.000000
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1f3c9d27b40"
down_revision: str | None = "62bc01c53e8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Base layer. Classifies every transaction into a flow (CONTRACT §5.4, §11.1):
#   expense  - category kind `expense`, or uncategorized with a negative amount
#   income   - category kind `income`, or uncategorized with a positive amount
#   excluded - kind `transfer` or `savings`
# Refunds net against spending: `spent` is the negated amount, so a positive amount in an
# expense category reduces the total. The same holds for `earned` and income categories.
V_FLOWS = """
CREATE VIEW v_flows AS
SELECT
    t.id AS transaction_id,
    t.account_id,
    t.currency,
    t.booking_date,
    EXTRACT(YEAR FROM t.booking_date)::int AS year,
    EXTRACT(MONTH FROM t.booking_date)::int AS month,
    t.counterparty_normalized,
    t.amount,
    t.category_slug IS NULL AS uncategorized,
    COALESCE(parent.slug, 'uncategorized') AS top_slug,
    COALESCE(parent.name, 'Uncategorized') AS top_name,
    COALESCE(sub.slug, 'uncategorized') AS sub_slug,
    COALESCE(sub.name, 'Uncategorized') AS sub_name,
    CASE
        WHEN parent.kind = 'expense' THEN 'expense'
        WHEN parent.kind = 'income' THEN 'income'
        WHEN parent.kind IS NULL AND t.amount < 0 THEN 'expense'
        WHEN parent.kind IS NULL THEN 'income'
        ELSE 'excluded'
    END AS flow
FROM transactions t
LEFT JOIN categories sub ON sub.slug = t.category_slug
LEFT JOIN categories parent ON parent.slug = sub.parent_slug
"""

V_MONTHLY_CATEGORY_SPENDING = """
CREATE VIEW v_monthly_category_spending AS
SELECT
    account_id, currency, year, month,
    top_slug, top_name, sub_slug, sub_name, uncategorized,
    SUM(-amount) AS spent,
    COUNT(*) AS transaction_count
FROM v_flows
WHERE flow = 'expense'
GROUP BY account_id, currency, year, month, top_slug, top_name, sub_slug, sub_name, uncategorized
"""

V_MONTHLY_INCOME_EXPENSES = """
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

V_MERCHANT_SPENDING = """
CREATE VIEW v_merchant_spending AS
SELECT
    account_id, currency, year, month, counterparty_normalized,
    SUM(-amount) AS spent,
    COUNT(*) AS transaction_count
FROM v_flows
WHERE flow = 'expense'
GROUP BY account_id, currency, year, month, counterparty_normalized
"""

VIEWS = [
    ("v_flows", V_FLOWS),
    ("v_monthly_category_spending", V_MONTHLY_CATEGORY_SPENDING),
    ("v_monthly_income_expenses", V_MONTHLY_INCOME_EXPENSES),
    ("v_merchant_spending", V_MERCHANT_SPENDING),
]


def upgrade() -> None:
    for _, sql in VIEWS:
        op.execute(sql)


def downgrade() -> None:
    for name, _ in reversed(VIEWS):
        op.execute(f"DROP VIEW {name}")
