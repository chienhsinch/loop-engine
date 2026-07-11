"""Concrete two-cycle Codex CLI executive demonstration for architecture v0.3."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

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


CommandFunction = Callable[
    [list[str], str], subprocess.CompletedProcess[str]
]

_MANDATE_ID = "synthetic-product-opportunity"
_EXECUTIVE_SCHEMA = "executive_proposal.schema.json"
_EXECUTION_SCHEMA = "execution_result.schema.json"
_FIXTURE = "synthetic_product_opportunities.md"


class CodexVerticalSliceError(RuntimeError):
    """Raised when the concrete Codex vertical slice cannot continue."""


class StructuredOutputError(ValueError):
    """Raised when a Codex structured output has an invalid shape."""


@dataclass(frozen=True)
class VerticalSliceSummary:
    mandate: Mandate
    objective_1: Objective
    artifact_paths: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    state_after_objective_1: CompanyState
    objective_2: Objective
    objective_2_rationale: str
    final_state: CompanyState


def run_vertical_slice(
    workspace: Path | str,
    *,
    codex_executable: str | None = None,
    command_function: CommandFunction | None = None,
    fixture_path: Path | None = None,
    schema_directory: Path | None = None,
) -> VerticalSliceSummary:
    """Run the synthetic Phase 5 demo and stop after Objective 2 is selected."""

    root = Path(workspace).resolve()
    repository_root = Path(__file__).resolve().parents[2]
    fixture = fixture_path or (
        repository_root / "examples" / "fixtures" / _FIXTURE
    )
    schemas = schema_directory or repository_root / "schemas"
    executive_schema = schemas / _EXECUTIVE_SCHEMA
    execution_schema = schemas / _EXECUTION_SCHEMA
    _require_file(fixture, "synthetic candidate fixture")
    _require_file(executive_schema, "executive JSON Schema")
    _require_file(execution_schema, "execution JSON Schema")

    executable = _resolve_codex_executable(
        codex_executable, command_function
    )
    store, mandate, state, execution_workspace = _prepare_workspace(
        root, fixture
    )
    output_directory = execution_workspace / ".codex-output"

    executive_1_path = output_directory / "executive-1.json"
    _invoke_codex(
        executable=executable,
        role="executive cycle 1",
        prompt=_executive_prompt(
            cycle=1,
            mandate=mandate,
            state=state,
            evidence=(),
            artifact_contents=(),
        ),
        workspace=execution_workspace,
        schema_path=executive_schema,
        output_path=executive_1_path,
        sandbox="read-only",
        command_function=command_function,
    )
    proposal_1 = parse_executive_proposal(executive_1_path)
    decision_1, objective_1, escalation_1 = _proposal_records(
        proposal_1, mandate, cycle=1
    )
    _require_continue(decision_1, objective_1, escalation_1, cycle=1)
    assert objective_1 is not None
    state = _persist_authorization(
        store, state, decision_1, objective_1
    )

    execution_path = output_directory / "execution-1.json"
    protected_files = _snapshot_protected_files(
        execution_workspace, execution_path
    )
    _invoke_codex(
        executable=executable,
        role="bounded execution",
        prompt=_execution_prompt(mandate, objective_1),
        workspace=execution_workspace,
        schema_path=execution_schema,
        output_path=execution_path,
        sandbox="workspace-write",
        command_function=command_function,
    )
    _verify_protected_files(
        execution_workspace, execution_path, protected_files
    )
    execution = parse_execution_result(
        execution_path, execution_workspace
    )
    evidence, state_update = _execution_records(
        execution=execution,
        state=state,
        objective=objective_1,
        decision=decision_1,
    )
    terminal_objective_1 = replace(
        objective_1, status=ObjectiveStatus.SUCCEEDED
    )
    state_after_objective_1 = apply_objective_result(
        state, terminal_objective_1, evidence, state_update
    )
    for record in evidence:
        store.save_evidence(record)
    store.save_state(state_after_objective_1)

    # Reload every durable input before the second executive decision.
    reread_state = store.load_state(mandate.id)
    reread_evidence = tuple(
        store.load_evidence(mandate.id, evidence_id)
        for evidence_id in reread_state.relevant_evidence_ids
    )
    artifact_paths = execution["artifact_paths"]
    assert isinstance(artifact_paths, tuple)
    artifact_contents = _read_artifacts(
        execution_workspace, artifact_paths
    )

    executive_2_path = output_directory / "executive-2.json"
    _invoke_codex(
        executable=executable,
        role="executive cycle 2",
        prompt=_executive_prompt(
            cycle=2,
            mandate=mandate,
            state=reread_state,
            evidence=reread_evidence,
            artifact_contents=artifact_contents,
        ),
        workspace=execution_workspace,
        schema_path=executive_schema,
        output_path=executive_2_path,
        sandbox="read-only",
        command_function=command_function,
    )
    proposal_2 = parse_executive_proposal(executive_2_path)
    decision_2, objective_2, escalation_2 = _proposal_records(
        proposal_2, mandate, cycle=2
    )
    _require_continue(decision_2, objective_2, escalation_2, cycle=2)
    assert objective_2 is not None
    _validate_materially_different(
        objective_1,
        objective_2,
        decision_2,
        tuple(record.id for record in evidence),
    )
    final_state = _persist_authorization(
        store, reread_state, decision_2, objective_2
    )

    return VerticalSliceSummary(
        mandate=mandate,
        objective_1=objective_1,
        artifact_paths=artifact_paths,
        evidence_ids=tuple(record.id for record in evidence),
        state_after_objective_1=state_after_objective_1,
        objective_2=objective_2,
        objective_2_rationale=decision_2.rationale,
        final_state=final_state,
    )


def parse_executive_proposal(path: Path | str) -> dict[str, object]:
    """Parse and validate the checked-in executive proposal shape."""

    payload = _load_json_object(Path(path), "executive proposal")
    _require_exact_keys(
        payload,
        {
            "decision_type",
            "rationale",
            "supporting_evidence_ids",
            "objective",
            "human_escalation",
        },
        "executive proposal",
    )
    decision_type = _require_string(
        payload["decision_type"], "executive proposal decision_type"
    )
    allowed_types = {item.value for item in ExecutiveDecisionType}
    if decision_type not in allowed_types:
        raise StructuredOutputError(
            f"executive proposal decision_type must be one of: "
            f"{', '.join(sorted(allowed_types))}"
        )

    objective = _parse_objective_payload(payload["objective"])
    escalation = _parse_escalation_payload(payload["human_escalation"])
    if decision_type == ExecutiveDecisionType.CONTINUE.value:
        if objective is None or escalation is not None:
            raise StructuredOutputError(
                "a continue proposal requires objective and null human_escalation"
            )
    elif decision_type == ExecutiveDecisionType.HUMAN_ESCALATION.value:
        if escalation is None or objective is not None:
            raise StructuredOutputError(
                "a human_escalation proposal requires human_escalation "
                "and null objective"
            )
    elif objective is not None or escalation is not None:
        raise StructuredOutputError(
            "success and stop proposals require null objective and "
            "human_escalation"
        )

    return {
        "decision_type": decision_type,
        "rationale": _require_string(
            payload["rationale"], "executive proposal rationale"
        ),
        "supporting_evidence_ids": _require_string_tuple(
            payload["supporting_evidence_ids"],
            "executive proposal supporting_evidence_ids",
        ),
        "objective": objective,
        "human_escalation": escalation,
    }


def parse_execution_result(
    path: Path | str, workspace: Path | str
) -> dict[str, object]:
    """Parse execution output and verify every referenced artifact."""

    payload = _load_json_object(Path(path), "execution result")
    _require_exact_keys(
        payload,
        {
            "summary",
            "observations",
            "artifact_paths",
            "facts",
            "assumptions",
            "open_questions",
        },
        "execution result",
    )
    observations = _require_string_tuple(
        payload["observations"], "execution result observations"
    )
    if not observations:
        raise StructuredOutputError(
            "execution result observations must not be empty"
        )
    raw_paths = _require_string_tuple(
        payload["artifact_paths"], "execution result artifact_paths"
    )
    if not raw_paths:
        raise StructuredOutputError(
            "execution result artifact_paths must not be empty"
        )
    artifact_paths = _validate_artifact_paths(Path(workspace), raw_paths)

    return {
        "summary": _require_string(
            payload["summary"], "execution result summary"
        ),
        "observations": observations,
        "artifact_paths": artifact_paths,
        "facts": _require_string_tuple(
            payload["facts"], "execution result facts"
        ),
        "assumptions": _require_string_tuple(
            payload["assumptions"], "execution result assumptions"
        ),
        "open_questions": _require_string_tuple(
            payload["open_questions"], "execution result open_questions"
        ),
    }


def _prepare_workspace(
    root: Path, fixture_path: Path
) -> tuple[FileCompanyStore, Mandate, CompanyState, Path]:
    root.mkdir(parents=True, exist_ok=True)
    execution_workspace = root / "execution-workspace"
    execution_workspace.mkdir(parents=True, exist_ok=True)
    fixture_target = execution_workspace / "candidate-brief.md"
    fixture_contents = fixture_path.read_text(encoding="utf-8")
    if fixture_target.exists():
        if fixture_target.read_text(encoding="utf-8") != fixture_contents:
            raise CodexVerticalSliceError(
                "demonstration candidate-brief.md differs from the "
                "checked-in synthetic fixture"
            )
    else:
        fixture_target.write_text(fixture_contents, encoding="utf-8")

    expected_mandate = Mandate(
        id=_MANDATE_ID,
        description=(
            "Using the supplied candidate brief, identify one promising AI "
            "product opportunity and determine the next evidence-producing "
            "validation step."
        ),
        constraints=(
            "Use only the supplied synthetic candidate brief in cycle 1.",
            "Do not claim that synthetic evidence proves real market demand.",
            "Do not execute Objective 2 in this demonstration.",
        ),
        success_criteria=(
            "One candidate hypothesis is selected with explicit uncertainty.",
            "A materially different real evidence-producing validation step "
            "is selected as Objective 2.",
        ),
        stop_conditions=(
            "Stop after Objective 2 is selected and persisted.",
        ),
    )
    initial_state = CompanyState(
        mandate_id=expected_mandate.id,
        status=MandateStatus.ACTIVE,
        summary=(
            "The synthetic candidate brief is available, but the candidates "
            "have not been compared."
        ),
        facts=(
            "The candidate brief is synthetic and contains no real "
            "market-demand evidence.",
        ),
        open_questions=(
            "Which candidate is the strongest hypothesis to validate next?",
        ),
    )
    store = FileCompanyStore(root / "company-store")
    try:
        mandate = store.load_mandate(expected_mandate.id)
    except FileNotFoundError:
        store.save_mandate(expected_mandate)
        mandate = expected_mandate
    if mandate != expected_mandate:
        raise CodexVerticalSliceError(
            "the persisted demonstration mandate does not match this fixture"
        )

    try:
        state = store.load_state(mandate.id)
    except FileNotFoundError:
        store.save_state(initial_state)
        state = initial_state
    if state != initial_state:
        raise CodexVerticalSliceError(
            "the demonstration workspace is not at its initial state; "
            "use a new workspace for this Phase 5 run"
        )
    return store, mandate, state, execution_workspace


def _resolve_codex_executable(
    requested: str | None, command_function: CommandFunction | None
) -> str:
    if requested is not None:
        return requested
    executable = shutil.which("codex")
    if executable is None:
        if command_function is not None:
            return "codex"
        raise CodexVerticalSliceError(
            "Codex CLI executable is unavailable; install it and ensure "
            "'codex' is on PATH"
        )
    return executable


def _invoke_codex(
    *,
    executable: str,
    role: str,
    prompt: str,
    workspace: Path,
    schema_path: Path,
    output_path: Path,
    sandbox: str,
    command_function: CommandFunction | None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.unlink(missing_ok=True)
    command = [
        executable,
        "exec",
        "--ephemeral",
        "--sandbox",
        sandbox,
        "--cd",
        str(workspace),
        "--skip-git-repo-check",
        "--output-schema",
        str(schema_path),
        "--output-last-message",
        str(output_path),
        "-",
    ]
    runner = command_function or _run_subprocess
    try:
        completed = runner(command, prompt)
    except FileNotFoundError as exc:
        raise CodexVerticalSliceError(
            "Codex CLI executable is unavailable"
        ) from exc
    except OSError as exc:
        raise CodexVerticalSliceError(
            f"Codex CLI could not be launched for {role}: {exc}"
        ) from exc
    if completed.returncode != 0:
        raise CodexVerticalSliceError(
            f"Codex {role} invocation exited with status "
            f"{completed.returncode}"
        )
    if not output_path.is_file():
        raise CodexVerticalSliceError(
            f"Codex {role} invocation did not create structured output: "
            f"{output_path}"
        )


def _run_subprocess(
    command: list[str], prompt: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        input=prompt,
        text=True,
        capture_output=True,
        check=False,
        shell=False,
    )


def _proposal_records(
    proposal: dict[str, object], mandate: Mandate, *, cycle: int
) -> tuple[ExecutiveDecision, Objective | None, HumanEscalation | None]:
    decision_type = ExecutiveDecisionType(str(proposal["decision_type"]))
    objective_payload = proposal["objective"]
    escalation_payload = proposal["human_escalation"]
    objective = None
    escalation = None

    if isinstance(objective_payload, dict):
        objective = Objective(
            id=f"objective-{cycle}",
            mandate_id=mandate.id,
            outcome=str(objective_payload["outcome"]),
            rationale=str(objective_payload["rationale"]),
            constraints=objective_payload["constraints"],
            acceptance_criteria=objective_payload["acceptance_criteria"],
            expected_evidence=objective_payload["expected_evidence"],
        )
    if isinstance(escalation_payload, dict):
        escalation = HumanEscalation(
            id=f"escalation-{cycle}",
            mandate_id=mandate.id,
            question=str(escalation_payload["question"]),
            reason=str(escalation_payload["reason"]),
            evidence_ids=escalation_payload["evidence_ids"],
            options=escalation_payload["options"],
        )

    decision = ExecutiveDecision(
        id=f"decision-{cycle}",
        mandate_id=mandate.id,
        decision_type=decision_type,
        rationale=str(proposal["rationale"]),
        objective_id=objective.id if objective is not None else None,
        human_escalation_id=(
            escalation.id if escalation is not None else None
        ),
        supporting_evidence_ids=proposal["supporting_evidence_ids"],
    )
    return decision, objective, escalation


def _require_continue(
    decision: ExecutiveDecision,
    objective: Objective | None,
    escalation: HumanEscalation | None,
    *,
    cycle: int,
) -> None:
    if (
        decision.decision_type is not ExecutiveDecisionType.CONTINUE
        or objective is None
        or escalation is not None
    ):
        raise CodexVerticalSliceError(
            f"executive cycle {cycle} must produce a CONTINUE decision "
            "for this demonstration"
        )


def _persist_authorization(
    store: FileCompanyStore,
    state: CompanyState,
    decision: ExecutiveDecision,
    objective: Objective,
) -> CompanyState:
    unknown_evidence = set(decision.supporting_evidence_ids) - set(
        state.relevant_evidence_ids
    )
    if unknown_evidence:
        raise CodexVerticalSliceError(
            "executive proposal references unknown evidence: "
            + ", ".join(sorted(unknown_evidence))
        )
    store.save_objective(objective)
    store.save_decision(decision)
    updated = apply_executive_decision(state, decision, objective)
    store.save_state(updated)
    return updated


def _execution_records(
    *,
    execution: dict[str, object],
    state: CompanyState,
    objective: Objective,
    decision: ExecutiveDecision,
) -> tuple[tuple[Evidence, ...], CompanyStateUpdate]:
    artifact_paths = execution["artifact_paths"]
    observations = execution["observations"]
    reported_facts = execution["facts"]
    assert isinstance(artifact_paths, tuple)
    assert isinstance(observations, tuple)
    assert isinstance(reported_facts, tuple)
    provenance = (
        f"codex-exec:{objective.id}; artifacts="
        + ",".join(artifact_paths)
    )
    evidence_observations = observations + tuple(
        f"Worker-reported fact, not independently verified: {item}"
        for item in reported_facts
    )
    evidence = tuple(
        Evidence(
            id=f"evidence-1-{index}",
            mandate_id=state.mandate_id,
            source=provenance,
            observation=observation,
            objective_id=objective.id,
            decision_id=decision.id,
        )
        for index, observation in enumerate(evidence_observations, start=1)
    )
    verified_fact = (
        f"Codex created {len(artifact_paths)} verified artifact file(s) "
        f"for {objective.id}: {', '.join(artifact_paths)}."
    )
    assumptions = execution["assumptions"]
    open_questions = execution["open_questions"]
    assert isinstance(assumptions, tuple)
    assert isinstance(open_questions, tuple)
    state_update = CompanyStateUpdate(
        summary=(
            f"Objective 1 execution completed. Codex reported: "
            f"{execution['summary']}"
        ),
        facts=_deduplicate(state.facts + (verified_fact,)),
        assumptions=_deduplicate(state.assumptions + assumptions),
        open_questions=open_questions,
        relevant_evidence_ids=(
            state.relevant_evidence_ids
            + tuple(record.id for record in evidence)
        ),
    )
    return evidence, state_update


def _validate_materially_different(
    objective_1: Objective,
    objective_2: Objective,
    decision_2: ExecutiveDecision,
    new_evidence_ids: tuple[str, ...],
) -> None:
    if objective_1.outcome.strip().casefold() == objective_2.outcome.strip().casefold():
        raise CodexVerticalSliceError(
            "Objective 2 must have a different outcome from Objective 1"
        )
    if not set(decision_2.supporting_evidence_ids).intersection(
        new_evidence_ids
    ):
        raise CodexVerticalSliceError(
            "Objective 2 must cite evidence persisted from Objective 1"
        )


def _executive_prompt(
    *,
    cycle: int,
    mandate: Mandate,
    state: CompanyState,
    evidence: tuple[Evidence, ...],
    artifact_contents: tuple[tuple[str, str], ...],
) -> str:
    context = {
        "mandate": {
            "id": mandate.id,
            "description": mandate.description,
            "constraints": mandate.constraints,
            "success_criteria": mandate.success_criteria,
            "stop_conditions": mandate.stop_conditions,
        },
        "company_state": {
            "status": state.status.value,
            "summary": state.summary,
            "facts": state.facts,
            "assumptions": state.assumptions,
            "open_questions": state.open_questions,
            "relevant_evidence_ids": state.relevant_evidence_ids,
        },
        "relevant_evidence": [
            {
                "id": record.id,
                "source": record.source,
                "observation": record.observation,
                "objective_id": record.objective_id,
            }
            for record in evidence
        ],
        "artifact_contents": [
            {"path": path, "content": content}
            for path, content in artifact_contents
        ],
        "available_execution_capability": (
            "One Codex exec run can inspect candidate-brief.md and create "
            "UTF-8 analysis artifacts under artifacts/."
        ),
    }
    cycle_instruction = (
        "Select one bounded objective that compares or investigates the "
        "synthetic candidates."
        if cycle == 1
        else (
            "Use the persisted evidence and artifact contents. Select a "
            "materially different evidence-producing validation objective "
            "for the chosen hypothesis, such as a demand or willingness-to-pay "
            "experiment. Cite at least one relevant evidence ID."
        )
    )
    return (
        "You are the constrained executive decision function for Loop Engine.\n"
        "You may choose only continue, success, stop, or human_escalation. "
        "You cannot edit files or execute the objective. Do not broaden the "
        "mandate or treat synthetic claims as real market evidence.\n"
        f"This is executive cycle {cycle}. {cycle_instruction}\n"
        "For this demonstration, return a continue decision with exactly one "
        "bounded objective. IDs are assigned by the runtime, so do not invent "
        "record IDs. Return only the JSON shape required by the supplied schema.\n\n"
        "Durable context:\n"
        + json.dumps(context, indent=2, ensure_ascii=False)
    )


def _execution_prompt(mandate: Mandate, objective: Objective) -> str:
    context = {
        "mandate": {
            "description": mandate.description,
            "constraints": mandate.constraints,
        },
        "objective": {
            "outcome": objective.outcome,
            "rationale": objective.rationale,
            "constraints": objective.constraints,
            "acceptance_criteria": objective.acceptance_criteria,
            "expected_evidence": objective.expected_evidence,
        },
    }
    return (
        "You are the concrete bounded execution capability, not the executive.\n"
        "Inspect candidate-brief.md and complete only the authorized objective. "
        "Create one or more UTF-8 text analysis artifacts under artifacts/. "
        "Do not edit files outside artifacts/. Do not select the next company "
        "objective, declare mandate success, or change the mandate.\n"
        "The fixture is synthetic. Clearly distinguish comparison findings from "
        "real demand evidence. Return only the JSON shape required by the "
        "supplied execution-result schema, with artifact paths relative to this "
        "workspace. Facts in the result remain worker claims until the runtime "
        "accepts them.\n\n"
        "Authorized context:\n"
        + json.dumps(context, indent=2, ensure_ascii=False)
    )


def _parse_objective_payload(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StructuredOutputError(
            "executive proposal objective must be an object or null"
        )
    _require_exact_keys(
        value,
        {
            "outcome",
            "rationale",
            "constraints",
            "acceptance_criteria",
            "expected_evidence",
        },
        "executive proposal objective",
    )
    return {
        "outcome": _require_string(
            value["outcome"], "executive proposal objective outcome"
        ),
        "rationale": _require_string(
            value["rationale"], "executive proposal objective rationale"
        ),
        "constraints": _require_string_tuple(
            value["constraints"], "executive proposal objective constraints"
        ),
        "acceptance_criteria": _require_string_tuple(
            value["acceptance_criteria"],
            "executive proposal objective acceptance_criteria",
        ),
        "expected_evidence": _require_string_tuple(
            value["expected_evidence"],
            "executive proposal objective expected_evidence",
        ),
    }


def _parse_escalation_payload(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise StructuredOutputError(
            "executive proposal human_escalation must be an object or null"
        )
    _require_exact_keys(
        value,
        {"question", "reason", "evidence_ids", "options"},
        "executive proposal human_escalation",
    )
    return {
        "question": _require_string(
            value["question"], "human escalation question"
        ),
        "reason": _require_string(
            value["reason"], "human escalation reason"
        ),
        "evidence_ids": _require_string_tuple(
            value["evidence_ids"], "human escalation evidence_ids"
        ),
        "options": _require_string_tuple(
            value["options"], "human escalation options"
        ),
    }


def _validate_artifact_paths(
    workspace: Path, raw_paths: tuple[str, ...]
) -> tuple[str, ...]:
    workspace_root = workspace.resolve()
    normalized: list[str] = []
    for raw_path in raw_paths:
        relative = Path(raw_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise StructuredOutputError(
                f"artifact path must stay relative to the workspace: {raw_path}"
            )
        if not relative.parts or relative.parts[0] != "artifacts":
            raise StructuredOutputError(
                f"artifact path must be under artifacts/: {raw_path}"
            )
        artifact = (workspace_root / relative).resolve()
        if not artifact.is_relative_to(workspace_root):
            raise StructuredOutputError(
                f"artifact path escapes the workspace: {raw_path}"
            )
        if not artifact.is_file():
            raise StructuredOutputError(
                f"referenced artifact does not exist: {raw_path}"
            )
        normalized_path = relative.as_posix()
        if normalized_path not in normalized:
            normalized.append(normalized_path)
    return tuple(normalized)


def _read_artifacts(
    workspace: Path, paths: tuple[str, ...]
) -> tuple[tuple[str, str], ...]:
    contents: list[tuple[str, str]] = []
    remaining = 40_000
    for path in paths:
        text = (workspace / Path(path)).read_text(encoding="utf-8")
        excerpt = text[: min(20_000, remaining)]
        if len(excerpt) < len(text):
            excerpt += "\n[artifact truncated by Loop Engine]"
        contents.append((path, excerpt))
        remaining -= len(excerpt)
        if remaining <= 0:
            break
    return tuple(contents)


def _snapshot_protected_files(
    workspace: Path, allowed_output_path: Path
) -> dict[str, str]:
    workspace_root = workspace.resolve()
    try:
        allowed_output = allowed_output_path.resolve().relative_to(
            workspace_root
        )
    except ValueError as exc:
        raise CodexVerticalSliceError(
            "bounded execution output path must be inside its workspace"
        ) from exc

    snapshot: dict[str, str] = {}
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace)
        if relative.parts[0] == "artifacts" or relative == allowed_output:
            continue
        if path.is_symlink():
            snapshot[relative.as_posix()] = f"symlink:{path.readlink()}"
        elif path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            snapshot[relative.as_posix()] = f"file:{digest}"
    return snapshot


def _verify_protected_files(
    workspace: Path,
    allowed_output_path: Path,
    before: dict[str, str],
) -> None:
    after = _snapshot_protected_files(workspace, allowed_output_path)
    before_paths = set(before)
    after_paths = set(after)
    added = sorted(after_paths - before_paths)
    deleted = sorted(before_paths - after_paths)
    modified = sorted(
        path
        for path in before_paths & after_paths
        if before[path] != after[path]
    )
    if not (added or deleted or modified):
        return

    changes: list[str] = []
    if added:
        changes.append("added " + ", ".join(added))
    if deleted:
        changes.append("deleted " + ", ".join(deleted))
    if modified:
        changes.append("modified " + ", ".join(modified))
    raise CodexVerticalSliceError(
        "Codex bounded execution changed protected files outside artifacts/ "
        "and its expected structured output: " + "; ".join(changes)
    )


def _load_json_object(path: Path, label: str) -> dict[str, object]:
    if not path.is_file():
        raise StructuredOutputError(f"{label} file is missing: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StructuredOutputError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise StructuredOutputError(f"{label} must be a JSON object")
    return payload


def _require_exact_keys(
    payload: dict[str, object], expected: set[str], label: str
) -> None:
    actual = set(payload)
    if actual == expected:
        return
    details: list[str] = []
    missing = expected - actual
    unexpected = actual - expected
    if missing:
        details.append("missing " + ", ".join(sorted(missing)))
    if unexpected:
        details.append("unexpected " + ", ".join(sorted(unexpected)))
    raise StructuredOutputError(f"{label} has invalid fields: {'; '.join(details)}")


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StructuredOutputError(f"{label} must be a non-empty string")
    return value


def _require_string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise StructuredOutputError(f"{label} must be an array")
    return tuple(
        _require_string(item, f"{label} item") for item in value
    )


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise CodexVerticalSliceError(f"{label} is missing: {path}")


def _deduplicate(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
