import json
import subprocess
from pathlib import Path

import pytest

import loop_engine.codex_durable_run as durable
from loop_engine.codex_durable_run import (
    CHECKPOINT_NAME,
    CodexDurableRunError,
    run_durable_cycles,
)
from loop_engine.company_models import (
    Evidence,
    HumanEscalation,
    MandateStatus,
    Objective,
)
from loop_engine.company_store import FileCompanyStore


def proposal(outcome="Compare candidates", kind="continue"):
    return {
        "decision_type": kind, "rationale": f"Choose {kind}",
        "supporting_evidence_ids": [],
        "objective": ({"outcome": outcome, "rationale": "Reduce uncertainty",
                       "constraints": ["Synthetic only"],
                       "acceptance_criteria": ["Create an artifact"],
                       "expected_evidence": ["Written analysis"]} if kind == "continue" else None),
        "human_escalation": None,
    }


def execution(cycle):
    return {"summary": f"Completed cycle {cycle}", "observations": [f"Observation {cycle}"],
            "artifact_paths": [f"artifacts/cycle-{cycle}/result.md"], "facts": [],
            "assumptions": [f"Assumption {cycle}"], "open_questions": [f"Question {cycle}"]}


class FakeCodex:
    def __init__(self, proposals):
        self.proposals = iter(proposals); self.calls = []; self.commands = []

    def __call__(self, command, prompt):
        self.calls.append(prompt)
        self.commands.append(command)
        output = Path(command[command.index("--output-last-message") + 1])
        if "executive" in prompt.lower() and "Select exactly one" in prompt:
            payload = next(self.proposals)
        else:
            cycle = int(output.stem.split("-")[-1])
            artifact = output.parents[1] / "artifacts" / f"cycle-{cycle}" / "result.md"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text(f"cycle {cycle}", encoding="utf-8")
            payload = execution(cycle)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_phase6_host_creates_cycle_directory_before_execution(tmp_path):
    class AssertExisting(FakeCodex):
        def __call__(self, command, prompt):
            output = Path(command[command.index("--output-last-message") + 1])
            if output.name == "execution-1.json":
                cycle = tmp_path / "execution-workspace/artifacts/cycle-1"
                assert cycle.is_dir()
                assert list(cycle.iterdir()) == []
                assert "already exists" in prompt
                assert "preserve its inherited permissions" in prompt
            return super().__call__(command, prompt)

    result = run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=AssertExisting([proposal(), proposal("Next")]),
    )
    assert result.executed_objective_ids == ("objective-1",)
    assert (tmp_path / "execution-workspace/artifacts/cycle-1/result.md").is_file()


def test_existing_empty_current_cycle_directory_is_accepted(tmp_path):
    cycle = tmp_path / "execution-workspace/artifacts/cycle-1"
    cycle.mkdir(parents=True)
    result = run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Next")]),
    )
    assert result.executed_objective_ids == ("objective-1",)


def test_regular_file_at_cycle_directory_path_is_rejected(tmp_path):
    cycle = tmp_path / "execution-workspace/artifacts/cycle-1"
    cycle.parent.mkdir(parents=True)
    cycle.write_text("not a directory", encoding="utf-8")
    with pytest.raises(CodexDurableRunError, match="cycle-1 must be a directory"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal()]),
        )


def test_symlink_at_cycle_directory_path_is_rejected(tmp_path):
    artifacts = tmp_path / "execution-workspace/artifacts"
    target = tmp_path / "cycle-target"
    artifacts.mkdir(parents=True)
    target.mkdir()
    try:
        (artifacts / "cycle-1").symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    with pytest.raises(CodexDurableRunError, match="cycle-1 must not be a symlink"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal()]),
        )


def test_unreadable_generated_artifact_preserves_checkpoint_and_evidence(
    tmp_path, monkeypatch
):
    original_is_file = Path.is_file

    def deny_result(path):
        if path.name == "result.md":
            raise PermissionError(5, "Access is denied", str(path))
        return original_is_file(path)

    monkeypatch.setattr(Path, "is_file", deny_result)
    with pytest.raises(CodexDurableRunError) as captured:
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal()]),
        )
    message = str(captured.value)
    assert "execution-workspace/artifacts/cycle-1/result.md" in message
    assert "unreadable" in message
    assert "native Windows Codex sandbox ACLs may be the cause" in message
    assert "WinError" not in message
    checkpoint = json.loads((tmp_path / CHECKPOINT_NAME).read_text())
    assert checkpoint["stage"] == "objective_active"
    assert checkpoint["protected_file_hashes"] is not None
    store = FileCompanyStore(tmp_path / "company-store")
    with pytest.raises(FileNotFoundError):
        store.load_evidence(durable.MANDATE_ID, "evidence-1-1")


def test_execution_workspace_is_physically_separate_and_inputs_match(tmp_path):
    fake = FakeCodex([proposal("Objective one"), proposal("Objective two")])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)

    executive = next(command for command in fake.commands if command[command.index("--sandbox") + 1] == "read-only")
    execution_command = next(command for command in fake.commands if command[command.index("--sandbox") + 1] == "workspace-write")
    assert Path(executive[executive.index("--cd") + 1]) == tmp_path.resolve()
    assert Path(execution_command[execution_command.index("--cd") + 1]) == (tmp_path / "execution-workspace").resolve()
    assert not (tmp_path / "execution-workspace/company-store").exists()
    assert not (tmp_path / "execution-workspace" / CHECKPOINT_NAME).exists()
    assert not (tmp_path / "execution-workspace/candidate-brief.md").exists()
    assert (tmp_path / "candidate-brief.md").read_bytes() == (
        tmp_path / "execution-workspace/authorized-inputs/candidate-brief.md"
    ).read_bytes()
    evidence = FileCompanyStore(tmp_path / "company-store").load_evidence(
        durable.MANDATE_ID, "evidence-1-1"
    )
    assert "execution-workspace/artifacts/cycle-1/result.md" in evidence.source
    assert "authorized-inputs/candidate-brief.md" in next(
        prompt for prompt in fake.calls if "Execute only" in prompt
    )


def test_differing_authorized_input_is_rejected_without_overwrite(tmp_path):
    authorized = tmp_path / "execution-workspace/authorized-inputs/candidate-brief.md"
    authorized.parent.mkdir(parents=True)
    authorized.write_bytes(b"user content")
    with pytest.raises(CodexDurableRunError, match="authorized candidate-brief.md differs"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))
    assert authorized.read_bytes() == b"user content"


def test_legacy_phase6_layout_is_rejected_explicitly(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(kind="stop")]),
    )
    legacy = tmp_path / ".codex-output/execution-1.json"
    legacy.parent.mkdir(exist_ok=True)
    legacy.write_text("{}", encoding="utf-8")
    with pytest.raises(CodexDurableRunError, match="legacy Phase 6 workspace layout"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_two_process_style_invocations_resume_without_repeating(tmp_path):
    fake1 = FakeCodex([proposal("Objective one"), proposal("Objective two")])
    first = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake1)
    assert first.executed_objective_ids == ("objective-1",)
    assert first.next_active_objective_id == "objective-2"
    assert first.ending_stage == "objective_active"

    fake2 = FakeCodex([proposal("Objective three")])
    second = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake2)
    assert second.starting_stage == "objective_active"
    assert second.executed_objective_ids == ("objective-2",)
    assert second.next_active_objective_id == "objective-3"
    assert not any("Cycle: 2" in call for call in fake2.calls)
    assert (tmp_path / "execution-workspace/.codex-output/execution-1.json").is_file()
    assert (tmp_path / "execution-workspace/artifacts/cycle-2/result.md").is_file()


def test_stop_decision_is_durable_and_rerun_is_quiet(tmp_path):
    fake = FakeCodex([proposal(kind="stop")])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert result.ending_stage == "terminal"
    assert result.mandate_status is MandateStatus.STOPPED
    quiet = FakeCodex([])
    rerun = run_durable_cycles(tmp_path, max_cycles=1, command_function=quiet)
    assert rerun.ending_stage == "terminal" and quiet.calls == []


def test_human_escalation_is_durable_and_rerun_is_quiet(tmp_path):
    value = proposal(kind="human_escalation")
    value["human_escalation"] = {"question": "Choose?", "reason": "Owner judgment",
                                 "evidence_ids": [], "options": ["A", "B"]}
    fake = FakeCodex([value])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert result.ending_stage == "needs_human"
    assert result.pending_escalation_id == "escalation-1"
    quiet = FakeCodex([])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=quiet)
    assert quiet.calls == []


def test_terminal_resume_does_not_resolve_or_invoke_codex(tmp_path, monkeypatch):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(kind="stop")]),
    )
    monkeypatch.setattr(durable.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        durable, "_run_subprocess",
        lambda command, prompt: pytest.fail("Codex subprocess must not run"),
    )

    result = run_durable_cycles(tmp_path, max_cycles=1)

    assert result.ending_stage == "terminal"


def test_needs_human_resume_does_not_resolve_or_invoke_codex(tmp_path, monkeypatch):
    value = proposal(kind="human_escalation")
    value["human_escalation"] = {
        "question": "Choose?", "reason": "Owner judgment",
        "evidence_ids": [], "options": ["A", "B"],
    }
    run_durable_cycles(
        tmp_path, max_cycles=1, command_function=FakeCodex([value])
    )
    monkeypatch.setattr(durable.shutil, "which", lambda name: None)
    monkeypatch.setattr(
        durable, "_run_subprocess",
        lambda command, prompt: pytest.fail("Codex subprocess must not run"),
    )

    result = run_durable_cycles(tmp_path, max_cycles=1)

    assert result.ending_stage == "needs_human"


def test_success_at_executive_cycle_one_is_rejected(tmp_path):
    with pytest.raises(
        CodexDurableRunError,
        match="cannot succeed before two objective executions",
    ):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal(kind="success")]),
        )


def test_success_at_executive_cycle_two_is_rejected(tmp_path):
    with pytest.raises(
        CodexDurableRunError,
        match="cannot succeed before two objective executions",
    ):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex(
                [proposal("Objective one"), proposal(kind="success")]
            ),
        )
    store = FileCompanyStore(tmp_path / "company-store")
    assert store.load_state(durable.MANDATE_ID).active_objective_id is None
    assert store.load_evidence(durable.MANDATE_ID, "evidence-1-1").id == "evidence-1-1"


def test_success_at_executive_cycle_three_is_accepted(tmp_path):
    first = run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex(
            [proposal("Objective one"), proposal("Objective two")]
        ),
    )
    assert first.next_active_objective_id == "objective-2"
    second = run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(kind="success")]),
    )
    assert second.executed_objective_ids == ("objective-2",)
    assert second.ending_stage == "terminal"
    assert second.mandate_status is MandateStatus.SUCCEEDED


def test_cycle_one_prompt_prohibits_combined_validation_experiment(tmp_path):
    fake = FakeCodex([proposal("Objective one"), proposal("Objective two")])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    cycle_one = next(call for call in fake.calls if "Cycle: 1" in call)
    assert "Do not combine or design the complete validation experiment" in cycle_one
    assert "SUCCESS is prohibited" in cycle_one


def test_cycle_two_prompt_requires_separate_validation_plan(tmp_path):
    fake = FakeCodex([proposal("Objective one"), proposal("Objective two")])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    cycle_two = next(call for call in fake.calls if "Cycle: 2" in call)
    assert "A separate validation-plan objective must be executed before success" in cycle_two
    assert "SUCCESS is prohibited" in cycle_two


def test_existing_execution_output_is_reused(tmp_path):
    initial = FakeCodex([proposal(), proposal("Objective two")])
    # Stop immediately after authorization by directly creating a max-limit state through one terminal-free run setup.
    run_durable_cycles(tmp_path, max_cycles=1, command_function=initial)
    # The first invocation leaves objective 2 active. Simulate Codex creating its
    # artifact and output only after the runner has durably saved the guard.
    def crash(command, prompt):
        output = Path(command[command.index("--output-last-message") + 1])
        artifact = tmp_path / "execution-workspace/artifacts/cycle-2/result.md"
        assert artifact.parent.is_dir()
        artifact.write_text("cycle 2", encoding="utf-8")
        output.write_text(json.dumps(execution(2)), encoding="utf-8")
        raise OSError("crash after Codex")
    with pytest.raises(CodexDurableRunError):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=crash)
    guarded = json.loads((tmp_path / CHECKPOINT_NAME).read_text())
    assert guarded["stage"] == "objective_active"
    assert guarded["protected_file_hashes"] is not None
    quiet = FakeCodex([proposal("Objective three")])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=quiet)
    assert result.executed_objective_ids == ("objective-2",)
    assert not any("artifacts/cycle-2/" in call and "Execute only" in call for call in quiet.calls)


def test_populated_current_cycle_without_guard_is_rejected_unchanged(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )
    artifact = tmp_path / "execution-workspace/artifacts/cycle-2/orphaned.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    original = b"untrusted pre-guard content\r\n"
    artifact.write_bytes(original)

    with pytest.raises(
        CodexDurableRunError,
        match="current-cycle artifacts without a durable pre-execution guard",
    ):
        run_durable_cycles(
            tmp_path, max_cycles=1, command_function=FakeCodex([])
        )

    assert artifact.read_bytes() == original
    checkpoint = json.loads((tmp_path / CHECKPOINT_NAME).read_text())
    assert checkpoint["stage"] == "objective_active"
    assert checkpoint["protected_file_hashes"] is None
    store = FileCompanyStore(tmp_path / "company-store")
    with pytest.raises(FileNotFoundError):
        store.load_evidence(durable.MANDATE_ID, "evidence-2-1")


def test_existing_execution_output_without_durable_guard_is_rejected(tmp_path):
    run_durable_cycles(
        tmp_path,
        max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )
    artifact = tmp_path / "execution-workspace/artifacts/cycle-2/result.md"
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text("orphaned", encoding="utf-8")
    output = tmp_path / "execution-workspace/.codex-output/execution-2.json"
    output.write_text(json.dumps(execution(2)), encoding="utf-8")
    quiet = FakeCodex([])

    with pytest.raises(CodexDurableRunError, match="without a durable"):
        run_durable_cycles(
            tmp_path, max_cycles=1, command_function=quiet
        )

    assert quiet.calls == []
    assert json.loads((tmp_path / CHECKPOINT_NAME).read_text())[
        "protected_file_hashes"
    ] is None


def _crash_after_checkpoint_stage(monkeypatch, stage):
    original = durable._save_checkpoint

    def save_then_crash(path, checkpoint):
        original(path, checkpoint)
        if checkpoint.stage == stage:
            raise RuntimeError(f"crash at {stage}")

    monkeypatch.setattr(durable, "_save_checkpoint", save_then_crash)


def test_proposal_captured_before_domain_commit_resumes_without_executive(
    tmp_path, monkeypatch
):
    _crash_after_checkpoint_stage(monkeypatch, "proposal_captured")
    with pytest.raises(RuntimeError, match="proposal_captured"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal("Captured objective")]),
        )
    monkeypatch.undo()
    calls = []

    def stop_at_execution(command, prompt):
        calls.append(prompt)
        raise OSError("stop after authorization")

    with pytest.raises(CodexDurableRunError):
        run_durable_cycles(
            tmp_path, max_cycles=1, command_function=stop_at_execution
        )
    store = FileCompanyStore(tmp_path / "company-store")
    assert store.load_decision(durable.MANDATE_ID, "decision-1").objective_id == "objective-1"
    assert store.load_objective(durable.MANDATE_ID, "objective-1").id == "objective-1"
    assert store.load_state(durable.MANDATE_ID).active_objective_id == "objective-1"
    assert json.loads((tmp_path / CHECKPOINT_NAME).read_text())["stage"] == "objective_active"
    assert calls and all("Select exactly one" not in call for call in calls)


def test_proposal_captured_after_domain_commit_reconciles_without_executive(
    tmp_path, monkeypatch
):
    original = durable._save_checkpoint

    def crash_before_objective_checkpoint(path, checkpoint):
        if checkpoint.stage == "objective_active":
            raise RuntimeError("domain committed")
        original(path, checkpoint)

    monkeypatch.setattr(durable, "_save_checkpoint", crash_before_objective_checkpoint)
    with pytest.raises(RuntimeError, match="domain committed"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal("Committed objective")]),
        )
    monkeypatch.undo()
    calls = []

    def stop_at_execution(command, prompt):
        calls.append(prompt)
        raise OSError("stop")

    with pytest.raises(CodexDurableRunError):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=stop_at_execution)
    store = FileCompanyStore(tmp_path / "company-store")
    assert store.load_state(durable.MANDATE_ID).active_objective_id == "objective-1"
    assert json.loads((tmp_path / CHECKPOINT_NAME).read_text())["stage"] == "objective_active"
    assert all("Select exactly one" not in call for call in calls)


def _leave_proposal_captured_after_domain_commit(
    tmp_path, monkeypatch, captured_proposal
):
    original = durable._save_checkpoint
    final_stage = {
        "continue": "objective_active",
        "success": "terminal",
        "stop": "terminal",
        "human_escalation": "needs_human",
    }[captured_proposal["decision_type"]]

    def crash_before_final_checkpoint(path, checkpoint):
        if checkpoint.stage == final_stage:
            raise RuntimeError("proposal domain committed")
        original(path, checkpoint)

    monkeypatch.setattr(durable, "_save_checkpoint", crash_before_final_checkpoint)
    with pytest.raises(RuntimeError, match="proposal domain committed"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([captured_proposal]),
        )
    monkeypatch.undo()


@pytest.mark.parametrize("kind", ["stop", "human_escalation"])
def test_proposal_post_commit_exact_reconciliation_supports_all_decisions(
    tmp_path, monkeypatch, kind
):
    value = proposal(kind=kind)
    if kind == "human_escalation":
        value["human_escalation"] = {
            "question": "Choose?", "reason": "Owner judgment",
            "evidence_ids": [], "options": ["A", "B"],
        }
    _leave_proposal_captured_after_domain_commit(tmp_path, monkeypatch, value)
    quiet = FakeCodex([])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=quiet)
    assert quiet.calls == []
    assert result.ending_stage == (
        "needs_human" if kind == "human_escalation" else "terminal"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", "changed"),
        ("facts", ("changed",)),
        ("assumptions", ("changed",)),
        ("open_questions", ("changed",)),
        ("relevant_evidence_ids", ("unexpected-evidence",)),
        ("active_objective_id", "objective-unexpected"),
    ],
)
def test_proposal_post_commit_rejects_any_snapshot_field_change(
    tmp_path, monkeypatch, field, value
):
    _leave_proposal_captured_after_domain_commit(
        tmp_path, monkeypatch, proposal("Committed objective")
    )
    store = FileCompanyStore(tmp_path / "company-store")
    if field == "relevant_evidence_ids":
        store.save_evidence(
            Evidence(
                "unexpected-evidence", durable.MANDATE_ID,
                "test", "Unexpected",
            )
        )
    if field == "active_objective_id":
        store.save_objective(
            Objective(
                "objective-unexpected", durable.MANDATE_ID,
                "Unexpected", "Test mismatch",
            )
        )
    state = store.load_state(durable.MANDATE_ID)
    store.save_state(durable.replace(state, **{field: value}))
    with pytest.raises(CodexDurableRunError, match="captured proposal"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_proposal_post_commit_rejects_changed_status(tmp_path, monkeypatch):
    _leave_proposal_captured_after_domain_commit(
        tmp_path, monkeypatch, proposal(kind="stop")
    )
    store = FileCompanyStore(tmp_path / "company-store")
    state = store.load_state(durable.MANDATE_ID)
    store.save_state(durable.replace(state, status=MandateStatus.SUCCEEDED))
    with pytest.raises(CodexDurableRunError, match="captured proposal"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_proposal_post_commit_rejects_changed_pending_escalation(
    tmp_path, monkeypatch
):
    value = proposal(kind="human_escalation")
    value["human_escalation"] = {
        "question": "Choose?", "reason": "Owner judgment",
        "evidence_ids": [], "options": ["A", "B"],
    }
    _leave_proposal_captured_after_domain_commit(tmp_path, monkeypatch, value)
    store = FileCompanyStore(tmp_path / "company-store")
    other = HumanEscalation(
        "unexpected-escalation", durable.MANDATE_ID,
        "Other question?", "Test mismatch",
    )
    store.save_escalation(other)
    state = store.load_state(durable.MANDATE_ID)
    store.save_state(
        durable.replace(state, pending_human_escalation_id=other.id)
    )
    with pytest.raises(CodexDurableRunError, match="captured proposal"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_objective_active_executes_before_requesting_executive(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )
    fake = FakeCodex([proposal(kind="success")])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert "Execute only this bounded objective for cycle 2" in fake.calls[0]
    assert "Select exactly one" in fake.calls[1]


def _leave_execution_captured(tmp_path, monkeypatch):
    original = durable._save_checkpoint

    def save_then_crash(path, checkpoint):
        original(path, checkpoint)
        if checkpoint.stage == "execution_captured":
            raise RuntimeError("execution captured")

    monkeypatch.setattr(durable, "_save_checkpoint", save_then_crash)
    with pytest.raises(RuntimeError, match="execution captured"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal()]),
        )
    monkeypatch.undo()


def test_execution_captured_before_domain_commit_does_not_repeat_execution(
    tmp_path, monkeypatch
):
    _leave_execution_captured(tmp_path, monkeypatch)
    fake = FakeCodex([proposal(kind="stop")])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert result.executed_objective_ids == ("objective-1",)
    assert result.evidence_ids_created == ("evidence-1-1",)
    assert all("Execute only" not in call for call in fake.calls)


def test_contradictory_execution_captured_state_creates_no_evidence_or_checkpoint_advance(
    tmp_path, monkeypatch
):
    _leave_execution_captured(tmp_path, monkeypatch)
    store = FileCompanyStore(tmp_path / "company-store")
    state = store.load_state(durable.MANDATE_ID)
    store.save_state(durable.replace(state, summary="contradictory state"))
    checkpoint_before = (tmp_path / CHECKPOINT_NAME).read_bytes()

    with pytest.raises(
        CodexDurableRunError, match="expected pre-result and post-result"
    ):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))

    with pytest.raises(FileNotFoundError):
        store.load_evidence(durable.MANDATE_ID, "evidence-1-1")
    assert (tmp_path / CHECKPOINT_NAME).read_bytes() == checkpoint_before


def _leave_execution_captured_after_domain_commit(tmp_path, monkeypatch):
    original = durable._save_checkpoint

    def crash_before_next_cycle(path, checkpoint):
        if checkpoint.stage == "awaiting_executive" and checkpoint.cycle_number == 2:
            raise RuntimeError("result domain committed")
        original(path, checkpoint)

    monkeypatch.setattr(durable, "_save_checkpoint", crash_before_next_cycle)
    with pytest.raises(RuntimeError, match="result domain committed"):
        run_durable_cycles(
            tmp_path, max_cycles=1,
            command_function=FakeCodex([proposal()]),
        )
    monkeypatch.undo()


def test_execution_captured_after_domain_commit_reconciles_exact_state(
    tmp_path, monkeypatch
):
    _leave_execution_captured_after_domain_commit(tmp_path, monkeypatch)
    fake = FakeCodex([proposal(kind="stop")])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert result.executed_objective_ids == ()
    assert result.evidence_ids_created == ()
    assert all("Execute only" not in call for call in fake.calls)
    store = FileCompanyStore(tmp_path / "company-store")
    assert store.load_evidence(durable.MANDATE_ID, "evidence-1-1").id == "evidence-1-1"


def test_reconciled_result_does_not_consume_max_cycle_budget(
    tmp_path, monkeypatch
):
    _leave_execution_captured_after_domain_commit(tmp_path, monkeypatch)
    fake = FakeCodex([proposal("Objective two"), proposal("Objective three")])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert result.executed_objective_ids == ("objective-2",)
    assert result.evidence_ids_created == ("evidence-2-1",)
    assert result.next_active_objective_id == "objective-3"
    assert sum("Execute only" in call for call in fake.calls) == 1
    assert "cycle 2" in next(call for call in fake.calls if "Execute only" in call)
    assert not (tmp_path / "execution-workspace/.codex-output/execution-3.json").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("summary", "wrong"),
        ("facts", ("wrong",)),
        ("assumptions", ("wrong",)),
        ("open_questions", ("wrong",)),
        ("relevant_evidence_ids", ("evidence-1-1", "extra")),
    ],
)
def test_incompatible_post_result_snapshot_is_rejected(
    tmp_path, monkeypatch, field, value
):
    _leave_execution_captured_after_domain_commit(tmp_path, monkeypatch)
    store = FileCompanyStore(tmp_path / "company-store")
    state = store.load_state(durable.MANDATE_ID)
    if field == "relevant_evidence_ids":
        store.save_evidence(
            Evidence("extra", durable.MANDATE_ID, "test", "unexpected")
        )
    store.save_state(durable.replace(state, **{field: value}))
    with pytest.raises((CodexDurableRunError, ValueError)):
        run_durable_cycles(
            tmp_path, max_cycles=1, command_function=FakeCodex([])
        )


def test_incompatible_post_result_active_objective_is_rejected(
    tmp_path, monkeypatch
):
    _leave_execution_captured_after_domain_commit(tmp_path, monkeypatch)
    store = FileCompanyStore(tmp_path / "company-store")
    state = store.load_state(durable.MANDATE_ID)
    store.save_state(durable.replace(state, active_objective_id="objective-1"))
    with pytest.raises(CodexDurableRunError, match="pre-result"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_incompatible_post_result_pending_escalation_is_rejected(
    tmp_path, monkeypatch
):
    _leave_execution_captured_after_domain_commit(tmp_path, monkeypatch)
    store = FileCompanyStore(tmp_path / "company-store")
    escalation = HumanEscalation(
        "unexpected-escalation", durable.MANDATE_ID, "Question?", "Unexpected"
    )
    store.save_escalation(escalation)
    state = store.load_state(durable.MANDATE_ID)
    store.save_state(
        durable.replace(
            state,
            status=MandateStatus.NEEDS_HUMAN,
            pending_human_escalation_id=escalation.id,
        )
    )
    with pytest.raises(CodexDurableRunError, match="execution_captured"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


@pytest.mark.parametrize(
    "field,value,match",
    [
        ("schema_version", 2, "schema_version"),
        ("stage", "unknown", "unknown stage"),
        ("cycle_number", 0, "positive"),
        ("mandate_id", "wrong", "mandate mismatch"),
        ("captured_execution_result", execution(1), "invalid terminal"),
    ],
)
def test_checkpoint_validation_rejects_invalid_payloads(
    tmp_path, field, value, match
):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(kind="stop")]),
    )
    path = tmp_path / CHECKPOINT_NAME
    checkpoint = json.loads(path.read_text())
    checkpoint[field] = value
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(CodexDurableRunError, match=match):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_checkpoint_company_state_contradiction_is_rejected(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )
    path = tmp_path / CHECKPOINT_NAME
    checkpoint = json.loads(path.read_text())
    checkpoint["stage"] = "awaiting_executive"
    path.write_text(json.dumps(checkpoint), encoding="utf-8")
    with pytest.raises(CodexDurableRunError, match="without objective"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_atomic_checkpoint_replace_failure_preserves_prior_file(
    tmp_path, monkeypatch
):
    path = tmp_path / CHECKPOINT_NAME
    original = durable.RunCheckpoint(1, durable.MANDATE_ID, 1, "awaiting_executive")
    durable._save_checkpoint(path, original)
    before = path.read_bytes()

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(durable.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        durable._save_checkpoint(
            path, durable.replace(original, cycle_number=2)
        )
    assert path.read_bytes() == before
    assert durable._load_checkpoint(path) == original
    assert list(tmp_path.glob(f".{CHECKPOINT_NAME}.*.tmp")) == []


@pytest.mark.parametrize(
    "target",
    [
        "execution-workspace/artifacts/cycle-1/result.md",
        "execution-workspace/.codex-output/execution-1.json",
        "execution-workspace/authorized-inputs/candidate-brief.md",
    ],
)
def test_later_cycle_rejects_modified_prior_files(tmp_path, target):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )

    def mutate(command, prompt):
        output = Path(command[command.index("--output-last-message") + 1])
        protected = tmp_path / target
        protected.write_text(protected.read_text(encoding="utf-8") + "changed", encoding="utf-8")
        artifact = tmp_path / "execution-workspace/artifacts/cycle-2/result.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("cycle 2", encoding="utf-8")
        output.write_text(json.dumps(execution(2)), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises(CodexDurableRunError, match="protected files"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=mutate)


def test_later_cycle_rejects_unexpected_root_file(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )

    def add_root_file(command, prompt):
        output = Path(command[command.index("--output-last-message") + 1])
        (tmp_path / "execution-workspace/unexpected.txt").write_text("unexpected", encoding="utf-8")
        artifact = tmp_path / "execution-workspace/artifacts/cycle-2/result.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("cycle 2", encoding="utf-8")
        output.write_text(json.dumps(execution(2)), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises(CodexDurableRunError, match="protected files"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=add_root_file)


def test_bounded_execution_rejects_modified_durable_executive_output(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )

    def mutate_durable(command, prompt):
        output = Path(command[command.index("--output-last-message") + 1])
        executive = tmp_path / ".codex-output/executive-1.json"
        executive.write_text(executive.read_text(encoding="utf-8") + "changed", encoding="utf-8")
        artifact = tmp_path / "execution-workspace/artifacts/cycle-2/result.md"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text("cycle 2", encoding="utf-8")
        output.write_text(json.dumps(execution(2)), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises(CodexDurableRunError, match="durable files"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=mutate_durable)


def test_nested_artifact_excerpt_is_supplied_to_next_executive(tmp_path):
    class Nested(FakeCodex):
        def __call__(self, command, prompt):
            completed = super().__call__(command, prompt)
            output = Path(command[command.index("--output-last-message") + 1])
            if output.name == "execution-1.json":
                nested = output.parents[1] / "artifacts/cycle-1/report/summary.md"
                nested.parent.mkdir(parents=True)
                nested.write_text("NESTED ARTIFACT CONTENT", encoding="utf-8")
            return completed

    fake = Nested([proposal("Objective one"), proposal("Objective two")])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    second_prompt = next(prompt for prompt in fake.calls if "Cycle: 2" in prompt)
    assert "artifacts/cycle-1/report/summary.md" in second_prompt
    assert "NESTED ARTIFACT CONTENT" in second_prompt


def test_later_cycle_rejects_reported_artifact_outside_cycle(tmp_path):
    class WrongPath(FakeCodex):
        def __call__(self, command, prompt):
            completed = super().__call__(command, prompt)
            output = Path(command[command.index("--output-last-message") + 1])
            if output.name == "execution-2.json":
                value = json.loads(output.read_text())
                value["artifact_paths"] = ["artifacts/cycle-1/result.md"]
                output.write_text(json.dumps(value), encoding="utf-8")
            return completed

    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )
    with pytest.raises((CodexDurableRunError, ValueError), match="cycle-2"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=WrongPath([]))


def test_later_cycle_rejects_symlink_artifact(tmp_path):
    run_durable_cycles(
        tmp_path, max_cycles=1,
        command_function=FakeCodex([proposal(), proposal("Objective two")]),
    )

    def create_symlink(command, prompt):
        output = Path(command[command.index("--output-last-message") + 1])
        directory = tmp_path / "execution-workspace/artifacts/cycle-2"
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / "target.md"
        target.write_text("target", encoding="utf-8")
        link = directory / "result.md"
        try:
            link.symlink_to(target)
        except OSError as exc:
            pytest.skip(f"symlinks unavailable: {exc}")
        output.write_text(json.dumps(execution(2)), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises((CodexDurableRunError, ValueError), match="regular cycle"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=create_symlink)


def test_symlinked_execution_workspace_root_is_rejected(tmp_path):
    target = tmp_path / "symlink-target"
    target.mkdir()
    execution_workspace = tmp_path / "execution-workspace"
    try:
        execution_workspace.symlink_to(target, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    with pytest.raises(CodexDurableRunError, match="must not be a symlink"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))
    assert list(target.iterdir()) == []


def test_max_cycles_one_commits_one_and_only_authorizes_next(tmp_path):
    fake = FakeCodex([proposal("One"), proposal("Two")])
    result = run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    assert result.executed_objective_ids == ("objective-1",)
    assert result.next_active_objective_id == "objective-2"
    assert not (tmp_path / "execution-workspace/.codex-output/execution-2.json").exists()
    assert sum("Execute only" in call for call in fake.calls) == 1


def test_malformed_checkpoint_and_missing_checkpoint_fail(tmp_path):
    fake = FakeCodex([proposal(kind="stop")])
    run_durable_cycles(tmp_path, max_cycles=1, command_function=fake)
    checkpoint = tmp_path / CHECKPOINT_NAME
    checkpoint.write_text("{", encoding="utf-8")
    with pytest.raises(CodexDurableRunError, match="malformed"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))
    checkpoint.unlink()
    with pytest.raises(CodexDurableRunError, match="checkpoint is missing"):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=FakeCodex([]))


def test_artifact_escape_is_rejected(tmp_path):
    class Escape(FakeCodex):
        def __call__(self, command, prompt):
            result = super().__call__(command, prompt)
            output = Path(command[command.index("--output-last-message") + 1])
            if output.name.startswith("execution"):
                value = json.loads(output.read_text())
                value["artifact_paths"] = ["artifacts/cycle-1/../escape.md"]
                output.write_text(json.dumps(value), encoding="utf-8")
            return result
    with pytest.raises((CodexDurableRunError, ValueError)):
        run_durable_cycles(tmp_path, max_cycles=1, command_function=Escape([proposal()]))


def test_max_cycles_must_be_positive(tmp_path):
    with pytest.raises(ValueError, match="positive"):
        run_durable_cycles(tmp_path, max_cycles=0, command_function=FakeCodex([]))
