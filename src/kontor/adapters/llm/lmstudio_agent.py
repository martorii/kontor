"""The agent's LM Studio adapter (CONTRACT §16). JSON-schema structured output, no tools."""

import json
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import openai
from openai import OpenAI

from kontor.adapters.llm.errors import status_error_detail
from kontor.domain.agent import ChartSpec, FailedAttempt, SqlDraft, Summary, Turn
from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError

SQL_SYSTEM_PROMPT = """\
You write PostgreSQL queries that answer questions about one person's bank transactions.

Rules:
- Write exactly one read-only SELECT statement (WITH and UNION are fine).
- Use only the tables, views and columns listed in the schema below, with the exact column
  names of the relation you query.
- Prefer the view v_flows. It already has the category (top_slug, top_name, sub_slug,
  sub_name), the flow and the date parts, so you never need to join categories.
- Spending is SUM(-amount) over flow = 'expense'; income is SUM(amount) over flow = 'income'.
  Never SUM(amount) for spending: outflows are negative.
- Filter categories on sub_slug or top_slug, using only the slugs in the Categories section.
- For relative periods, copy the date range from the Dates section.
- Return only the columns the question asks for, with short names (AS).
- Order results meaningfully, and add LIMIT for "top" questions.
- First write a one-sentence plan (relation, filters, sign, period), then the query.
- Answer with JSON: {"plan": "...", "sql": "..."}. No comments in the SQL.

"""


# Worked examples in the house style: question, plan, SQL. None is a golden-set question.
# Their dates are made up; the prompt tells the model to take its own from the Dates section.
SQL_EXAMPLES: list[tuple[str, str, str]] = [
    (
        "How much did I spend at the pharmacy last month?",
        "v_flows, sub_slug health.pharmacy, SUM(-amount), last month range",
        "SELECT SUM(-amount) AS spent FROM v_flows WHERE sub_slug = 'health.pharmacy' "
        "AND booking_date >= '2030-04-01' AND booking_date < '2030-05-01'",
    ),
    (
        "What did I spend per top-level category this year?",
        "v_flows, expense flow, SUM(-amount) grouped by top_name, this year range",
        "SELECT top_name AS category, SUM(-amount) AS spent FROM v_flows "
        "WHERE flow = 'expense' AND booking_date >= '2030-01-01' AND booking_date < '2031-01-01' "
        "GROUP BY top_name ORDER BY spent DESC",
    ),
    (
        "How much salary did I receive over the last 6 complete months?",
        "v_flows, sub_slug income.salary, SUM(amount) because income is positive, "
        "last 6 complete months range",
        "SELECT SUM(amount) AS received FROM v_flows WHERE sub_slug = 'income.salary' "
        "AND booking_date >= '2029-11-01' AND booking_date < '2030-05-01'",
    ),
    (
        "Which 3 merchants did I pay most for subscriptions last year?",
        "v_flows, sub_slug leisure.subscriptions, SUM(-amount) per counterparty_normalized, "
        "top 3, last year range",
        "SELECT counterparty_normalized AS merchant, SUM(-amount) AS spent FROM v_flows "
        "WHERE sub_slug = 'leisure.subscriptions' "
        "AND booking_date >= '2029-01-01' AND booking_date < '2030-01-01' "
        "GROUP BY counterparty_normalized ORDER BY spent DESC LIMIT 3",
    ),
    (
        "How many utility payments came from the Girokonto this year?",
        "v_flows joined to accounts by account_id, account name Girokonto, "
        "sub_slug housing.utilities, COUNT, this year range",
        "SELECT COUNT(*) AS payments FROM v_flows AS f JOIN accounts AS a ON a.id = f.account_id "
        "WHERE a.name = 'Girokonto' AND f.sub_slug = 'housing.utilities' "
        "AND f.booking_date >= '2030-01-01' AND f.booking_date < '2031-01-01'",
    ),
    (
        "What was my average monthly spending on daycare over the last 12 complete months?",
        "v_flows, sub_slug kids.daycare, monthly SUM(-amount), then AVG, "
        "last 12 complete months range",
        "SELECT AVG(spent) AS average_per_month FROM (SELECT year, month, SUM(-amount) AS spent "
        "FROM v_flows WHERE sub_slug = 'kids.daycare' "
        "AND booking_date >= '2029-05-01' AND booking_date < '2030-05-01' "
        "GROUP BY year, month) AS monthly",
    ),
]


def render_examples() -> str:
    blocks = [
        f"Question: {question}\n{json.dumps({'plan': plan, 'sql': sql})}"
        for question, plan, sql in SQL_EXAMPLES
    ]
    return "Examples (their dates are made up; take yours from the Dates section):\n\n" + (
        "\n\n".join(blocks)
    )


SUMMARY_SYSTEM_PROMPT = """\
You answer a question about one person's bank transactions from the result of a SQL query.

Rules:
- Answer in one to three sentences, in the language of the question.
- Use only the numbers in the result. If the result is empty, say that nothing was found.
- Money values are in the account currency. If only some rows are shown, say so.
- Pick a chart for the result: "line" for values over time, "bar" for comparing categories,
  merchants or months, "none" when a chart does not help (a single number, text, few rows).
  For "bar" and "line", "x" is the label or date column and "y" a numeric column, both
  exactly as named in the result. For "none", use empty strings.
- Answer with JSON: {"answer": "...", "chart": {"type": "...", "x": "...", "y": "..."}}.
"""

SQL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"plan": {"type": "string"}, "sql": {"type": "string"}},
    "required": ["plan", "sql"],
    "additionalProperties": False,
}

SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "chart": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "enum": ["bar", "line", "none"]},
                "x": {"type": "string"},
                "y": {"type": "string"},
            },
            "required": ["type", "x", "y"],
            "additionalProperties": False,
        },
    },
    "required": ["answer", "chart"],
    "additionalProperties": False,
}


class LMStudioAgentLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float,
        api_key: str = "lm-studio",
        *,
        client: OpenAI | None = None,
    ) -> None:
        self._model = model
        self._client = client or OpenAI(
            base_url=base_url, api_key=api_key, timeout=timeout_seconds, max_retries=0
        )

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def prompt_text(self) -> str:
        return PROMPT_TEXT

    def generate_sql(
        self,
        question: str,
        history: Sequence[Turn],
        context: str,
        failed_attempts: Sequence[FailedAttempt],
    ) -> SqlDraft:
        content = self._complete(
            f"{SQL_SYSTEM_PROMPT}\n{render_examples()}\n\n{context}",
            render_sql_request(question, history, failed_attempts),
            "sql_query",
            SQL_SCHEMA,
        )
        return parse_sql_answer(content)

    def summarize(
        self,
        question: str,
        sql: str,
        columns: Sequence[str],
        rows: Sequence[Sequence[object]],
        truncated: bool,
    ) -> Summary:
        content = self._complete(
            SUMMARY_SYSTEM_PROMPT,
            render_summary_request(question, sql, columns, rows, truncated),
            "answer",
            SUMMARY_SCHEMA,
        )
        return parse_summary_answer(content)

    def _complete(self, system: str, user: str, name: str, schema: dict[str, Any]) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": name, "strict": True, "schema": schema},
                },
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(str(exc)) from exc
        except openai.APIStatusError as exc:
            raise LLMUnavailableError(status_error_detail(exc)) from exc
        content = response.choices[0].message.content
        if not content:
            raise LLMInvalidOutputError("response has no content")
        return content


def render_sql_request(
    question: str,
    history: Sequence[Turn],
    failed_attempts: Sequence[FailedAttempt],
) -> str:
    """The user message. Today's date and the date ranges are in the context."""
    parts: list[str] = []
    if history:
        earlier = "\n\n".join(
            f"Question: {turn.question}\nSQL: {turn.sql or '(none)'}\nAnswer: {turn.answer}"
            for turn in history
        )
        parts.append(f"Earlier in this conversation:\n\n{earlier}")
    parts.append(f"Question: {question}")
    if failed_attempts:
        failures = "\n\n".join(
            f"SQL: {attempt.sql or '(no usable output)'}\nError: {attempt.error}"
            for attempt in failed_attempts
        )
        parts.append(
            f"Your earlier attempts for this question failed:\n\n{failures}\n\n"
            "Write a corrected query."
        )
    return "\n\n".join(parts)


def render_summary_request(
    question: str,
    sql: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    truncated: bool,
) -> str:
    lines = [" | ".join(columns), *(" | ".join(_cell(value) for value in row) for row in rows)]
    note = f"\n(Only the first {len(rows)} rows are shown.)" if truncated else ""
    return f"Question: {question}\n\nSQL:\n{sql}\n\nResult:\n" + "\n".join(lines) + note


def _cell(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def parse_sql_answer(content: str) -> SqlDraft:
    try:
        data = json.loads(content)
        sql = data["sql"]
        plan = data.get("plan")
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise LLMInvalidOutputError("answer is not the expected JSON") from exc
    if not isinstance(sql, str) or not sql.strip():
        raise LLMInvalidOutputError("answer has no SQL")
    plan = plan.strip() if isinstance(plan, str) and plan.strip() else None
    return SqlDraft(sql.strip(), plan)


def parse_summary_answer(content: str) -> Summary:
    try:
        data = json.loads(content)
        answer, chart = data["answer"], data["chart"]
        chart_type, x, y = chart["type"], chart["x"], chart["y"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMInvalidOutputError("answer is not the expected JSON") from exc
    if not isinstance(answer, str) or not answer.strip():
        raise LLMInvalidOutputError("answer is empty")
    if chart_type not in ("bar", "line", "none"):
        raise LLMInvalidOutputError(f"unknown chart type {chart_type!r}")
    if chart_type == "none":
        return Summary(answer.strip(), ChartSpec("none"))
    return Summary(answer.strip(), ChartSpec(chart_type, str(x) or None, str(y) or None))


def _prompt_text() -> str:
    """The system prompts plus rendered sample requests, so editing a template changes it."""
    sample_sql = render_sql_request(
        "QUESTION",
        [Turn("EARLIER", "SELECT 1", "ANSWER")],
        [FailedAttempt("SELECT 2", "ERROR")],
    )
    sample_summary = render_summary_request("QUESTION", "SELECT 1", ["a"], [[1]], True)
    return "\n---\n".join(
        [SQL_SYSTEM_PROMPT, render_examples(), SUMMARY_SYSTEM_PROMPT, sample_sql, sample_summary]
    )


PROMPT_TEXT = _prompt_text()
