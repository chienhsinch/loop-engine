import json
import shutil
from dataclasses import replace

import pytest

import loop_engine.company_store as company_store_module
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
from loop_engine.company_store import FileCompanyStore
from loop_engine.executive_loop import (
    apply_executive_decision,
    apply_objective_result,
)


def make_mandate(mandate_id: str = "mandate-1") -> Mandate:
    return Mandate(
        mandate_id,
        "Validate whether the product is worth building",
        constraints=("Remain within the research budget",),
        success_criteria=("Demand is supported by evidence",),
        stop_conditions=("Evidence disproves the core assumption",),
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
        "Interview target users",
        "Demand is the largest current uncertainty",
        status=status,
        constraints=("Do not collect payment details",),
        acceptance_criteria=("Complete five interviews",),
        expected_evidence=("Interview notes",),
    )


def save_mandate(store: FileCompanyStore, mandate_id: str = "mandate-1") -> Mandate:
    mandate = make_mandate(mandate_id)
    store.save_mandate(mandate)
    return mandate


def test_mandate_round_trip(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    mandate = make_mandate()

    store.save_mandate(mandate)

    loaded = store.load_mandate(mandate.id)
    assert loaded == mandate
    assert isinstance(loaded.constraints, tuple)


def test_objective_round_trip_preserves_enum_and_tuples(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective(status=ObjectiveStatus.IN_PROGRESS)

    store.save_objective(objective)

    loaded = store.load_objective(objective.mandate_id, objective.id)
    assert loaded == objective
    assert loaded.status is ObjectiveStatus.IN_PROGRESS
    assert isinstance(loaded.acceptance_criteria, tuple)


def test_executive_decision_round_trip_preserves_optional_fields(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    decision = ExecutiveDecision(
        "decision-1",
        "mandate-1",
        ExecutiveDecisionType.CONTINUE,
        "Authorize the first objective",
        objective_id="objective-1",
        supporting_evidence_ids=("evidence-1",),
    )

    store.save_decision(decision)

    loaded = store.load_decision(decision.mandate_id, decision.id)
    assert loaded == decision
    assert loaded.decision_type is ExecutiveDecisionType.CONTINUE
    assert loaded.human_escalation_id is None
    assert isinstance(loaded.supporting_evidence_ids, tuple)


def test_evidence_round_trip_preserves_optional_fields(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    evidence = Evidence(
        "evidence-1",
        "mandate-1",
        "customer-interview",
        "Four users described the same manual workaround",
        objective_id="objective-1",
        decision_id="decision-1",
    )

    store.save_evidence(evidence)

    assert store.load_evidence(evidence.mandate_id, evidence.id) == evidence


def test_human_escalation_round_trip_preserves_tuples(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    escalation = HumanEscalation(
        "escalation-1",
        "mandate-1",
        "Should the customer segment change?",
        "Evidence contradicts the initial segment assumption",
        objective_id="objective-1",
        evidence_ids=("evidence-1",),
        options=("Change segment", "Stop pursuit"),
    )

    store.save_escalation(escalation)

    loaded = store.load_escalation(escalation.mandate_id, escalation.id)
    assert loaded == escalation
    assert isinstance(loaded.evidence_ids, tuple)
    assert isinstance(loaded.options, tuple)


def test_current_company_state_round_trip_and_replacement(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective()
    evidence = Evidence(
        "evidence-1",
        "mandate-1",
        "worker",
        "The objective is blocked",
        objective_id=objective.id,
    )
    escalation = HumanEscalation(
        "escalation-1",
        "mandate-1",
        "Should the objective continue?",
        "Owner input is required",
        objective_id=objective.id,
        evidence_ids=(evidence.id,),
    )
    store.save_objective(objective)
    store.save_evidence(evidence)
    store.save_escalation(escalation)
    initial = CompanyState("mandate-1", MandateStatus.ACTIVE, "Initial")
    current = CompanyState(
        "mandate-1",
        MandateStatus.NEEDS_HUMAN,
        "Owner input is pending",
        active_objective_id=objective.id,
        facts=("Execution is blocked",),
        assumptions=("The owner can resolve the blocker",),
        open_questions=("Should constraints change?",),
        relevant_evidence_ids=(evidence.id,),
        pending_human_escalation_id=escalation.id,
    )

    store.save_state(initial)
    store.save_state(current)

    loaded = store.load_state("mandate-1")
    assert loaded == current
    assert isinstance(loaded.facts, tuple)
    state_payload = json.loads(
        (tmp_path / "mandates" / "mandate-1" / "state.json").read_text()
    )
    assert state_payload["active_objective_id"] == objective.id
    assert "objectives" not in state_payload
    assert "evidence" not in state_payload
    assert "decisions" not in state_payload
    assert "escalations" not in state_payload


def test_company_state_can_resume_across_objective_cycles(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    mandate = save_mandate(store)
    initial = CompanyState(mandate.id, MandateStatus.ACTIVE, "Initial state")
    store.save_state(initial)

    objective = make_objective()
    decision = ExecutiveDecision(
        "decision-1",
        mandate.id,
        ExecutiveDecisionType.CONTINUE,
        "Authorize customer interviews",
        objective_id=objective.id,
    )
    active = apply_executive_decision(initial, decision, objective)
    store.save_objective(objective)
    store.save_decision(decision)
    store.save_state(active)

    resumed_store = FileCompanyStore(tmp_path)
    resumed_state = resumed_store.load_state(mandate.id)
    resumed_objective = resumed_store.load_objective(mandate.id, objective.id)
    assert resumed_state.active_objective_id == objective.id
    assert resumed_objective == objective

    completed_objective = replace(
        resumed_objective, status=ObjectiveStatus.SUCCEEDED
    )
    evidence = Evidence(
        "evidence-1",
        mandate.id,
        "stub-worker",
        "Five customer interviews completed",
        objective_id=objective.id,
    )
    updated = apply_objective_result(
        resumed_state,
        completed_objective,
        (evidence,),
        CompanyStateUpdate(
            "Demand interviews completed",
            facts=("Five interviews completed",),
            relevant_evidence_ids=(evidence.id,),
        ),
    )
    resumed_store.save_evidence(evidence)
    resumed_store.save_state(updated)

    continued_store = FileCompanyStore(tmp_path)
    continued_state = continued_store.load_state(mandate.id)
    assert continued_state.status is MandateStatus.ACTIVE
    assert continued_state.active_objective_id is None
    assert continued_store.load_evidence(mandate.id, evidence.id) == evidence

    next_objective = make_objective("objective-2")
    next_decision = ExecutiveDecision(
        "decision-2",
        mandate.id,
        ExecutiveDecisionType.CONTINUE,
        "Use the interview evidence to test willingness to pay",
        objective_id=next_objective.id,
        supporting_evidence_ids=(evidence.id,),
    )
    next_state = apply_executive_decision(
        continued_state, next_decision, next_objective
    )
    continued_store.save_objective(next_objective)
    continued_store.save_decision(next_decision)
    continued_store.save_state(next_state)

    assert FileCompanyStore(tmp_path).load_state(
        mandate.id
    ).active_objective_id == next_objective.id


def test_human_escalation_can_resume(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    mandate = save_mandate(store)
    objective = make_objective()
    store.save_objective(objective)
    active = CompanyState(
        mandate.id,
        MandateStatus.ACTIVE,
        "Objective is active",
        active_objective_id=objective.id,
    )
    store.save_state(active)
    escalation = HumanEscalation(
        "escalation-1",
        mandate.id,
        "May the executive broaden the customer segment?",
        "The current segment is too small",
        objective_id=objective.id,
    )
    decision = ExecutiveDecision(
        "decision-escalate",
        mandate.id,
        ExecutiveDecisionType.HUMAN_ESCALATION,
        "Owner authority is required",
        human_escalation_id=escalation.id,
    )
    needs_human = apply_executive_decision(
        active, decision, human_escalation=escalation
    )
    store.save_escalation(escalation)
    store.save_decision(decision)
    store.save_state(needs_human)

    resumed_store = FileCompanyStore(tmp_path)
    resumed_state = resumed_store.load_state(mandate.id)

    assert resumed_state.status is MandateStatus.NEEDS_HUMAN
    assert resumed_state.pending_human_escalation_id == escalation.id
    assert resumed_store.load_escalation(mandate.id, escalation.id) == escalation


@pytest.mark.parametrize(
    ("method_name", "record"),
    [
        (
            "save_state",
            CompanyState("mandate-1", MandateStatus.ACTIVE, "Initial"),
        ),
        ("save_objective", make_objective()),
        (
            "save_decision",
            ExecutiveDecision(
                "decision-1",
                "mandate-1",
                ExecutiveDecisionType.STOP,
                "Stop",
            ),
        ),
        (
            "save_evidence",
            Evidence("evidence-1", "mandate-1", "source", "observation"),
        ),
        (
            "save_escalation",
            HumanEscalation(
                "escalation-1", "mandate-1", "Question?", "Reason"
            ),
        ),
    ],
)
def test_company_records_require_existing_mandate(
    tmp_path, method_name: str, record
) -> None:
    store = FileCompanyStore(tmp_path)

    with pytest.raises(FileNotFoundError, match="mandate"):
        getattr(store, method_name)(record)


def test_missing_required_records_fail_explicitly(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)

    with pytest.raises(FileNotFoundError, match="mandate"):
        store.load_mandate("missing")

    save_mandate(store)
    with pytest.raises(FileNotFoundError, match="company state"):
        store.load_state("mandate-1")


def test_immutable_record_save_is_idempotent_but_rejects_collision(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective()
    store.save_objective(objective)

    store.save_objective(objective)

    with pytest.raises(FileExistsError, match="different content"):
        store.save_objective(replace(objective, outcome="Different outcome"))


def test_malformed_json_fails_explicitly(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    mandate_path = tmp_path / "mandates" / "mandate-1" / "mandate.json"
    mandate_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="malformed JSON"):
        store.load_mandate("mandate-1")


def test_invalid_serialized_enum_fails_explicitly(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective()
    store.save_objective(objective)
    objective_path = (
        tmp_path
        / "mandates"
        / "mandate-1"
        / "objectives"
        / "objective-1.json"
    )
    payload = json.loads(objective_path.read_text(encoding="utf-8"))
    payload["status"] = "unknown"
    objective_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid objective record"):
        store.load_objective("mandate-1", "objective-1")


@pytest.mark.parametrize(
    ("collection", "filename", "identity_field", "load_method"),
    [
        (None, "mandate.json", "id", "load_mandate"),
        ("objectives", "objective-1.json", "id", "load_objective"),
        ("decisions", "decision-1.json", "id", "load_decision"),
        ("evidence", "evidence-1.json", "id", "load_evidence"),
        ("escalations", "escalation-1.json", "id", "load_escalation"),
    ],
)
def test_load_rejects_stored_record_identity_mismatch(
    tmp_path,
    collection,
    filename: str,
    identity_field: str,
    load_method: str,
) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective()
    evidence = Evidence(
        "evidence-1",
        "mandate-1",
        "worker",
        "Observation",
        objective_id=objective.id,
    )
    escalation = HumanEscalation(
        "escalation-1",
        "mandate-1",
        "Question?",
        "Reason",
        objective_id=objective.id,
        evidence_ids=(evidence.id,),
    )
    decision = ExecutiveDecision(
        "decision-1",
        "mandate-1",
        ExecutiveDecisionType.CONTINUE,
        "Continue",
        objective_id=objective.id,
        supporting_evidence_ids=(evidence.id,),
    )
    store.save_objective(objective)
    store.save_evidence(evidence)
    store.save_escalation(escalation)
    store.save_decision(decision)

    record_path = tmp_path / "mandates" / "mandate-1"
    if collection is not None:
        record_path /= collection
    record_path /= filename
    payload = json.loads(record_path.read_text(encoding="utf-8"))
    payload[identity_field] = "tampered-id"
    record_path.write_text(json.dumps(payload), encoding="utf-8")

    loader = getattr(store, load_method)
    load_args = ("mandate-1",)
    if load_method != "load_mandate":
        load_args += (
            "objective-1"
            if load_method == "load_objective"
            else filename.removesuffix(".json"),
        )

    with pytest.raises(ValueError, match="does not match the requested ID"):
        loader(*load_args)


def test_state_reference_validation_rejects_tampered_objective_id(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective()
    store.save_objective(objective)
    objective_path = (
        tmp_path
        / "mandates"
        / "mandate-1"
        / "objectives"
        / "objective-1.json"
    )
    payload = json.loads(objective_path.read_text(encoding="utf-8"))
    payload["id"] = "tampered-id"
    objective_path.write_text(json.dumps(payload), encoding="utf-8")
    state = CompanyState(
        "mandate-1",
        MandateStatus.ACTIVE,
        "Objective is active",
        active_objective_id=objective.id,
    )

    with pytest.raises(ValueError, match="does not match the requested ID"):
        store.save_state(state)


def test_state_rejects_missing_objective_reference(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    state = CompanyState(
        "mandate-1",
        MandateStatus.ACTIVE,
        "Objective is active",
        active_objective_id="missing-objective",
    )

    with pytest.raises(ValueError, match="missing active objective"):
        store.save_state(state)


def test_state_rejects_missing_evidence_reference(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    state = CompanyState(
        "mandate-1",
        MandateStatus.ACTIVE,
        "Evidence is relevant",
        relevant_evidence_ids=("missing-evidence",),
    )

    with pytest.raises(ValueError, match="missing evidence"):
        store.save_state(state)


def test_state_rejects_missing_escalation_reference(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    state = CompanyState(
        "mandate-1",
        MandateStatus.NEEDS_HUMAN,
        "Owner input is pending",
        pending_human_escalation_id="missing-escalation",
    )

    with pytest.raises(ValueError, match="missing human escalation"):
        store.save_state(state)


def test_state_rejects_cross_mandate_reference(tmp_path) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store, "mandate-1")
    save_mandate(store, "mandate-2")
    other_objective = make_objective(mandate_id="mandate-2")
    store.save_objective(other_objective)
    source = (
        tmp_path
        / "mandates"
        / "mandate-2"
        / "objectives"
        / "objective-1.json"
    )
    destination = (
        tmp_path
        / "mandates"
        / "mandate-1"
        / "objectives"
        / "objective-1.json"
    )
    destination.parent.mkdir(parents=True)
    shutil.copyfile(source, destination)
    state = CompanyState(
        "mandate-1",
        MandateStatus.ACTIVE,
        "Cross-mandate objective reference",
        active_objective_id=other_objective.id,
    )

    with pytest.raises(ValueError, match="different mandate"):
        store.save_state(state)


def test_failed_atomic_state_replace_preserves_previous_snapshot(
    tmp_path, monkeypatch
) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    initial = CompanyState("mandate-1", MandateStatus.ACTIVE, "Initial")
    store.save_state(initial)

    def fail_replace(source, destination) -> None:
        raise OSError("simulated replace failure")

    monkeypatch.setattr(company_store_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated replace failure"):
        store.save_state(
            CompanyState("mandate-1", MandateStatus.ACTIVE, "Updated")
        )

    assert FileCompanyStore(tmp_path).load_state("mandate-1") == initial
    mandate_dir = tmp_path / "mandates" / "mandate-1"
    assert tuple(mandate_dir.glob(".state.json.*.tmp")) == ()


def test_failed_immutable_install_leaves_no_partial_record(
    tmp_path, monkeypatch
) -> None:
    store = FileCompanyStore(tmp_path)
    save_mandate(store)
    objective = make_objective()

    def fail_link(source, destination) -> None:
        raise OSError("simulated immutable install failure")

    monkeypatch.setattr(company_store_module.os, "link", fail_link)
    with pytest.raises(OSError, match="simulated immutable install failure"):
        store.save_objective(objective)

    objective_dir = tmp_path / "mandates" / "mandate-1" / "objectives"
    assert not (objective_dir / "objective-1.json").exists()
    assert tuple(objective_dir.glob(".objective-1.json.*.tmp")) == ()
