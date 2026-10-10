from datetime import UTC, datetime, timedelta

from kontor.application.agent_conversations import ConversationStore
from kontor.domain.agent import Turn


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


def turn(n: int) -> Turn:
    return Turn(f"question {n}", f"SELECT {n}", f"answer {n}")


def test_new_conversation_has_no_history() -> None:
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60))

    conversation_id = store.start()

    assert store.history(conversation_id) == ()


def test_turns_are_kept_in_order() -> None:
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60))
    conversation_id = store.start()

    store.append(conversation_id, turn(1))
    store.append(conversation_id, turn(2))

    assert store.history(conversation_id) == (turn(1), turn(2))


def test_only_the_last_max_turns_are_kept() -> None:
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60))
    conversation_id = store.start()

    for n in range(12):
        store.append(conversation_id, turn(n))

    assert store.history(conversation_id) == tuple(turn(n) for n in range(2, 12))


def test_unknown_conversation_has_no_history() -> None:
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60))

    assert store.history("no-such-id") is None


def test_idle_conversation_expires_after_the_ttl() -> None:
    clock = Clock()
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60), clock=clock)
    conversation_id = store.start()
    store.append(conversation_id, turn(1))

    clock.now += timedelta(minutes=61)

    assert store.history(conversation_id) is None


def test_use_keeps_a_conversation_alive() -> None:
    clock = Clock()
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60), clock=clock)
    conversation_id = store.start()

    clock.now += timedelta(minutes=50)
    store.history(conversation_id)
    clock.now += timedelta(minutes=50)

    assert store.history(conversation_id) == ()


def test_expired_conversations_are_evicted_from_memory() -> None:
    clock = Clock()
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60), clock=clock)
    old = store.start()
    clock.now += timedelta(minutes=61)

    store.start()

    assert old not in store._conversations


def test_delete() -> None:
    store = ConversationStore(max_turns=10, ttl=timedelta(minutes=60))
    conversation_id = store.start()

    assert store.delete(conversation_id) is True
    assert store.delete(conversation_id) is False
    assert store.history(conversation_id) is None
