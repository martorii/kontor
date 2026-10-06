from kontor.application.llm_progress import LLMProgressTracker
from kontor.domain.llm import LLMProgress


def test_tracker_follows_a_run_and_keeps_the_last_numbers() -> None:
    tracker = LLMProgressTracker()
    assert tracker.snapshot() == LLMProgress()

    tracker.start(total=10, import_id=3)
    tracker.advance(4)
    assert tracker.snapshot() == LLMProgress(True, 4, 10, 3)

    tracker.finish()
    assert tracker.snapshot() == LLMProgress(False, 4, 10, 3)


def test_a_new_run_replaces_the_previous_one() -> None:
    tracker = LLMProgressTracker()
    tracker.start(total=2, import_id=1)
    tracker.advance(2)
    tracker.finish()

    tracker.start(total=5, import_id=None)

    assert tracker.snapshot() == LLMProgress(True, 0, 5, None)
