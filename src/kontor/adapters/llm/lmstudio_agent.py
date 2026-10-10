"""The agent's LM Studio adapter (CONTRACT §16). JSON-schema structured output, no tools."""

import json
from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Any

import openai
from openai import OpenAI

from kontor.domain.agent import ChartSpec, FailedAttempt, Summary, Turn
from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError

SQL_SYSTEM_PROMPT = """\
You write PostgreSQL queries that answer questions about one person's bank transactions.

Rules:
- Write exactly one read-only SELECT statement (WITH and UNION are fine).
- Use only the tables, views and columns listed in the schema below.
- Follow the notes on what the data means, especially the signs of amounts and the views
  to prefer for spending and income.
- Give result columns short, readable names with AS.
- Order results meaningfully, and add LIMIT for "top" questions.
- Answer with JSON: {"sql": "<the query>"}. No explanation, no comments in the SQL.
"""

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
    "properties": {"sql": {"type": "string"}},
    "required": ["sql"],
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
    ) -> str:
        content = self._complete(
            f"{SQL_SYSTEM_PROMPT}\n{context}",
            render_sql_request(question, history, failed_attempts, date.today()),
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
            raise LLMUnavailableError(f"LM Studio returned HTTP {exc.status_code}") from exc
        content = response.choices[0].message.content
        if not content:
            raise LLMInvalidOutputError("response has no content")
        return content


def render_sql_request(
    question: str,
    history: Sequence[Turn],
    failed_attempts: Sequence[FailedAttempt],
    today: date,
) -> str:
    parts = [f"Today is {today.isoformat()}."]
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


def parse_sql_answer(content: str) -> str:
    try:
        sql = json.loads(content)["sql"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMInvalidOutputError("answer is not the expected JSON") from exc
    if not isinstance(sql, str) or not sql.strip():
        raise LLMInvalidOutputError("answer has no SQL")
    return sql.strip()


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
        date(2000, 1, 1),
    )
    sample_summary = render_summary_request("QUESTION", "SELECT 1", ["a"], [[1]], True)
    return "\n---\n".join([SQL_SYSTEM_PROMPT, SUMMARY_SYSTEM_PROMPT, sample_sql, sample_summary])


PROMPT_TEXT = _prompt_text()
