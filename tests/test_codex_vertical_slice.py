import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from loop_engine.codex_vertical_slice import (
    CodexVerticalSliceError,
    StructuredOutputError,
    _run_subprocess,
    parse_execution_result,
    parse_executive_proposal,
    run_vertical_slice,
)
from loop_engine.company_models import ObjectiveStatus
from loop_engine.company_store import FileCompanyStore


def executive_proposal_1() -> dict[str, object]:
    return {
        "decision_type": "continue",
        "rationale": (
            "The synthetic candidates must be compared before selecting a "
            "real validation step."
        ),
        "supporting_evidence_ids": [],
        "objective": {
            "outcome": (
                "Compare the three synthetic candidates and select the "
                "strongest hypothesis."
            ),
            "rationale": (
                "A bounded comparison will identify which uncertainty to "
                "validate next."
            ),
            "constraints": [
                "Use only candidate-brief.md.",
                "Do not claim real market demand.",
            ],
            "acceptance_criteria": [
                "All three candidates are compared on explicit criteria.",
                "One candidate hypothesis is selected with risks.",
            ],
            "expected_evidence": [
                "A durable candidate-comparison artifact."
            ],
        },
        "human_escalation": None,
    }


def execution_result() -> dict[str, object]:
    return {
        "summary": (
            "The manufacturing RFP assistant is the strongest synthetic "
            "hypothesis, subject to real validation."
        ),
        "observations": [
            "Candidate B has the clearest repeated workflow in the synthetic brief."
        ],
        "artifact_paths": ["artifacts/candidate-comparison.md"],
        "facts": [
            "Candidate B appears to have a bounded, inspectable output."
        ],
        "assumptions": [
            "Manufacturing teams can identify a buyer for this workflow."
        ],
        "open_questions": [
            "Will a real buyer commit time or money to solve this problem?"
        ],
    }


def executive_proposal_2() -> dict[str, object]:
    return {
        "decision_type": "continue",
        "rationale": (
            "Evidence evidence-1-1 selects Candidate B as a hypothesis, so "
            "the next uncertainty is real willingness to pay."
        ),
        "supporting_evidence_ids": ["evidence-1-1"],
        "objective": {
            "outcome": (
                "Design a willingness-to-pay interview experiment for the "
                "manufacturing RFP assistant."
            ),
            "rationale": (
                "The comparison is complete; the next objective must seek "
                "real demand evidence."
            ),
            "constraints": [
                "Do not treat the synthetic comparison as demand evidence."
            ],
            "acceptance_criteria": [
                "Define a target buyer, interview script, and commitment threshold."
            ],
            "expected_evidence": [
                "A validation plan capable of producing real buyer evidence."
            ],
        },
        "human_escalation": None,
    }


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_run_subprocess_decodes_utf8_stdout_and_stderr() -> None:
    script = (
        "import sys; "
        "sys.stdout.buffer.write("
        "'Gr\\u00fc\\u00dfe \\u6771\\u4eac \\U0001f680\\n'.encode('utf-8')); "
        "sys.stderr.buffer.write("
        "'\\u8a3a\\u65ad caf\\u00e9 \\U0001f680\\n'.encode('utf-8') "
        "+ b'\\xff')"
    )

    completed = _run_subprocess([sys.executable, "-c", script], "")

    assert completed.returncode == 0
    assert completed.stdout == "Grüße 東京 🚀\n"
    assert completed.stderr == "診断 café 🚀\n�"


def run_with_execution_mutation(
    demo: Path, mutation: Callable[[Path], None]
) -> None:
    payloads = [executive_proposal_1(), execution_result()]
    invocation = 0

    def canned_command(command: list[str], prompt: str):
        nonlocal invocation
        payload = payloads[invocation]
        invocation += 1
        workspace = Path(command[command.index("--cd") + 1])
        if command[command.index("--sandbox") + 1] == "workspace-write":
            artifact = workspace / "artifacts" / "candidate-comparison.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text("Allowed artifact", encoding="utf-8")
            mutation(workspace)
        output = Path(
            command[command.index("--output-last-message") + 1]
        )
        write_json(output, payload)
        return subprocess.CompletedProcess(command, 0, "", "")

    run_vertical_slice(
        demo,
        codex_executable="codex",
        command_function=canned_command,
    )


def test_executive_structured_output_parsing(tmp_path) -> None:
    output = tmp_path / "executive.json"
    write_json(output, executive_proposal_1())

    parsed = parse_executive_proposal(output)

    assert parsed["decision_type"] == "continue"
    objective = parsed["objective"]
    assert isinstance(objective, dict)
    assert objective["constraints"] == (
        "Use only candidate-brief.md.",
        "Do not claim real market demand.",
    )


def test_execution_structured_output_parsing_and_artifact_validation(
    tmp_path,
) -> None:
    workspace = tmp_path / "execution-workspace"
    artifact = workspace / "artifacts" / "candidate-comparison.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("Synthetic comparison", encoding="utf-8")
    output = workspace / "execution.json"
    write_json(output, execution_result())

    parsed = parse_execution_result(output, workspace)

    assert parsed["artifact_paths"] == (
        "artifacts/candidate-comparison.md",
    )
    assert parsed["observations"] == (
        "Candidate B has the clearest repeated workflow in the synthetic brief.",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda payload: payload.update(decision_type="unknown"),
        lambda payload: payload.pop("rationale"),
        lambda payload: payload.update(human_escalation={}),
    ],
)
def test_invalid_executive_output_is_rejected(tmp_path, mutate) -> None:
    payload = executive_proposal_1()
    mutate(payload)
    output = tmp_path / "executive.json"
    write_json(output, payload)

    with pytest.raises(StructuredOutputError):
        parse_executive_proposal(output)


def test_execution_output_cannot_select_objective_or_declare_success(
    tmp_path,
) -> None:
    workspace = tmp_path / "execution-workspace"
    artifact = workspace / "artifacts" / "candidate-comparison.md"
    artifact.parent.mkdir(parents=True)
    artifact.write_text("Synthetic comparison", encoding="utf-8")
    payload = execution_result()
    payload["decision_type"] = "success"
    payload["objective"] = {"outcome": "Execute Objective 2"}
    output = workspace / "execution.json"
    write_json(output, payload)

    with pytest.raises(StructuredOutputError, match="unexpected"):
        parse_execution_result(output, workspace)


def test_execution_output_rejects_missing_or_escaping_artifact(tmp_path) -> None:
    workspace = tmp_path / "execution-workspace"
    workspace.mkdir()
    payload = execution_result()
    payload["artifact_paths"] = ["../outside.md"]
    output = workspace / "execution.json"
    write_json(output, payload)

    with pytest.raises(StructuredOutputError, match="relative"):
        parse_execution_result(output, workspace)


def test_nonzero_codex_exit_is_reported(tmp_path) -> None:
    def failing_command(command: list[str], prompt: str):
        return subprocess.CompletedProcess(command, 17, "", "failed")

    with pytest.raises(CodexVerticalSliceError, match="status 17"):
        run_vertical_slice(
            tmp_path / "demo",
            codex_executable="codex",
            command_function=failing_command,
        )


def test_missing_structured_output_is_reported(tmp_path) -> None:
    def missing_output(command: list[str], prompt: str):
        return subprocess.CompletedProcess(command, 0, "", "")

    with pytest.raises(CodexVerticalSliceError, match="did not create"):
        run_vertical_slice(
            tmp_path / "demo",
            codex_executable="codex",
            command_function=missing_output,
        )


def test_modified_candidate_brief_is_rejected(tmp_path) -> None:
    def modify_candidate(workspace: Path) -> None:
        (workspace / "candidate-brief.md").write_text(
            "Codex changed the fixture", encoding="utf-8"
        )

    with pytest.raises(
        CodexVerticalSliceError, match="modified candidate-brief.md"
    ):
        run_with_execution_mutation(tmp_path / "demo", modify_candidate)


def test_unexpected_file_outside_artifacts_is_rejected(tmp_path) -> None:
    def add_unexpected_file(workspace: Path) -> None:
        (workspace / "unexpected.md").write_text(
            "Unexpected", encoding="utf-8"
        )

    with pytest.raises(
        CodexVerticalSliceError, match="added unexpected.md"
    ):
        run_with_execution_mutation(tmp_path / "demo", add_unexpected_file)


def test_modified_prior_executive_output_is_rejected(tmp_path) -> None:
    def modify_executive_output(workspace: Path) -> None:
        (workspace / ".codex-output" / "executive-1.json").write_text(
            "Modified", encoding="utf-8"
        )

    with pytest.raises(
        CodexVerticalSliceError,
        match=r"modified \.codex-output/executive-1\.json",
    ):
        run_with_execution_mutation(
            tmp_path / "demo", modify_executive_output
        )


def test_unexpected_additional_codex_output_is_rejected(tmp_path) -> None:
    def add_unexpected_output(workspace: Path) -> None:
        (workspace / ".codex-output" / "unexpected.json").write_text(
            "{}", encoding="utf-8"
        )

    with pytest.raises(
        CodexVerticalSliceError,
        match=r"added \.codex-output/unexpected\.json",
    ):
        run_with_execution_mutation(tmp_path / "demo", add_unexpected_output)


def test_deleted_prior_executive_output_is_rejected(tmp_path) -> None:
    def delete_executive_output(workspace: Path) -> None:
        (workspace / ".codex-output" / "executive-1.json").unlink()

    with pytest.raises(
        CodexVerticalSliceError,
        match=r"deleted \.codex-output/executive-1\.json",
    ):
        run_with_execution_mutation(
            tmp_path / "demo", delete_executive_output
        )


@pytest.mark.parametrize(
    ("action", "expected"),
    [("delete", "deleted protected.txt"), ("modify", "modified protected.txt")],
)
def test_deleted_or_modified_protected_file_is_rejected(
    tmp_path, action: str, expected: str
) -> None:
    demo = tmp_path / "demo"
    execution_workspace = demo / "execution-workspace"
    execution_workspace.mkdir(parents=True)
    protected = execution_workspace / "protected.txt"
    protected.write_text("Original", encoding="utf-8")

    def change_protected_file(workspace: Path) -> None:
        if action == "delete":
            protected.unlink()
        else:
            protected.write_text("Modified", encoding="utf-8")

    with pytest.raises(CodexVerticalSliceError, match=expected):
        run_with_execution_mutation(demo, change_protected_file)


def test_valid_artifact_only_two_cycle_execution_persists_evidence(
    tmp_path,
) -> None:
    demo = tmp_path / "demo"
    payloads = [
        executive_proposal_1(),
        execution_result(),
        executive_proposal_2(),
    ]
    commands: list[list[str]] = []
    prompts: list[str] = []

    def canned_command(command: list[str], prompt: str):
        index = len(commands)
        commands.append(command)
        prompts.append(prompt)
        workspace = Path(command[command.index("--cd") + 1])
        if command[command.index("--sandbox") + 1] == "workspace-write":
            artifact = workspace / "artifacts" / "candidate-comparison.md"
            artifact.parent.mkdir(parents=True)
            artifact.write_text(
                "SYNTHETIC ANALYSIS ARTIFACT: Candidate B is only a hypothesis.",
                encoding="utf-8",
            )
        output = Path(
            command[command.index("--output-last-message") + 1]
        )
        write_json(output, payloads[index])
        return subprocess.CompletedProcess(command, 0, "", "")

    result = run_vertical_slice(
        demo,
        codex_executable="codex",
        command_function=canned_command,
    )

    assert len(commands) == 3
    assert [
        command[command.index("--sandbox") + 1] for command in commands
    ] == ["read-only", "workspace-write", "read-only"]
    execution_workspace = (demo / "execution-workspace").resolve()
    assert all(
        Path(command[command.index("--cd") + 1]) == execution_workspace
        for command in commands
    )
    assert all("--output-schema" in command for command in commands)
    assert all("--skip-git-repo-check" in command for command in commands)

    store = FileCompanyStore(demo / "company-store")
    mandate_id = result.mandate.id
    assert store.load_objective(
        mandate_id, result.objective_1.id
    ).status is ObjectiveStatus.PENDING
    assert store.load_decision(mandate_id, "decision-1").objective_id == (
        result.objective_1.id
    )
    evidence = store.load_evidence(mandate_id, "evidence-1-1")
    assert "artifacts/candidate-comparison.md" in evidence.source
    assert "Candidate B" in evidence.observation
    final_state = store.load_state(mandate_id)
    assert final_state.active_objective_id == result.objective_2.id
    assert "evidence-1-1" in final_state.relevant_evidence_ids
    assert not any(
        "bounded, inspectable output" in fact for fact in final_state.facts
    )

    assert result.objective_2.outcome != result.objective_1.outcome
    assert "evidence-1-1" in prompts[2]
    assert "Candidate B has the clearest" in prompts[2]
    assert "SYNTHETIC ANALYSIS ARTIFACT" in prompts[2]
    assert "Do not select the next company objective" in prompts[1]
    assert result.final_state.active_objective_id == result.objective_2.id
