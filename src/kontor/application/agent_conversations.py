"""Agent conversations, held in API process memory (CONTRACT §16.7). A restart clears them."""

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from kontor.domain.agent import Turn


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class _Conversation:
    last_used: datetime
    turns: list[Turn] = field(default_factory=list)


class ConversationStore:
    """Keeps the last `max_turns` turns per conversation and forgets idle ones after `ttl`.

    Thread-safe: FastAPI runs sync endpoints in a thread pool.
    """

    def __init__(
        self, max_turns: int, ttl: timedelta, clock: Callable[[], datetime] = _now
    ) -> None:
        self._max_turns = max_turns
        self._ttl = ttl
        self._clock = clock
        self._conversations: dict[str, _Conversation] = {}
        self._lock = threading.Lock()

    def history(self, conversation_id: str) -> tuple[Turn, ...] | None:
        """The turns so far, or None when the conversation is unknown or expired."""
        with self._lock:
            self._evict_expired()
            conversation = self._conversations.get(conversation_id)
            if conversation is None:
                return None
            conversation.last_used = self._clock()
            return tuple(conversation.turns)

    def start(self) -> str:
        with self._lock:
            self._evict_expired()
            conversation_id = str(uuid.uuid4())
            self._conversations[conversation_id] = _Conversation(last_used=self._clock())
            return conversation_id

    def append(self, conversation_id: str, turn: Turn) -> None:
        with self._lock:
            conversation = self._conversations.setdefault(
                conversation_id, _Conversation(last_used=self._clock())
            )
            conversation.turns.append(turn)
            del conversation.turns[: -self._max_turns]
            conversation.last_used = self._clock()

    def delete(self, conversation_id: str) -> bool:
        """Forget a conversation. False if it did not exist."""
        with self._lock:
            return self._conversations.pop(conversation_id, None) is not None

    def _evict_expired(self) -> None:
        cutoff = self._clock() - self._ttl
        expired = [cid for cid, c in self._conversations.items() if c.last_used < cutoff]
        for conversation_id in expired:
            del self._conversations[conversation_id]
