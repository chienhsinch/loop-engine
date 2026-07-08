import pytest

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
from loop_engine.executive_loop import (
    apply_executive_decision,
    apply_objective_result,
)


def make_state(
    *,
    active_objective_id=None,
    relevant_evidence_ids: tuple[str, ...] = (),
) -> CompanyState:
    return CompanyState(
        "mandate-1",
        MandateStatus.ACTIVE,
        "Initial company state",
        active_objective_id=active_objective_id,
        relevant_evidence_ids=relevant_evidence_ids,
    )


def make_objective(
    objective_id: str = "objective-1",
    *,
    mandate_id: str = "mandate-1",
    status: ObjectiveStatus = ObjectiveStatus.PENDING,
) -> Objective:
    return Objective(
        objective_id,
        mandate_id,
        f"Complete {objective_id}",
        f"{objective_id} is the next bounded outcome",
        status=status,
    )


def make_continue_decision(
    objective_id: str = "objective-1",
    *,
    mandate_id: str = "mandate-1",
    supporting_evidence_ids: tuple[str, ...] = (),
) -> ExecutiveDecision:
    return ExecutiveDecision(
        f"decision-{objective_id}",
        mandate_id,
        ExecutiveDecisionType.CONTINUE,
        f"Authorize {objective_id}",
        objective_id=objective_id,
        supporting_evidence_ids=supporting_evidence_ids,
    )


def test_continue_authorizes_pending_objective() -> None:
    state = make_state()
    objective = make_objective()
    decision = make_continue_decision(objective.id)

    result = apply_executive_decision(state, decision, objective)

    assert result.status is MandateStatus.ACTIVE
    assert result.active_objective_id == objective.id
    assert result.pending_human_escalation_id is None
    assert state.active_objective_id is None


def test_objective_completion_applies_evidence_and_replaces_snapshot() -> None:
    state = make_state(
        active_objective_id="objective-1",
        relevant_evidence_ids=("evidence-existing",),
    )
    objective = make_objective(status=ObjectiveStatus.SUCCEEDED)
    evidence = Evidence(
        "evidence-new",
        "mandate-1",
        "objective-worker",
        "The objective completion criteria passed",
        objective_id=objective.id,
    )
    update = CompanyStateUpdate(
        "The first objective completed",
        facts=("The completion criteria passed",),
        assumptions=("The result generalizes to the target segment",),
        open_questions=("Will the result hold at larger scale?",),
        relevant_evidence_ids=("evidence-existing", evidence.id),
    )

    result = apply_objective_result(state, objective, (evidence,), update)

    assert result.status is MandateStatus.ACTIVE
    assert result.active_objective_id is None
    assert result.pending_human_escalation_id is None
    assert result.summary == update.summary
    assert result.facts == update.facts
    assert result.assumptions == update.assumptions
    assert result.open_questions == update.open_questions
    assert result.relevant_evidence_ids == update.relevant_evidence_ids


def test_multiple_objective_cycles_can_end_in_success() -> None:
    state = make_state()

    objective_1 = make_objective("objective-1")
    state = apply_executive_decision(
        state, make_continue_decision(objective_1.id), objective_1
    )
    evidence_1 = Evidence(
        "evidence-1",
        "mandate-1",
        "stub-worker",
        "The first experiment completed",
        objective_id=objective_1.id,
    )
    state = apply_objective_result(
        state,
        make_objective("objective-1", status=ObjectiveStatus.SUCCEEDED),
        (evidence_1,),
        CompanyStateUpdate(
            "The first uncertainty is resolved",
            relevant_evidence_ids=(evidence_1.id,),
        ),
    )

    objective_2 = make_objective("objective-2")
    decision_2 = make_continue_decision(
        objective_2.id, supporting_evidence_ids=(evidence_1.id,)
    )
    state = apply_executive_decision(state, decision_2, objective_2)
    evidence_2 = Evidence(
        "evidence-2",
        "mandate-1",
        "stub-worker",
        "The second experiment met its threshold",
        objective_id=objective_2.id,
    )
    state = apply_objective_result(
        state,
        make_objective("objective-2", status=ObjectiveStatus.SUCCEEDED),
        (evidence_2,),
        CompanyStateUpdate(
            "All mandate success criteria are supported",
            relevant_evidence_ids=(evidence_1.id, evidence_2.id),
        ),
    )

    success = ExecutiveDecision(
        "decision-success",
        "mandate-1",
        ExecutiveDecisionType.SUCCESS,
        "Both experiments support mandate success",
        supporting_evidence_ids=(evidence_1.id, evidence_2.id),
    )
    state = apply_executive_decision(state, success)

    assert state.status is MandateStatus.SUCCEEDED
    assert state.active_objective_id is None


def test_stop_decision_stops_active_mandate_without_objective() -> None:
    state = make_state()
    decision = ExecutiveDecision(
        "decision-stop",
        "mandate-1",
        ExecutiveDecisionType.STOP,
        "Further pursuit is not justified",
    )

    result = apply_executive_decision(state, decision)

    assert result.status is MandateStatus.STOPPED
    assert result.active_objective_id is None
    assert result.pending_human_escalation_id is None


def test_human_escalation_pauses_mandate_and_retains_active_objective() -> None:
    state = make_state(active_objective_id="objective-1")
    escalation = HumanEscalation(
        "escalation-1",
        "mandate-1",
        "Should the mandate constraints be changed?",
        "The active objective cannot proceed within current authority",
        objective_id="objective-1",
    )
    decision = ExecutiveDecision(
        "decision-escalate",
        "mandate-1",
        ExecutiveDecisionType.HUMAN_ESCALATION,
        "Owner authority is required",
        human_escalation_id=escalation.id,
    )

    result = apply_executive_decision(
        state, decision, human_escalation=escalation
    )

    assert result.status is MandateStatus.NEEDS_HUMAN
    assert result.active_objective_id == "objective-1"
    assert result.pending_human_escalation_id == escalation.id


def test_decision_mandate_must_match_state() -> None:
    decision = ExecutiveDecision(
        "decision-stop",
        "other-mandate",
        ExecutiveDecisionType.STOP,
        "Stop",
    )

    with pytest.raises(ValueError, match="same mandate"):
        apply_executive_decision(make_state(), decision)


@pytest.mark.parametrize(
    "status", [MandateStatus.SUCCEEDED, MandateStatus.STOPPED]
)
def test_decisions_cannot_be_applied_to_terminal_state(
    status: MandateStatus,
) -> None:
    state = CompanyState("mandate-1", status, "Terminal")
    decision = ExecutiveDecision(
        "decision-stop",
        "mandate-1",
        ExecutiveDecisionType.STOP,
        "Stop again",
    )

    with pytest.raises(ValueError, match="terminal state"):
        apply_executive_decision(state, decision)


def test_decision_cannot_be_applied_while_human_input_is_pending() -> None:
    state = CompanyState(
        "mandate-1",
        MandateStatus.NEEDS_HUMAN,
        "Owner input is pending",
        pending_human_escalation_id="escalation-1",
    )
    decision = ExecutiveDecision(
        "decision-stop",
        "mandate-1",
        ExecutiveDecisionType.STOP,
        "Do not resolve escalation implicitly",
    )

    with pytest.raises(ValueError, match="human input is pending"):
        apply_executive_decision(state, decision)


def test_second_active_objective_cannot_be_authorized() -> None:
    state = make_state(active_objective_id="objective-existing")

    with pytest.raises(ValueError, match="second objective"):
        apply_executive_decision(
            state, make_continue_decision(), make_objective()
        )


def test_decision_supporting_evidence_must_be_known() -> None:
    decision = ExecutiveDecision(
        "decision-stop",
        "mandate-1",
        ExecutiveDecisionType.STOP,
        "Unsupported decision",
        supporting_evidence_ids=("evidence-unknown",),
    )

    with pytest.raises(ValueError, match="unknown supporting evidence"):
        apply_executive_decision(make_state(), decision)


def test_continue_objective_must_match_decision_and_mandate() -> None:
    with pytest.raises(ValueError, match="does not match"):
        apply_executive_decision(
            make_state(),
            make_continue_decision("objective-1"),
            make_objective("objective-2"),
        )

    with pytest.raises(ValueError, match="same mandate"):
        apply_executive_decision(
            make_state(),
            make_continue_decision("objective-1"),
            make_objective("objective-1", mandate_id="other-mandate"),
        )


def test_continue_requires_pending_objective() -> None:
    with pytest.raises(ValueError, match="pending objective"):
        apply_executive_decision(
            make_state(),
            make_continue_decision(),
            make_objective(status=ObjectiveStatus.IN_PROGRESS),
        )


def test_terminal_decision_requires_no_active_objective() -> None:
    decision = ExecutiveDecision(
        "decision-success",
        "mandate-1",
        ExecutiveDecisionType.SUCCESS,
        "Success",
    )

    with pytest.raises(ValueError, match="no active objective"):
        apply_executive_decision(
            make_state(active_objective_id="objective-1"), decision
        )


def test_human_escalation_must_match_decision_mandate_and_active_objective() -> None:
    decision = ExecutiveDecision(
        "decision-escalate",
        "mandate-1",
        ExecutiveDecisionType.HUMAN_ESCALATION,
        "Escalate",
        human_escalation_id="escalation-1",
    )

    with pytest.raises(ValueError, match="does not match the executive decision"):
        apply_executive_decision(
            make_state(),
            decision,
            human_escalation=HumanEscalation(
                "escalation-2", "mandate-1", "Question?", "Reason"
            ),
        )

    with pytest.raises(ValueError, match="same mandate"):
        apply_executive_decision(
            make_state(),
            decision,
            human_escalation=HumanEscalation(
                "escalation-1", "other-mandate", "Question?", "Reason"
            ),
        )

    with pytest.raises(ValueError, match="active objective"):
        apply_executive_decision(
            make_state(active_objective_id="objective-1"),
            decision,
            human_escalation=HumanEscalation(
                "escalation-1",
                "mandate-1",
                "Question?",
                "Reason",
                objective_id="objective-2",
            ),
        )


def test_completed_objective_must_be_active() -> None:
    update = CompanyStateUpdate("Updated")

    with pytest.raises(ValueError, match="require an active objective"):
        apply_objective_result(
            make_state(),
            make_objective(status=ObjectiveStatus.SUCCEEDED),
            (),
            update,
        )

    with pytest.raises(ValueError, match="does not match the active objective"):
        apply_objective_result(
            make_state(active_objective_id="objective-1"),
            make_objective("objective-2", status=ObjectiveStatus.SUCCEEDED),
            (),
            update,
        )


@pytest.mark.parametrize(
    "status", [ObjectiveStatus.PENDING, ObjectiveStatus.IN_PROGRESS]
)
def test_completed_objective_requires_terminal_status(
    status: ObjectiveStatus,
) -> None:
    with pytest.raises(ValueError, match="terminal status"):
        apply_objective_result(
            make_state(active_objective_id="objective-1"),
            make_objective(status=status),
            (),
            CompanyStateUpdate("Updated"),
        )


@pytest.mark.parametrize(
    "status",
    [
        ObjectiveStatus.SUCCEEDED,
        ObjectiveStatus.FAILED,
        ObjectiveStatus.CANCELLED,
        ObjectiveStatus.NEEDS_HUMAN,
    ],
)
def test_all_terminal_objective_results_return_control_to_active_mandate(
    status: ObjectiveStatus,
) -> None:
    result = apply_objective_result(
        make_state(active_objective_id="objective-1"),
        make_objective(status=status),
        (),
        CompanyStateUpdate("Executive must choose the next action"),
    )

    assert result.status is MandateStatus.ACTIVE
    assert result.active_objective_id is None


def test_objective_and_evidence_must_match_mandate() -> None:
    state = make_state(active_objective_id="objective-1")
    update = CompanyStateUpdate("Updated")

    with pytest.raises(ValueError, match="state and objective"):
        apply_objective_result(
            state,
            make_objective(
                mandate_id="other-mandate", status=ObjectiveStatus.SUCCEEDED
            ),
            (),
            update,
        )

    with pytest.raises(ValueError, match="state and evidence"):
        apply_objective_result(
            state,
            make_objective(status=ObjectiveStatus.SUCCEEDED),
            (
                Evidence(
                    "evidence-1",
                    "other-mandate",
                    "worker",
                    "Observation",
                    objective_id="objective-1",
                ),
            ),
            update,
        )


@pytest.mark.parametrize("objective_id", [None, "objective-2"])
def test_execution_evidence_must_identify_active_objective(objective_id) -> None:
    evidence = Evidence(
        "evidence-1",
        "mandate-1",
        "worker",
        "Observation",
        objective_id=objective_id,
    )

    with pytest.raises(ValueError, match="identify the active objective"):
        apply_objective_result(
            make_state(active_objective_id="objective-1"),
            make_objective(status=ObjectiveStatus.SUCCEEDED),
            (evidence,),
            CompanyStateUpdate("Updated"),
        )


def test_state_update_may_reference_only_known_or_supplied_evidence() -> None:
    state = make_state(
        active_objective_id="objective-1",
        relevant_evidence_ids=("evidence-known",),
    )
    evidence = Evidence(
        "evidence-new",
        "mandate-1",
        "worker",
        "Observation",
        objective_id="objective-1",
    )
    update = CompanyStateUpdate(
        "Updated",
        relevant_evidence_ids=(
            "evidence-known",
            evidence.id,
            "evidence-unknown",
        ),
    )

    with pytest.raises(ValueError, match="unknown evidence"):
        apply_objective_result(
            state,
            make_objective(status=ObjectiveStatus.SUCCEEDED),
            (evidence,),
            update,
        )
