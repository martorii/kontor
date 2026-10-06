import threading

from kontor.domain.llm import LLMProgress


class LLMProgressTracker:
    """In-memory progress of the LLM step (CONTRACT §8.9).

    One run is tracked at a time. If two runs overlap, the later one wins. The state is lost
    when the API restarts, which is fine for a single-user local app.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state = LLMProgress()

    def start(self, total: int, import_id: int | None) -> None:
        with self._lock:
            self._state = LLMProgress(True, 0, total, import_id)

    def advance(self, processed: int) -> None:
        with self._lock:
            self._state = LLMProgress(True, processed, self._state.total, self._state.import_id)

    def finish(self) -> None:
        with self._lock:
            self._state = LLMProgress(
                False, self._state.processed, self._state.total, self._state.import_id
            )

    def snapshot(self) -> LLMProgress:
        with self._lock:
            return self._state
