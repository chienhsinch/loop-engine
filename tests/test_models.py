import pytest

from loop_engine.models import (
    Attempt,
    AttemptStatus,
    GateStatus,
    Goal,
    ReviewResult,
    Task,
    TaskStatus,
    TestResult as DomainTestResult,
    TransitionDecision,
    TransitionType,
)


def test_domain_models_can_be_constructed() -> None:
    goal = Goal("goal-1", "Implement the core models", ("Use Python",))
    task = Task(
        "task-1",
        goal.id,
        "Define models",
        "Create the domain records.",
        acceptance_criteria=("Models validate required fields",),
    )
    attempt = Attempt(
        "attempt-1", task.id, AttemptStatus.SUCCEEDED, "test-worker", "Done"
    )
    review = ReviewResult(attempt.id, GateStatus.PASSED, ("Looks correct",))
    test_result = DomainTestResult(
        attempt.id, GateStatus.PASSED, ("pytest",), "All tests passed"
    )
    decision = TransitionDecision(
        task.id, TransitionType.DONE, "Review and tests passed"
    )

    assert goal.constraints == ("Use Python",)
    assert task.status is TaskStatus.PENDING
    assert attempt.status is AttemptStatus.SUCCEEDED
    assert review.status is GateStatus.PASSED
    assert test_result.commands == ("pytest",)
    assert decision.transition is TransitionType.DONE


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: Goal("", "Description"), "goal id"),
        (lambda: Goal("goal-1", "  "), "goal description"),
        (lambda: Task("", "goal-1", "Title", "Description"), "task id"),
        (lambda: Task("task-1", "", "Title", "Description"), "goal_id"),
        (lambda: Task("task-1", "goal-1", "", "Description"), "task title"),
        (lambda: Task("task-1", "goal-1", "Title", ""), "task description"),
        (
            lambda: Attempt("", "task-1", AttemptStatus.STARTED, "worker"),
            "attempt id",
        ),
        (
            lambda: Attempt("attempt-1", "", AttemptStatus.STARTED, "worker"),
            "task_id",
        ),
        (
            lambda: Attempt("attempt-1", "task-1", AttemptStatus.STARTED, ""),
            "worker",
        ),
        (lambda: ReviewResult("", GateStatus.PASSED), "attempt_id"),
        (lambda: DomainTestResult("", GateStatus.PASSED), "attempt_id"),
        (
            lambda: TransitionDecision("", TransitionType.DONE, "Passed"),
            "task_id",
        ),
    ],
)
def test_empty_required_fields_are_rejected(factory, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


def test_task_cannot_depend_on_itself() -> None:
    with pytest.raises(ValueError, match="must not depend on itself"):
        Task(
            "task-1",
            "goal-1",
            "Title",
            "Description",
            dependencies=("task-1",),
        )


def test_transition_decision_requires_reason() -> None:
    with pytest.raises(ValueError, match="reason"):
        TransitionDecision("task-1", TransitionType.RETRY, "  ")
