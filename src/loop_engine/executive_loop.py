"""Deterministic company-level state transitions."""

from dataclasses import replace
from typing import Optional

from loop_engine.company_models import (
    CompanyState,
    CompanyStateUpdate,
    Evidence,
    ExecutiveDecision,
    ExecutiveDecisionType,
    HumanEscalation,
    MandateStatus,
    Objective,
    ObjectiveStatus,
)


_TERMINAL_MANDATE_STATUSES = (MandateStatus.SUCCEEDED, MandateStatus.STOPPED)
_TERMINAL_OBJECTIVE_STATUSES = (
    ObjectiveStatus.SUCCEEDED,
    ObjectiveStatus.FAILED,
    ObjectiveStatus.CANCELLED,
    ObjectiveStatus.NEEDS_HUMAN,
)


def apply_executive_decision(
    state: CompanyState,
    decision: ExecutiveDecision,
    objective: Optional[Objective] = None,
    human_escalation: Optional[HumanEscalation] = None,
) -> CompanyState:
    """Validate and apply one executive decision to the current snapshot."""

    if state.mandate_id != decision.mandate_id:
        raise ValueError("state and decision must belong to the same mandate")
    if state.status in _TERMINAL_MANDATE_STATUSES:
        raise ValueError("an executive decision cannot be applied to terminal state")
    if state.status is MandateStatus.NEEDS_HUMAN:
        raise ValueError(
            "an executive decision cannot be applied while human input is pending"
        )

    unknown_evidence_ids = set(decision.supporting_evidence_ids) - set(
        state.relevant_evidence_ids
    )
    if unknown_evidence_ids:
        unknown_ids = ", ".join(sorted(unknown_evidence_ids))
        raise ValueError(
            f"decision references unknown supporting evidence: {unknown_ids}"
        )

    if decision.decision_type is ExecutiveDecisionType.CONTINUE:
        return _apply_continue_decision(
            state, decision, objective, human_escalation
        )
    if decision.decision_type is ExecutiveDecisionType.SUCCESS:
        return _apply_terminal_decision(
            state,
            MandateStatus.SUCCEEDED,
            objective,
            human_escalation,
        )
    if decision.decision_type is ExecutiveDecisionType.STOP:
        return _apply_terminal_decision(
            state,
            MandateStatus.STOPPED,
            objective,
            human_escalation,
        )
    return _apply_human_escalation_decision(
        state, decision, objective, human_escalation
    )


def apply_objective_result(
    state: CompanyState,
    objective: Objective,
    evidence: tuple[Evidence, ...],
    state_update: CompanyStateUpdate,
) -> CompanyState:
    """Apply a terminal result for the currently active bounded objective."""

    if state.status is not MandateStatus.ACTIVE:
        raise ValueError("objective results require an active company state")
    if state.active_objective_id is None:
        raise ValueError("objective results require an active objective")
    if objective.id != state.active_objective_id:
        raise ValueError("completed objective does not match the active objective")
    if objective.mandate_id != state.mandate_id:
        raise ValueError("state and objective must belong to the same mandate")
    if objective.status not in _TERMINAL_OBJECTIVE_STATUSES:
        raise ValueError("completed objective must have a terminal status")

    supplied_evidence_ids: set[str] = set()
    for evidence_record in evidence:
        if evidence_record.mandate_id != state.mandate_id:
            raise ValueError("state and evidence must belong to the same mandate")
        if evidence_record.objective_id != state.active_objective_id:
            raise ValueError("execution evidence must identify the active objective")
        supplied_evidence_ids.add(evidence_record.id)

    known_evidence_ids = set(state.relevant_evidence_ids) | supplied_evidence_ids
    unknown_evidence_ids = set(state_update.relevant_evidence_ids) - known_evidence_ids
    if unknown_evidence_ids:
        unknown_ids = ", ".join(sorted(unknown_evidence_ids))
        raise ValueError(
            f"state update references unknown evidence: {unknown_ids}"
        )

    return CompanyState(
        mandate_id=state.mandate_id,
        status=MandateStatus.ACTIVE,
        summary=state_update.summary,
        active_objective_id=None,
        facts=state_update.facts,
        assumptions=state_update.assumptions,
        open_questions=state_update.open_questions,
        relevant_evidence_ids=state_update.relevant_evidence_ids,
        pending_human_escalation_id=None,
    )


def _apply_continue_decision(
    state: CompanyState,
    decision: ExecutiveDecision,
    objective: Optional[Objective],
    human_escalation: Optional[HumanEscalation],
) -> CompanyState:
    if objective is None:
        raise ValueError("a continue decision requires its objective")
    if human_escalation is not None:
        raise ValueError("a continue decision must not include a human escalation")
    if objective.id != decision.objective_id:
        raise ValueError("objective does not match the executive decision")
    if objective.mandate_id != state.mandate_id:
        raise ValueError("state and objective must belong to the same mandate")
    if objective.status is not ObjectiveStatus.PENDING:
        raise ValueError("a continue decision requires a pending objective")
    if state.active_objective_id is not None:
        raise ValueError("a second objective cannot be authorized while one is active")

    return replace(
        state,
        status=MandateStatus.ACTIVE,
        active_objective_id=objective.id,
        pending_human_escalation_id=None,
    )


def _apply_terminal_decision(
    state: CompanyState,
    status: MandateStatus,
    objective: Optional[Objective],
    human_escalation: Optional[HumanEscalation],
) -> CompanyState:
    if objective is not None or human_escalation is not None:
        raise ValueError("a terminal decision must not include related work")
    if state.active_objective_id is not None:
        raise ValueError("a terminal decision requires no active objective")

    return replace(
        state,
        status=status,
        active_objective_id=None,
        pending_human_escalation_id=None,
    )


def _apply_human_escalation_decision(
    state: CompanyState,
    decision: ExecutiveDecision,
    objective: Optional[Objective],
    human_escalation: Optional[HumanEscalation],
) -> CompanyState:
    if objective is not None:
        raise ValueError("a human escalation decision must not include an objective")
    if human_escalation is None:
        raise ValueError("a human escalation decision requires its escalation")
    if human_escalation.id != decision.human_escalation_id:
        raise ValueError("human escalation does not match the executive decision")
    if human_escalation.mandate_id != state.mandate_id:
        raise ValueError("state and human escalation must belong to the same mandate")
    if (
        human_escalation.objective_id is not None
        and state.active_objective_id is not None
        and human_escalation.objective_id != state.active_objective_id
    ):
        raise ValueError("human escalation does not match the active objective")

    return replace(
        state,
        status=MandateStatus.NEEDS_HUMAN,
        pending_human_escalation_id=human_escalation.id,
    )
