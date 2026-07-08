from dataclasses import FrozenInstanceError, fields

import pytest

from loop_engine.company_models import (
    CompanyState,
    CompanyStateUpdate,
    Evidence,
    ExecutiveDecision,
    ExecutiveDecisionType,
    HumanEscalation,
    Mandate,
    MandateStatus,
    Objective,
    ObjectiveStatus,
)
from loop_engine.models import Goal, Task


def make_objective() -> Objective:
    return Objective(
        "objective-1",
        "mandate-1",
        "Validate demand for the product",
        "Demand evidence is the largest current uncertainty",
        acceptance_criteria=("Five target users complete interviews",),
        expected_evidence=("Interview notes",),
    )


def test_company_domain_models_can_be_constructed() -> None:
    mandate = Mandate(
        "mandate-1",
        "Determine whether the product is worth building",
        constraints=("Do not accept payments",),
        success_criteria=("Demand is supported by customer evidence",),
        stop_conditions=("The validation budget is exhausted",),
    )
    objective = make_objective()
    evidence = Evidence(
        "evidence-1",
        mandate.id,
        "customer-interview",
        "Four of five interviewees currently use a manual workaround",
        objective_id=objective.id,
    )
    escalation = HumanEscalation(
        "escalation-1",
        mandate.id,
        "Should validation continue with a different customer segment?",
        "The initial segment did not meet the demand threshold",
        objective_id=objective.id,
        evidence_ids=(evidence.id,),
        options=("Test another segment", "Stop validation"),
    )
    decision = ExecutiveDecision(
        "decision-1",
        mandate.id,
        ExecutiveDecisionType.CONTINUE,
        "Customer interviews are the next bounded step",
        objective_id=objective.id,
        supporting_evidence_ids=(evidence.id,),
    )
    state = CompanyState(
        mandate.id,
        MandateStatus.ACTIVE,
        "Demand remains unvalidated",
        active_objective_id=objective.id,
        assumptions=("The initial customer segment is reachable",),
        open_questions=("Will users pay to replace the workaround?",),
        relevant_evidence_ids=(evidence.id,),
    )
    state_update = CompanyStateUpdate(
        "Demand evidence was collected",
        facts=("Four interviewees use a workaround",),
        relevant_evidence_ids=(evidence.id,),
    )

    assert mandate.success_criteria == (
        "Demand is supported by customer evidence",
    )
    assert objective.status is ObjectiveStatus.PENDING
    assert evidence.source == "customer-interview"
    assert escalation.evidence_ids == (evidence.id,)
    assert decision.objective_id == objective.id
    assert decision.supporting_evidence_ids == (evidence.id,)
    assert state.status is MandateStatus.ACTIVE
    assert state_update.relevant_evidence_ids == (evidence.id,)


def test_company_state_update_contains_only_snapshot_fields() -> None:
    assert tuple(field.name for field in fields(CompanyStateUpdate)) == (
        "summary",
        "facts",
        "assumptions",
        "open_questions",
        "relevant_evidence_ids",
    )


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (lambda: Mandate("", "Description"), "mandate id"),
        (lambda: Mandate("mandate-1", "  "), "mandate description"),
        (
            lambda: Objective("", "mandate-1", "Outcome", "Rationale"),
            "objective id",
        ),
        (
            lambda: Objective("objective-1", "", "Outcome", "Rationale"),
            "mandate_id",
        ),
        (
            lambda: Objective("objective-1", "mandate-1", "", "Rationale"),
            "objective outcome",
        ),
        (
            lambda: Objective("objective-1", "mandate-1", "Outcome", ""),
            "objective rationale",
        ),
        (
            lambda: Evidence("", "mandate-1", "source", "observation"),
            "evidence id",
        ),
        (
            lambda: Evidence("evidence-1", "", "source", "observation"),
            "mandate_id",
        ),
        (
            lambda: Evidence("evidence-1", "mandate-1", "", "observation"),
            "evidence source",
        ),
        (
            lambda: Evidence("evidence-1", "mandate-1", "source", ""),
            "evidence observation",
        ),
        (
            lambda: ExecutiveDecision(
                "", "mandate-1", ExecutiveDecisionType.SUCCESS, "Complete"
            ),
            "executive decision id",
        ),
        (
            lambda: HumanEscalation(
                "escalation-1", "mandate-1", "", "Reason"
            ),
            "human escalation question",
        ),
        (
            lambda: CompanyState("", MandateStatus.ACTIVE, "Summary"),
            "mandate_id",
        ),
        (
            lambda: CompanyState("mandate-1", MandateStatus.ACTIVE, ""),
            "company state summary",
        ),
        (
            lambda: CompanyStateUpdate(""),
            "company state update summary",
        ),
    ],
)
def test_empty_required_fields_are_rejected(factory, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


def test_continue_decision_requires_and_identifies_objective() -> None:
    decision = ExecutiveDecision(
        "decision-1",
        "mandate-1",
        ExecutiveDecisionType.CONTINUE,
        "Authorize the next bounded objective",
        objective_id="objective-1",
    )

    assert decision.objective_id == "objective-1"
    assert decision.supporting_evidence_ids == ()

    with pytest.raises(ValueError, match="requires an objective_id"):
        ExecutiveDecision(
            "decision-2",
            "mandate-1",
            ExecutiveDecisionType.CONTINUE,
            "Continue without identifying work",
        )


@pytest.mark.parametrize(
    "decision_type",
    [ExecutiveDecisionType.SUCCESS, ExecutiveDecisionType.STOP],
)
def test_terminal_decisions_do_not_require_objectives(
    decision_type: ExecutiveDecisionType,
) -> None:
    decision = ExecutiveDecision(
        "decision-1",
        "mandate-1",
        decision_type,
        "The mandate has reached a terminal outcome",
    )

    assert decision.objective_id is None


@pytest.mark.parametrize(
    "decision_type",
    [ExecutiveDecisionType.SUCCESS, ExecutiveDecisionType.STOP],
)
def test_terminal_decisions_reject_objectives(
    decision_type: ExecutiveDecisionType,
) -> None:
    with pytest.raises(ValueError, match="must not identify an objective"):
        ExecutiveDecision(
            "decision-1",
            "mandate-1",
            decision_type,
            "Terminal decisions do not authorize more work",
            objective_id="objective-1",
        )


def test_human_escalation_decision_requires_escalation_without_objective() -> None:
    decision = ExecutiveDecision(
        "decision-1",
        "mandate-1",
        ExecutiveDecisionType.HUMAN_ESCALATION,
        "The owner must choose whether to broaden the mandate",
        human_escalation_id="escalation-1",
    )

    assert decision.human_escalation_id == "escalation-1"
    assert decision.objective_id is None

    with pytest.raises(ValueError, match="requires a human_escalation_id"):
        ExecutiveDecision(
            "decision-2",
            "mandate-1",
            ExecutiveDecisionType.HUMAN_ESCALATION,
            "Escalate without an escalation record",
        )


def test_continue_and_escalation_decisions_reject_conflicting_references() -> None:
    with pytest.raises(ValueError, match="must not identify a human escalation"):
        ExecutiveDecision(
            "decision-1",
            "mandate-1",
            ExecutiveDecisionType.CONTINUE,
            "A decision cannot continue and escalate",
            objective_id="objective-1",
            human_escalation_id="escalation-1",
        )

    with pytest.raises(ValueError, match="must not authorize an objective"):
        ExecutiveDecision(
            "decision-2",
            "mandate-1",
            ExecutiveDecisionType.HUMAN_ESCALATION,
            "An escalation cannot authorize new work",
            objective_id="objective-1",
            human_escalation_id="escalation-1",
        )


def test_terminal_company_state_rejects_active_objective() -> None:
    with pytest.raises(ValueError, match="terminal company state"):
        CompanyState(
            "mandate-1",
            MandateStatus.SUCCEEDED,
            "The mandate succeeded",
            active_objective_id="objective-1",
        )


def test_needs_human_company_state_requires_pending_escalation() -> None:
    with pytest.raises(ValueError, match="requires a pending_human_escalation_id"):
        CompanyState(
            "mandate-1",
            MandateStatus.NEEDS_HUMAN,
            "Owner input is required",
        )

    with pytest.raises(ValueError, match="pending_human_escalation_id"):
        CompanyState(
            "mandate-1",
            MandateStatus.NEEDS_HUMAN,
            "Owner input is required",
            pending_human_escalation_id="  ",
        )


def test_needs_human_company_state_may_retain_active_objective() -> None:
    state = CompanyState(
        "mandate-1",
        MandateStatus.NEEDS_HUMAN,
        "The active objective is blocked pending owner input",
        active_objective_id="objective-1",
        pending_human_escalation_id="escalation-1",
    )

    assert state.active_objective_id == "objective-1"
    assert state.pending_human_escalation_id == "escalation-1"


@pytest.mark.parametrize(
    "status",
    [MandateStatus.ACTIVE, MandateStatus.SUCCEEDED, MandateStatus.STOPPED],
)
def test_non_escalated_company_states_reject_pending_escalation(
    status: MandateStatus,
) -> None:
    with pytest.raises(ValueError, match="only a needs-human company state"):
        CompanyState(
            "mandate-1",
            status,
            "No owner input is pending",
            pending_human_escalation_id="escalation-1",
        )


@pytest.mark.parametrize(
    ("factory", "match"),
    [
        (
            lambda: Objective(
                "objective-1",
                "mandate-1",
                "Outcome",
                "Rationale",
                status="pending",
            ),
            "ObjectiveStatus",
        ),
        (
            lambda: ExecutiveDecision(
                "decision-1",
                "mandate-1",
                "continue",
                "Rationale",
                objective_id="objective-1",
            ),
            "ExecutiveDecisionType",
        ),
        (
            lambda: CompanyState("mandate-1", "active", "Summary"),
            "MandateStatus",
        ),
    ],
)
def test_status_and_decision_fields_require_their_enum_types(
    factory, match: str
) -> None:
    with pytest.raises(ValueError, match=match):
        factory()


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Mandate("mandate-1", "Description", constraints=["mutable"]),
        lambda: Mandate(
            "mandate-1", "Description", success_criteria=["mutable"]
        ),
        lambda: Mandate(
            "mandate-1", "Description", stop_conditions=["mutable"]
        ),
        lambda: Objective(
            "objective-1",
            "mandate-1",
            "Outcome",
            "Rationale",
            constraints=["mutable"],
        ),
        lambda: Objective(
            "objective-1",
            "mandate-1",
            "Outcome",
            "Rationale",
            acceptance_criteria=["mutable"],
        ),
        lambda: Objective(
            "objective-1",
            "mandate-1",
            "Outcome",
            "Rationale",
            expected_evidence=["mutable"],
        ),
        lambda: ExecutiveDecision(
            "decision-1",
            "mandate-1",
            ExecutiveDecisionType.SUCCESS,
            "Rationale",
            supporting_evidence_ids=["mutable"],
        ),
        lambda: HumanEscalation(
            "escalation-1",
            "mandate-1",
            "Question?",
            "Reason",
            evidence_ids=["mutable"],
        ),
        lambda: HumanEscalation(
            "escalation-1",
            "mandate-1",
            "Question?",
            "Reason",
            options=["mutable"],
        ),
        lambda: CompanyState(
            "mandate-1", MandateStatus.ACTIVE, "Summary", facts=["mutable"]
        ),
        lambda: CompanyState(
            "mandate-1",
            MandateStatus.ACTIVE,
            "Summary",
            assumptions=["mutable"],
        ),
        lambda: CompanyState(
            "mandate-1",
            MandateStatus.ACTIVE,
            "Summary",
            open_questions=["mutable"],
        ),
        lambda: CompanyState(
            "mandate-1",
            MandateStatus.ACTIVE,
            "Summary",
            relevant_evidence_ids=["mutable"],
        ),
        lambda: CompanyStateUpdate("Summary", facts=["mutable"]),
        lambda: CompanyStateUpdate("Summary", assumptions=["mutable"]),
        lambda: CompanyStateUpdate("Summary", open_questions=["mutable"]),
        lambda: CompanyStateUpdate(
            "Summary", relevant_evidence_ids=["mutable"]
        ),
    ],
)
def test_tuple_valued_fields_reject_mutable_lists(factory) -> None:
    with pytest.raises(ValueError, match="must be a tuple"):
        factory()


def test_executive_decision_rejects_empty_supporting_evidence_id() -> None:
    with pytest.raises(ValueError, match="supporting evidence id"):
        ExecutiveDecision(
            "decision-1",
            "mandate-1",
            ExecutiveDecisionType.SUCCESS,
            "Rationale",
            supporting_evidence_ids=(" ",),
        )


def test_evidence_is_a_record_not_an_accepted_company_fact() -> None:
    evidence = Evidence(
        "evidence-1",
        "mandate-1",
        "worker-report",
        "The worker reports that demand was validated",
    )
    state = CompanyState(
        "mandate-1",
        MandateStatus.ACTIVE,
        "The worker claim has not been accepted as a company fact",
        relevant_evidence_ids=(evidence.id,),
    )

    assert state.relevant_evidence_ids == (evidence.id,)
    assert state.facts == ()


def test_company_models_are_immutable() -> None:
    objective = make_objective()

    with pytest.raises(FrozenInstanceError):
        objective.status = ObjectiveStatus.IN_PROGRESS


def test_objective_is_separate_from_execution_models() -> None:
    objective = make_objective()

    assert not isinstance(objective, Task)
    assert not isinstance(objective, Goal)
    assert not hasattr(objective, "goal_id")
