"""Domain records shared by Loop Engine components."""

from dataclasses import dataclass
from enum import Enum


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    NEEDS_HUMAN = "needs_human"


class AttemptStatus(Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GateStatus(Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TransitionType(Enum):
    DONE = "done"
    RETRY = "retry"
    HUMAN_ESCALATION = "human_escalation"


@dataclass
class Goal:
    id: str
    description: str
    constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "goal id")
        _require_text(self.description, "goal description")


@dataclass
class Task:
    id: str
    goal_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    dependencies: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "task id")
        _require_text(self.goal_id, "task goal_id")
        _require_text(self.title, "task title")
        _require_text(self.description, "task description")
        if self.id in self.dependencies:
            raise ValueError("a task must not depend on itself")


@dataclass
class Attempt:
    id: str
    task_id: str
    status: AttemptStatus
    worker: str
    summary: str = ""

    def __post_init__(self) -> None:
        _require_text(self.id, "attempt id")
        _require_text(self.task_id, "attempt task_id")
        _require_text(self.worker, "attempt worker")


@dataclass
class ReviewResult:
    attempt_id: str
    status: GateStatus
    findings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.attempt_id, "review attempt_id")


@dataclass
class TestResult:
    attempt_id: str
    status: GateStatus
    commands: tuple[str, ...] = ()
    output: str = ""

    def __post_init__(self) -> None:
        _require_text(self.attempt_id, "test attempt_id")


@dataclass
class TransitionDecision:
    task_id: str
    transition: TransitionType
    reason: str
    feedback: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.task_id, "transition task_id")
        _require_text(self.reason, "transition reason")
