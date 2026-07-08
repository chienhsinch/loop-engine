"""Company-level domain records for long-horizon mandate pursuit."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must not be empty")


def _require_optional_text(value: Optional[str], field_name: str) -> None:
    if value is not None:
        _require_text(value, field_name)


def _require_text_items(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple):
        raise ValueError(f"{field_name} values must be a tuple")
    for value in values:
        _require_text(value, field_name)


class MandateStatus(Enum):
    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    STOPPED = "stopped"
    NEEDS_HUMAN = "needs_human"


class ObjectiveStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    NEEDS_HUMAN = "needs_human"


class ExecutiveDecisionType(Enum):
    CONTINUE = "continue"
    SUCCESS = "success"
    STOP = "stop"
    HUMAN_ESCALATION = "human_escalation"


@dataclass(frozen=True)
class Mandate:
    id: str
    description: str
    constraints: tuple[str, ...] = ()
    success_criteria: tuple[str, ...] = ()
    stop_conditions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "mandate id")
        _require_text(self.description, "mandate description")
        _require_text_items(self.constraints, "mandate constraint")
        _require_text_items(self.success_criteria, "mandate success criterion")
        _require_text_items(self.stop_conditions, "mandate stop condition")


@dataclass(frozen=True)
class Objective:
    id: str
    mandate_id: str
    outcome: str
    rationale: str
    status: ObjectiveStatus = ObjectiveStatus.PENDING
    constraints: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    expected_evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "objective id")
        _require_text(self.mandate_id, "objective mandate_id")
        _require_text(self.outcome, "objective outcome")
        _require_text(self.rationale, "objective rationale")
        if not isinstance(self.status, ObjectiveStatus):
            raise ValueError("objective status must be an ObjectiveStatus")
        _require_text_items(self.constraints, "objective constraint")
        _require_text_items(
            self.acceptance_criteria, "objective acceptance criterion"
        )
        _require_text_items(self.expected_evidence, "objective expected evidence")


@dataclass(frozen=True)
class ExecutiveDecision:
    id: str
    mandate_id: str
    decision_type: ExecutiveDecisionType
    rationale: str
    objective_id: Optional[str] = None
    human_escalation_id: Optional[str] = None
    supporting_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "executive decision id")
        _require_text(self.mandate_id, "executive decision mandate_id")
        _require_text(self.rationale, "executive decision rationale")
        if not isinstance(self.decision_type, ExecutiveDecisionType):
            raise ValueError(
                "executive decision type must be an ExecutiveDecisionType"
            )
        _require_optional_text(self.objective_id, "executive decision objective_id")
        _require_optional_text(
            self.human_escalation_id,
            "executive decision human_escalation_id",
        )
        _require_text_items(
            self.supporting_evidence_ids,
            "executive decision supporting evidence id",
        )

        if self.decision_type is ExecutiveDecisionType.CONTINUE:
            if self.objective_id is None:
                raise ValueError("a continue decision requires an objective_id")
            if self.human_escalation_id is not None:
                raise ValueError(
                    "a continue decision must not identify a human escalation"
                )
        elif self.decision_type is ExecutiveDecisionType.HUMAN_ESCALATION:
            if self.human_escalation_id is None:
                raise ValueError(
                    "a human escalation decision requires a human_escalation_id"
                )
            if self.objective_id is not None:
                raise ValueError(
                    "a human escalation decision must not authorize an objective"
                )
        elif self.objective_id is not None or self.human_escalation_id is not None:
            raise ValueError(
                "success and stop decisions must not identify an objective "
                "or human escalation"
            )


@dataclass(frozen=True)
class Evidence:
    id: str
    mandate_id: str
    source: str
    observation: str
    objective_id: Optional[str] = None
    decision_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text(self.id, "evidence id")
        _require_text(self.mandate_id, "evidence mandate_id")
        _require_text(self.source, "evidence source")
        _require_text(self.observation, "evidence observation")
        _require_optional_text(self.objective_id, "evidence objective_id")
        _require_optional_text(self.decision_id, "evidence decision_id")


@dataclass(frozen=True)
class HumanEscalation:
    id: str
    mandate_id: str
    question: str
    reason: str
    objective_id: Optional[str] = None
    evidence_ids: tuple[str, ...] = ()
    options: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.id, "human escalation id")
        _require_text(self.mandate_id, "human escalation mandate_id")
        _require_text(self.question, "human escalation question")
        _require_text(self.reason, "human escalation reason")
        _require_optional_text(
            self.objective_id, "human escalation objective_id"
        )
        _require_text_items(self.evidence_ids, "human escalation evidence id")
        _require_text_items(self.options, "human escalation option")


@dataclass(frozen=True)
class CompanyStateUpdate:
    summary: str
    facts: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    relevant_evidence_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_text(self.summary, "company state update summary")
        _require_text_items(self.facts, "company state update fact")
        _require_text_items(self.assumptions, "company state update assumption")
        _require_text_items(
            self.open_questions, "company state update open question"
        )
        _require_text_items(
            self.relevant_evidence_ids,
            "company state update relevant evidence id",
        )


@dataclass(frozen=True)
class CompanyState:
    mandate_id: str
    status: MandateStatus
    summary: str
    active_objective_id: Optional[str] = None
    facts: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    open_questions: tuple[str, ...] = ()
    relevant_evidence_ids: tuple[str, ...] = ()
    pending_human_escalation_id: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text(self.mandate_id, "company state mandate_id")
        _require_text(self.summary, "company state summary")
        if not isinstance(self.status, MandateStatus):
            raise ValueError("company state status must be a MandateStatus")
        _require_optional_text(
            self.active_objective_id, "company state active_objective_id"
        )
        _require_optional_text(
            self.pending_human_escalation_id,
            "company state pending_human_escalation_id",
        )
        _require_text_items(self.facts, "company state fact")
        _require_text_items(self.assumptions, "company state assumption")
        _require_text_items(self.open_questions, "company state open question")
        _require_text_items(
            self.relevant_evidence_ids, "company state relevant evidence id"
        )

        if (
            self.status in (MandateStatus.SUCCEEDED, MandateStatus.STOPPED)
            and self.active_objective_id is not None
        ):
            raise ValueError(
                "terminal company state must not identify an active objective"
            )

        if self.status is MandateStatus.NEEDS_HUMAN:
            if self.pending_human_escalation_id is None:
                raise ValueError(
                    "a needs-human company state requires a "
                    "pending_human_escalation_id"
                )
        elif self.pending_human_escalation_id is not None:
            raise ValueError(
                "only a needs-human company state may identify a pending "
                "human escalation"
            )
