# Notes on the Kontor data

Kontor stores one person's bank transactions. These notes explain what the data means; the
schema listing that follows them says which tables, views and columns exist.

## Money

- `amount` is `numeric(12,2)`. Negative amounts are outflows (money leaving the account),
  positive amounts are inflows.
- Every account has one currency. Do not add up amounts across different `currency` values.

## Categories

- `categories` is a two-level tree. A top-level category has a `kind` and no `parent_slug`;
  a subcategory has a `parent_slug` and no `kind`. Subcategory slugs look like
  `<parent>.<name>`, for example `food.groceries`.
- `kind` is one of `expense`, `income`, `transfer`, `savings`.
- A transaction points at a subcategory through `transactions.category_slug`, or has none
  (uncategorized). `category_source` says who set it: `rule`, `llm` or `manual`; it is null
  exactly when the transaction is uncategorized.

## Spending and income

- Spending is the outflow in `expense` categories. Refunds (positive amounts in an expense
  category) reduce spending. `income` categories count as income. `transfer` and `savings`
  count as neither.
- Uncategorized transactions count as spending when negative and as income when positive.
- `v_flows` already applies these rules: one row per transaction, with `flow` set to
  `expense`, `income` or `excluded`, the top-level and subcategory (`top_slug`, `top_name`,
  `sub_slug`, `sub_name`, `'uncategorized'` when there is none), and `year` and `month`.
  Spending is `SUM(-amount)` over `flow = 'expense'`; income is `SUM(amount)` over
  `flow = 'income'`.
- Prefer `v_flows` and the report views over the raw `transactions` table for any question
  about spending or income:
  - `v_monthly_category_spending`: spending per month and category (`spent` is positive).
  - `v_merchant_spending`: spending per day and merchant (`spent` is positive).

## Merchants and text

- `counterparty_normalized` is the merchant or person, normalized (uppercase, no store
  numbers). Use it to group by merchant, and match it with `ILIKE`, e.g.
  `counterparty_normalized ILIKE '%rewe%'`. `counterparty_raw` is the bank's original text.
- `purpose` is the free-text payment reference. Match it case-insensitively with `ILIKE`.

## Dates

- `booking_date` is the date the bank booked the transaction; use it for date filters.
  `value_date` may be null.
- "Last month" and similar phrases are relative to `current_date`.

## Accounts and imports

- `accounts` holds each bank account with its `name`, `iban` and `currency`.
- `imports` records each uploaded file. `categorization_events` is the history of every
  categorization; the current category is on `transactions`.
