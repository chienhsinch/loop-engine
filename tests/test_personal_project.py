import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from loop_engine.__main__ import main
from loop_engine import codex_durable_run as durable
from loop_engine.company_models import MandateStatus
from loop_engine.company_store import FileCompanyStore
from loop_engine import personal_project
from loop_engine.personal_project import (
    PersonalProjectError,
    history_text,
    initialize_project,
    load_project,
    run_personal_project,
    status_text,
)


def mandate_value():
    return {
        "id": "user-mandate", "description": "Produce a supported report.",
        "constraints": ["Stay local."],
        "success_criteria": ["The report cites durable evidence."],
        "stop_conditions": ["Stop before outreach."],
    }


def write_mandate(path, value=None):
    path.write_text(json.dumps(value or mandate_value(), indent=2), encoding="utf-8")
    return path


def proposal(outcome="Create report", kind="continue"):
    return {
        "decision_type": kind, "rationale": "Use current evidence.",
        "supporting_evidence_ids": [],
        "objective": ({"outcome": outcome, "rationale": "Bounded work.",
                       "constraints": ["Stay local."], "acceptance_criteria": ["Artifact exists."],
                       "expected_evidence": ["A report."]} if kind == "continue" else None),
        "human_escalation": None,
    }


class FakeCodex:
    def __init__(self, proposals):
        self.proposals = list(proposals)
        self.calls = []

    def __call__(self, command, prompt):
        self.calls.append((command, prompt))
        output = Path(command[command.index("--output-last-message") + 1])
        if output.name.startswith("executive-"):
            value = self.proposals.pop(0)
        else:
            cycle = int(output.stem.split("-")[-1])
            artifact = output.parents[1] / f"artifacts/cycle-{cycle}/report.md"
            artifact.parent.mkdir(parents=True, exist_ok=True)
            artifact.write_text("report", encoding="utf-8")
            value = {"summary": "Done", "observations": ["A report was created."],
                     "artifact_paths": [f"artifacts/cycle-{cycle}/report.md"],
                     "facts": [], "assumptions": [], "open_questions": []}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(value), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")


def test_personal_host_creates_cycle_directory_before_execution(tmp_path):
    root, _ = initialized(tmp_path)

    class AssertExisting(FakeCodex):
        def __call__(self, command, prompt):
            output = Path(command[command.index("--output-last-message") + 1])
            if output.name == "execution-1.json":
                cycle = root / "execution-workspace/artifacts/cycle-1"
                assert cycle.is_dir()
                assert list(cycle.iterdir()) == []
                assert "already exists" in prompt
                assert "preserve its inherited permissions" in prompt
            return super().__call__(command, prompt)

    result = run_personal_project(
        root, max_cycles=1,
        command_function=AssertExisting([proposal(), proposal(kind="stop")]),
    )
    assert result.executed_objective_ids == ("objective-1",)


def initialized(tmp_path):
    source = write_mandate(tmp_path / "input.json")
    root = tmp_path / "project"
    initialize_project(root, source)
    return root, source


def test_initialization_layout_hash_and_durable_records(tmp_path):
    root, source = initialized(tmp_path)
    canonical = root / "mandate.json"
    authorized = root / "execution-workspace/authorized-inputs/mandate.json"
    assert canonical.read_bytes() == source.read_bytes() == authorized.read_bytes()
    assert json.loads((root / "project.json").read_text()) == {
        "schema_version": 1, "mandate_id": "user-mandate",
        "mandate_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    _, store, mandate, checkpoint = load_project(root)
    state = store.load_state(mandate.id)
    assert mandate.id == "user-mandate"
    assert state.summary == "No bounded objective has been executed yet."
    assert state.open_questions == ("What bounded objective should be pursued first?",)
    assert checkpoint.stage == "awaiting_executive" and checkpoint.cycle_number == 1


@pytest.mark.parametrize("change", [
    lambda x: {**x, "unknown": 1},
    lambda x: {**x, "id": True},
    lambda x: {**x, "constraints": [""]},
])
def test_invalid_mandates_are_rejected_before_workspace_creation(tmp_path, change):
    source = write_mandate(tmp_path / "bad.json", change(mandate_value()))
    root = tmp_path / "project"
    with pytest.raises(PersonalProjectError):
        initialize_project(root, source)
    assert not root.exists()


def test_duplicate_initialization_refuses_overwrite(tmp_path):
    root, source = initialized(tmp_path)
    before = (root / "project.json").read_bytes()
    with pytest.raises(PersonalProjectError, match="contains content"):
        initialize_project(root, source)
    assert (root / "project.json").read_bytes() == before


@pytest.mark.parametrize("preexisting", [False, True])
def test_initialization_failure_is_atomic(tmp_path, monkeypatch, preexisting):
    source = write_mandate(tmp_path / "input.json")
    root = tmp_path / "project"
    if preexisting:
        root.mkdir()

    def fail_checkpoint(path, checkpoint):
        raise OSError("checkpoint write failed")

    monkeypatch.setattr(personal_project, "_save_checkpoint", fail_checkpoint)
    with pytest.raises(OSError, match="checkpoint write failed"):
        initialize_project(root, source)

    if preexisting:
        assert root.is_dir() and list(root.iterdir()) == []
    else:
        assert not root.exists()
    assert list(tmp_path.glob(".project.init.*")) == []
    assert list(tmp_path.glob(".project.empty.*")) == []


def test_initialization_publishes_into_existing_empty_workspace(tmp_path):
    source = write_mandate(tmp_path / "input.json")
    root = tmp_path / "project"
    root.mkdir()
    initialize_project(root, source)
    assert (root / "project.json").is_file()


def test_invalid_staging_project_is_rejected_before_publication(
    tmp_path, monkeypatch
):
    source = write_mandate(tmp_path / "input.json")
    root = tmp_path / "project"
    original_build = personal_project._build_project

    def build_then_corrupt(staging, mandate, source_bytes):
        original_build(staging, mandate, source_bytes)
        project = json.loads((staging / "project.json").read_text())
        project["mandate_sha256"] = "0" * 64
        (staging / "project.json").write_text(
            json.dumps(project), encoding="utf-8"
        )

    monkeypatch.setattr(
        personal_project, "_build_project", build_then_corrupt
    )
    with pytest.raises(PersonalProjectError, match="hash"):
        initialize_project(root, source)

    assert not root.exists()
    assert list(tmp_path.glob(".project.init.*")) == []
    assert list(tmp_path.glob(".project.empty.*")) == []

    monkeypatch.setattr(personal_project, "_build_project", original_build)
    initialize_project(root, source)
    assert load_project(root)[2].id == "user-mandate"


@pytest.mark.parametrize("preexisting", [False, True])
def test_final_installation_failure_restores_destination(
    tmp_path, monkeypatch, preexisting
):
    source = write_mandate(tmp_path / "input.json")
    root = (tmp_path / "project").absolute()
    if preexisting:
        root.mkdir()
    real_replace = personal_project.os.replace

    def fail_staging_publication(source_path, destination_path):
        source_path = Path(source_path)
        destination_path = Path(destination_path)
        if (
            source_path.parent == root.parent
            and source_path.name.startswith(f".{root.name}.init.")
            and destination_path == root
        ):
            raise OSError("final installation failed")
        return real_replace(source_path, destination_path)

    monkeypatch.setattr(
        personal_project.os, "replace", fail_staging_publication
    )
    with pytest.raises(OSError, match="final installation failed"):
        initialize_project(root, source)

    if preexisting:
        assert root.is_dir() and list(root.iterdir()) == []
    else:
        assert not root.exists()
    assert list(tmp_path.glob(".project.init.*")) == []
    assert list(tmp_path.glob(".project.empty.*")) == []


def test_personal_run_uses_shared_boundaries_and_has_no_cycle_three_rule(tmp_path):
    root, _ = initialized(tmp_path)
    fake = FakeCodex([proposal(), proposal(kind="success")])
    result = run_personal_project(root, max_cycles=1, command_function=fake)
    assert result.mandate_id == "user-mandate"
    executive, execution, final_executive = fake.calls
    assert executive[0][executive[0].index("--sandbox") + 1] == "read-only"
    assert Path(executive[0][executive[0].index("--cd") + 1]) == root.resolve()
    assert execution[0][execution[0].index("--sandbox") + 1] == "workspace-write"
    assert Path(execution[0][execution[0].index("--cd") + 1]) == (root / "execution-workspace").resolve()
    assert "candidate-brief" not in execution[1]
    assert result.mandate_status is MandateStatus.SUCCEEDED
    assert final_executive[0]


def test_resume_does_not_repeat_previous_objective(tmp_path):
    root, _ = initialized(tmp_path)
    first = FakeCodex([proposal("One"), proposal("Two")])
    run_personal_project(root, max_cycles=1, command_function=first)
    second = FakeCodex([proposal(kind="stop")])
    result = run_personal_project(root, max_cycles=1, command_function=second)
    assert result.executed_objective_ids == ("objective-2",)
    assert sum("Execute only" in prompt for _, prompt in second.calls) == 1


def test_execution_captured_rejects_inexact_state_without_mutation(
    tmp_path, monkeypatch
):
    root, _ = initialized(tmp_path)
    original_save = durable._save_checkpoint

    def save_then_crash(path, checkpoint):
        original_save(path, checkpoint)
        if checkpoint.stage == "execution_captured":
            raise RuntimeError("execution captured")

    monkeypatch.setattr(durable, "_save_checkpoint", save_then_crash)
    with pytest.raises(RuntimeError, match="execution captured"):
        run_personal_project(
            root, max_cycles=1, command_function=FakeCodex([proposal()])
        )
    monkeypatch.setattr(durable, "_save_checkpoint", original_save)

    store = FileCompanyStore(root / "company-store")
    state = store.load_state("user-mandate")
    store.save_state(replace(state, summary="contradictory summary"))
    checkpoint_before = (root / durable.CHECKPOINT_NAME).read_bytes()
    evidence_directory = next((root / "company-store").rglob("evidence"), None)
    evidence_before = (
        tuple(sorted(path.read_bytes() for path in evidence_directory.glob("*.json")))
        if evidence_directory else ()
    )

    with pytest.raises(durable.CodexDurableRunError, match="expected pre-result"):
        status_text(root)

    assert (root / durable.CHECKPOINT_NAME).read_bytes() == checkpoint_before
    evidence_directory = next((root / "company-store").rglob("evidence"), None)
    evidence_after = (
        tuple(sorted(path.read_bytes() for path in evidence_directory.glob("*.json")))
        if evidence_directory else ()
    )
    assert evidence_after == evidence_before == ()


def test_terminal_status_history_are_read_only(tmp_path, monkeypatch):
    root, _ = initialized(tmp_path)
    run_personal_project(root, max_cycles=1,
                         command_function=FakeCodex([proposal(), proposal(kind="stop")]))
    monkeypatch.setattr("loop_engine.codex_durable_run._resolve_codex",
                        lambda *args: pytest.fail("Codex must not resolve"))
    status = status_text(root)
    history = history_text(root)
    assert "Mandate status: stopped" in status
    assert "Relevant evidence IDs:" in status
    assert history.index("Cycle: 1") < history.index("Cycle: 2")
    assert "Objective outcome: Create report" in history
    assert "Decision type: stop" in history


@pytest.mark.parametrize("target", ["project", "canonical", "authorized", "store"])
def test_project_mismatches_are_rejected(tmp_path, target):
    root, _ = initialized(tmp_path)
    if target == "project":
        value = json.loads((root / "project.json").read_text())
        value["extra"] = 1
        (root / "project.json").write_text(json.dumps(value), encoding="utf-8")
    elif target == "canonical":
        (root / "mandate.json").write_text("{}", encoding="utf-8")
    elif target == "authorized":
        (root / "execution-workspace/authorized-inputs/mandate.json").write_text("{}", encoding="utf-8")
    else:
        stored = next((root / "company-store").rglob("mandate.json"))
        value = json.loads(stored.read_text())
        value["description"] = "changed"
        stored.write_text(json.dumps(value), encoding="utf-8")
    with pytest.raises(PersonalProjectError):
        load_project(root)


def test_cli_success_error_and_help(tmp_path, capsys):
    source = write_mandate(tmp_path / "input.json")
    root = tmp_path / "project"
    assert main(["init", "--workspace", str(root), "--mandate", str(source)]) == 0
    assert main(["status", "--workspace", str(root)]) == 0
    assert main(["init", "--workspace", str(root), "--mandate", str(source)]) == 1
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
