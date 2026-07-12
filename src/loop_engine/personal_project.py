"""Personal-use project workspace built on the durable Codex runner."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, replace
from pathlib import Path

from loop_engine.codex_durable_run import (
    CHECKPOINT_NAME,
    CodexDurableRunError,
    DurableRunSummary,
    RunCheckpoint,
    RunnerDefinition,
    _artifact_excerpts,
    _json_value,
    _load_checkpoint,
    _reconstruct_pre_execution_state,
    _reject_symlinks,
    _save_checkpoint,
    _validate_checkpoint,
    run_project_cycles,
)
from loop_engine.company_models import CompanyState, Mandate, MandateStatus
from loop_engine.company_store import FileCompanyStore
from loop_engine.executive_loop import apply_executive_decision

PROJECT_NAME = "project.json"
MANDATE_NAME = "mandate.json"
PROJECT_KEYS = {"schema_version", "mandate_id", "mandate_sha256"}
MANDATE_KEYS = {"id", "description", "constraints", "success_criteria", "stop_conditions"}


class PersonalProjectError(CodexDurableRunError):
    """Raised when a personal project is malformed or unsafe."""


def initial_company_state(mandate: Mandate) -> CompanyState:
    return CompanyState(
        mandate_id=mandate.id,
        status=MandateStatus.ACTIVE,
        summary="No bounded objective has been executed yet.",
        open_questions=("What bounded objective should be pursued first?",),
    )


def parse_mandate_file(path: Path | str) -> tuple[Mandate, bytes]:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise PersonalProjectError(f"mandate file does not exist or is unsafe: {source}")
    data = source.read_bytes()
    try:
        text = data.decode("utf-8")
        payload = json.loads(text, object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonalProjectError(f"mandate contains invalid JSON: {exc}") from exc
    return _parse_mandate(payload), data


def initialize_project(workspace: Path | str, mandate_file: Path | str) -> Mandate:
    mandate, source_bytes = parse_mandate_file(mandate_file)
    root = Path(workspace).absolute()
    _validate_workspace_path(root)
    if root.exists() and any(root.iterdir()):
        raise PersonalProjectError("workspace already contains content; refusing to initialize")
    root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(
        dir=root.parent, prefix=f".{root.name}.init."
    ))
    backup = None
    try:
        _build_project(staging, mandate, source_bytes)
        _, _, staged_mandate, _ = load_project(staging)
        if staged_mandate != mandate:
            raise PersonalProjectError(
                "validated staging Mandate does not match the input mandate"
            )
        if root.exists():
            backup = Path(tempfile.mkdtemp(
                dir=root.parent, prefix=f".{root.name}.empty."
            ))
            backup.rmdir()
            os.replace(root, backup)
        try:
            os.replace(staging, root)
        except Exception:
            if backup is not None:
                os.replace(backup, root)
                backup = None
            raise
        if backup is not None:
            backup.rmdir()
            backup = None
    finally:
        if staging.exists():
            shutil.rmtree(staging)
        if backup is not None and backup.exists():
            if not root.exists():
                os.replace(backup, root)
            else:
                backup.rmdir()
    return mandate


def _build_project(root: Path, mandate: Mandate, source_bytes: bytes) -> None:
    canonical = root / MANDATE_NAME
    authorized = root / "execution-workspace" / "authorized-inputs" / MANDATE_NAME
    authorized.parent.mkdir(parents=True)
    (root / "execution-workspace" / ".codex-output").mkdir()
    (root / "execution-workspace" / "artifacts").mkdir()
    (root / ".codex-output").mkdir()
    canonical.write_bytes(source_bytes)
    authorized.write_bytes(source_bytes)
    _write_json(root / PROJECT_NAME, {
        "schema_version": 1,
        "mandate_id": mandate.id,
        "mandate_sha256": hashlib.sha256(source_bytes).hexdigest(),
    })
    store = FileCompanyStore(root / "company-store")
    store.save_mandate(mandate)
    store.save_state(initial_company_state(mandate))
    _save_checkpoint(
        root / CHECKPOINT_NAME,
        RunCheckpoint(1, mandate.id, 1, "awaiting_executive"),
    )


def load_project(workspace: Path | str):
    root = Path(workspace)
    _validate_workspace_path(root, require_existing=True)
    project = _load_json(root / PROJECT_NAME, "project metadata")
    if set(project) != PROJECT_KEYS or project.get("schema_version") != 1:
        raise PersonalProjectError("project.json must use the exact supported schema")
    mandate_id = project.get("mandate_id")
    digest = project.get("mandate_sha256")
    if not isinstance(mandate_id, str) or not mandate_id.strip():
        raise PersonalProjectError("project mandate_id must be a non-empty string")
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise PersonalProjectError("project mandate_sha256 must be a lowercase SHA-256 digest")
    canonical = root / MANDATE_NAME
    authorized = root / "execution-workspace" / "authorized-inputs" / MANDATE_NAME
    if canonical.is_symlink() or not canonical.is_file():
        raise PersonalProjectError("canonical mandate.json is missing or unsafe")
    data = canonical.read_bytes()
    if hashlib.sha256(data).hexdigest() != digest:
        raise PersonalProjectError("canonical mandate.json hash does not match project.json")
    try:
        payload = json.loads(data.decode("utf-8"), object_pairs_hook=_unique_object)
        mandate = _parse_mandate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonalProjectError(f"canonical mandate.json is invalid: {exc}") from exc
    if mandate.id != mandate_id:
        raise PersonalProjectError("canonical mandate ID does not match project.json")
    if authorized.is_symlink() or not authorized.is_file() or authorized.read_bytes() != data:
        raise PersonalProjectError("authorized mandate copy is missing or differs from canonical mandate")
    _reject_symlinks(root / "execution-workspace")
    store_root = root / "company-store"
    if store_root.is_symlink() or not store_root.is_dir():
        raise PersonalProjectError("company-store is missing or unsafe")
    store = FileCompanyStore(store_root)
    try:
        stored = store.load_mandate(mandate.id)
        if stored != mandate:
            raise PersonalProjectError("stored Mandate does not match canonical mandate.json")
        store.load_state(mandate.id)
        checkpoint = _load_checkpoint(root / CHECKPOINT_NAME, mandate.id, project_definition())
        definition = project_definition()
        _validate_checkpoint(checkpoint, store, root, mandate, definition)
        _validate_exact_state(root, store, mandate, checkpoint, definition)
    except (FileNotFoundError, ValueError) as exc:
        raise PersonalProjectError(f"project company state is invalid: {exc}") from exc
    return root.resolve(), store, mandate, checkpoint


def run_personal_project(workspace: Path | str, *, max_cycles: int,
                         codex_executable: str | None = None,
                         command_function=None) -> DurableRunSummary:
    root, store, mandate, checkpoint = load_project(workspace)
    return run_project_cycles(
        root, store=store, mandate=mandate, checkpoint=checkpoint,
        definition=project_definition(), max_cycles=max_cycles,
        codex_executable=codex_executable, command_function=command_function,
    )


def project_definition() -> RunnerDefinition:
    return RunnerDefinition(initial_company_state, _executive_prompt,
                            _execution_prompt, _validate_proposal)


def status_text(workspace: Path | str) -> str:
    _, store, mandate, checkpoint = load_project(workspace)
    state = store.load_state(mandate.id)
    objective = store.load_objective(mandate.id, state.active_objective_id) if state.active_objective_id else None
    escalation = store.load_escalation(mandate.id, state.pending_human_escalation_id) if state.pending_human_escalation_id else None
    lines = [
        f"Mandate ID: {mandate.id}", f"Mandate status: {state.status.value}",
        f"Checkpoint stage: {checkpoint.stage}", f"Current cycle: {checkpoint.cycle_number}",
        f"Active objective ID: {objective.id if objective else '(none)'}",
        f"Active objective outcome: {objective.outcome if objective else '(none)'}",
        f"Pending escalation ID: {escalation.id if escalation else '(none)'}",
        f"Pending escalation question: {escalation.question if escalation else '(none)'}",
        f"Summary: {state.summary}", "Facts:", *_section(state.facts),
        "Assumptions:", *_section(state.assumptions), "Open questions:",
        *_section(state.open_questions), "Relevant evidence IDs:",
        *_section(state.relevant_evidence_ids),
    ]
    return "\n".join(lines)


def history_text(workspace: Path | str) -> str:
    _, store, mandate, checkpoint = load_project(workspace)
    blocks = []
    for cycle in range(1, checkpoint.cycle_number + 1):
        try:
            decision = store.load_decision(mandate.id, f"decision-{cycle}")
        except FileNotFoundError:
            break
        lines = [f"Cycle: {cycle}", f"Decision ID: {decision.id}",
                 f"Decision type: {decision.decision_type.value}",
                 f"Rationale: {decision.rationale}", "Supporting evidence IDs:",
                 *_section(decision.supporting_evidence_ids)]
        if decision.objective_id:
            objective = store.load_objective(mandate.id, decision.objective_id)
            lines += [f"Objective ID: {objective.id}", f"Objective outcome: {objective.outcome}"]
        if decision.human_escalation_id:
            item = store.load_escalation(mandate.id, decision.human_escalation_id)
            lines += [f"Escalation ID: {item.id}", f"Escalation question: {item.question}"]
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) if blocks else "(none)"


def _executive_prompt(mandate, state, evidence, excerpts, cycle):
    return (
        "You are the constrained executive for Loop Engine. Select exactly one existing decision type: "
        "continue, success, stop, or human_escalation. Authorize only one bounded objective at a time, "
        "chosen from current durable evidence rather than a complete static plan. Do not claim success "
        "unless durable evidence supports every success criterion. Worker claims are not independently "
        "verified facts. Do not broaden authority, relax constraints, or perform external-world actions "
        "unless the mandate explicitly authorizes them. Request human input when owner judgment or "
        "authority is required. Durable IDs are assigned by the runtime.\n\n"
        f"Cycle: {cycle}\nMandate: {_json_value(asdict(mandate))}\n"
        f"Current state: {_json_value(asdict(state))}\n"
        f"Evidence: {[_json_value(asdict(x)) for x in evidence]}\n"
        f"Prior artifact excerpts: {excerpts}\n\nOutput only the required schema object."
    )


def _execution_prompt(mandate, objective, state, cycle):
    return (
        f"Execute only this bounded objective for cycle {cycle}.\nMandate: {_json_value(asdict(mandate))}\n"
        f"Objective: {_json_value(asdict(objective))}\nState: {_json_value(asdict(state))}\n"
        "The only initial authorized file is authorized-inputs/mandate.json. Write only the structured "
        f"output and files under artifacts/cycle-{cycle}/. That directory already exists; write artifact "
        "files inside it and preserve its inherited permissions. Do not replace, rename, delete, or recreate "
        "that directory, and do not modify prior cycle directories. Preserve authorized inputs, prior outputs, "
        "prior artifacts, and unexpected files. Report artifact paths relative to this execution workspace. "
        "Do not choose the next objective, declare mandate success, or modify durable project records. "
        "Output only the required schema object."
    )


def _validate_proposal(proposal, cycle):
    return None


def _validate_exact_state(root, store, mandate, checkpoint, definition):
    if checkpoint.stage in ("proposal_captured", "execution_captured"):
        return
    state = store.load_state(mandate.id)
    base = _reconstruct_pre_execution_state(
        root, store, mandate, checkpoint.cycle_number, definition
    )
    if checkpoint.stage == "awaiting_executive":
        expected = base
    elif checkpoint.stage == "objective_active":
        expected = replace(base, active_objective_id=f"objective-{checkpoint.cycle_number}")
    else:
        decision = store.load_decision(
            mandate.id, f"decision-{checkpoint.cycle_number}"
        )
        objective = (store.load_objective(mandate.id, decision.objective_id)
                     if decision.objective_id else None)
        escalation = (store.load_escalation(mandate.id, decision.human_escalation_id)
                      if decision.human_escalation_id else None)
        expected = apply_executive_decision(base, decision, objective, escalation)
    if state != expected:
        raise PersonalProjectError(
            "company state does not exactly match deterministic project history"
        )


def _parse_mandate(payload) -> Mandate:
    if not isinstance(payload, dict) or set(payload) != MANDATE_KEYS:
        raise PersonalProjectError("mandate must contain exactly: " + ", ".join(sorted(MANDATE_KEYS)))
    for key in ("id", "description"):
        if not isinstance(payload[key], str) or not payload[key].strip():
            raise PersonalProjectError(f"mandate {key} must be a non-empty string")
    collections = {}
    for key in ("constraints", "success_criteria", "stop_conditions"):
        value = payload[key]
        if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
            raise PersonalProjectError(f"mandate {key} must be an array of non-empty strings")
        collections[key] = tuple(value)
    return Mandate(payload["id"], payload["description"], **collections)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _validate_workspace_path(root: Path, require_existing=False):
    if root.is_symlink():
        raise PersonalProjectError("workspace path must not be a symlink")
    current = root.absolute()
    for parent in (current, *current.parents):
        if parent.exists() and parent.is_symlink():
            raise PersonalProjectError("workspace path must not contain symlink components")
    if root.exists() and not root.is_dir():
        raise PersonalProjectError("workspace path must be a directory")
    if require_existing and not root.is_dir():
        raise PersonalProjectError("personal project workspace does not exist")


def _load_json(path, label):
    if path.is_symlink() or not path.is_file():
        raise PersonalProjectError(f"{label} is missing or unsafe")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PersonalProjectError(f"{label} contains malformed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PersonalProjectError(f"{label} must contain a JSON object")
    return value


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def _section(items):
    return [f"- {item}" for item in items] if items else ["(none)"]
