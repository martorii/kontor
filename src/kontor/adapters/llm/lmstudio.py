import hashlib
import json
import math
from collections.abc import Sequence
from datetime import date
from decimal import Decimal

import openai
from openai import OpenAI

from kontor.domain.errors import LLMInvalidOutputError, LLMTimeoutError, LLMUnavailableError
from kontor.domain.llm import LLMSuggestion
from kontor.domain.transaction import Transaction

SYSTEM_PROMPT = (
    "You categorize bank transactions. Answer with the single best category from the allowed list."
)


class LMStudioClient:
    """LM Studio through its OpenAI-compatible API.

    The category is constrained to an enum with JSON-schema structured output. Confidence is
    the probability of the chosen category's tokens, from the logprobs the server returns.
    """

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
    def prompt_hash(self) -> str:
        return PROMPT_HASH

    def is_healthy(self) -> bool:
        try:
            self._client.models.list()
        except openai.OpenAIError:
            return False
        return True

    def classify(self, transaction: Transaction, category_slugs: Sequence[str]) -> LLMSuggestion:
        schema = {
            "type": "object",
            "properties": {"category": {"type": "string", "enum": list(category_slugs)}},
            "required": ["category"],
            "additionalProperties": False,
        }
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": _describe(transaction, category_slugs)},
                ],
                temperature=0,
                logprobs=True,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "categorization", "strict": True, "schema": schema},
                },
            )
        except openai.APITimeoutError as exc:
            raise LLMTimeoutError(str(exc)) from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(str(exc)) from exc
        except openai.APIStatusError as exc:
            raise LLMUnavailableError(f"LM Studio returned HTTP {exc.status_code}") from exc

        choice = response.choices[0]
        if not choice.message.content or choice.logprobs is None or not choice.logprobs.content:
            raise LLMInvalidOutputError("response has no content or no logprobs")
        tokens = [(t.token, t.logprob) for t in choice.logprobs.content]
        return parse_answer(choice.message.content, tokens, category_slugs)


def _describe(transaction: Transaction, category_slugs: Sequence[str]) -> str:
    return (
        f"Counterparty: {transaction.counterparty}\n"
        f"Purpose: {transaction.purpose}\n"
        f"Amount: {transaction.amount} {transaction.currency}\n"
        "Allowed categories:\n" + "\n".join(f"- {slug}" for slug in category_slugs)
    )


def parse_answer(
    content: str, tokens: Sequence[tuple[str, float]], category_slugs: Sequence[str]
) -> LLMSuggestion:
    """Validate the JSON answer and compute the confidence of the chosen category."""
    try:
        category = json.loads(content)["category"]
    except (ValueError, KeyError, TypeError) as exc:
        raise LLMInvalidOutputError("answer is not the expected JSON") from exc
    if category not in category_slugs:
        raise LLMInvalidOutputError(f"category {category!r} is not in the allowed list")
    return LLMSuggestion(category_slug=category, confidence=_category_probability(category, tokens))


def _category_probability(category: str, tokens: Sequence[tuple[str, float]]) -> float:
    """exp(sum of logprobs) of the tokens that spell the category value."""
    text = "".join(token for token, _ in tokens)
    key_end = text.find(":") + 1
    start = text.find(category, key_end)
    if start < 0:
        raise LLMInvalidOutputError("category not found in the token stream")
    end = start + len(category)
    total = 0.0
    position = 0
    for token, logprob in tokens:
        token_end = position + len(token)
        if token_end > start and position < end:
            total += logprob
        position = token_end
    return min(1.0, math.exp(total))


def _prompt_hash() -> str:
    """Hash of the system prompt and the rendered user-message template, so editing either
    changes it."""
    sample = Transaction(date(2000, 1, 1), Decimal("-1.00"), "EUR", "COUNTERPARTY", "PURPOSE")
    rendered = _describe(sample, ["category.one", "category.two"])
    return hashlib.sha256(f"{SYSTEM_PROMPT}\n---\n{rendered}".encode()).hexdigest()


PROMPT_HASH = _prompt_hash()
