"""agent column docs and curation

Revision ID: ae1591fcb761
Revises: ad15d3e433c4
Create Date: 2026-10-13 12:00:00.000000

Column comments document the data for the agent, which reads them through introspection
(CONTRACT §16.4). The table comments match the `comment=` in the models, so the drift check
stays green; the view comments live only here.

`kontor_agent` loses SELECT on the relations that misled it in the evaluation (§16.2): the
report views (v_flows covers what they offer) and the bookkeeping tables. The API's reports
keep using the views as before.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ae1591fcb761"
down_revision: str | None = "ad15d3e433c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HIDDEN = ("imports", "categorization_events", "v_monthly_category_spending", "v_merchant_spending")

COMMENTS: dict[tuple[str, str], str] = {
    ("accounts", "name"): "Account name as the user sees it.",
    ("categories", "slug"): (
        "Top-level slug such as food, or subcategory slug such as food.groceries."
    ),
    ("categories", "parent_slug"): (
        "Top-level category of a subcategory; NULL for top-level categories."
    ),
    (
        "categories",
        "kind",
    ): "expense, income, transfer or savings; set on top-level categories only.",
    ("transactions", "booking_date"): (
        "Date the bank booked the transaction; use it for date filters."
    ),
    ("transactions", "amount"): (
        "Signed: negative is money leaving the account, positive is money coming in."
    ),
    ("transactions", "counterparty_normalized"): (
        "Merchant or person, uppercase, without store numbers; match with ILIKE."
    ),
    ("transactions", "purpose"): "Free-text payment reference; match with ILIKE.",
    ("transactions", "category_slug"): (
        "Subcategory slug (categories.slug), or NULL when uncategorized."
    ),
    ("transactions", "category_source"): (
        "Who set the category: rule, llm or manual; NULL when uncategorized."
    ),
    ("v_flows", "transaction_id"): "transactions.id",
    ("v_flows", "account_id"): "accounts.id; join accounts for the account name.",
    ("v_flows", "currency"): "Account currency; do not add up different currencies.",
    ("v_flows", "booking_date"): "Date the bank booked the transaction; use it for date filters.",
    ("v_flows", "year"): "Year of booking_date.",
    ("v_flows", "month"): "Month of booking_date, 1 to 12.",
    ("v_flows", "counterparty_normalized"): (
        "Merchant or person, uppercase; match with ILIKE. A merchant question filters on this, "
        "not on a category."
    ),
    ("v_flows", "amount"): (
        "Signed: negative is money out. Spending is SUM(-amount) over flow = 'expense'; income "
        "is SUM(amount) over flow = 'income'. A refund is a positive amount in an expense "
        "category, so refunds alone are amount > 0."
    ),
    ("v_flows", "uncategorized"): (
        "true when the transaction has no category; it then counts as expense or income by sign."
    ),
    ("v_flows", "top_slug"): "Top-level category slug, or 'uncategorized'.",
    ("v_flows", "top_name"): "Top-level category name, or 'Uncategorized'.",
    ("v_flows", "sub_slug"): "Subcategory slug, or 'uncategorized'. Filter categories here.",
    ("v_flows", "sub_name"): "Subcategory name, or 'Uncategorized'.",
    ("v_flows", "flow"): (
        "Only expense, income or excluded. Transfers and savings are excluded; find them by "
        "top_slug or sub_slug, never by flow."
    ),
}


def _literal(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


def upgrade() -> None:
    for (relation, column), comment in COMMENTS.items():
        op.execute(f"COMMENT ON COLUMN {relation}.{column} IS {_literal(comment)}")
    for relation in HIDDEN:
        op.execute(f"REVOKE SELECT ON {relation} FROM kontor_agent")


def downgrade() -> None:
    for relation in HIDDEN:
        op.execute(f"GRANT SELECT ON {relation} TO kontor_agent")
    for relation, column in COMMENTS:
        op.execute(f"COMMENT ON COLUMN {relation}.{column} IS NULL")
