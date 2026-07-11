"""Concrete durable multi-cycle Codex CLI runner for architecture v0.3."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path, PurePosixPath

from loop_engine.codex_vertical_slice import (
    StructuredOutputError,
    parse_executive_proposal,
)
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
from loop_engine.executive_loop import apply_executive_decision, apply_objective_result

CommandFunction = Callable[[list[str], str], subprocess.CompletedProcess[str]]

MANDATE_ID = "synthetic-resumable-product-validation"
CHECKPOINT_NAME = "codex-run-checkpoint.json"
STAGES = {
    "awaiting_executive", "proposal_captured", "objective_active",
    "execution_captured", "needs_human", "terminal",
}
_CHECKPOINT_KEYS = {
    "schema_version", "mandate_id", "cycle_number", "stage",
    "captured_executive_proposal", "captured_execution_result",
    "protected_file_hashes",
}
_EXCERPT_LIMIT = 4_000
_TOTAL_CONTEXT_LIMIT = 16_000


class CodexDurableRunError(RuntimeError):
    """Raised when durable runner state is invalid or cannot safely advance."""


@dataclass(frozen=True)
class RunCheckpoint:
    schema_version: int
    mandate_id: str
    cycle_number: int
    stage: str
    captured_executive_proposal: dict[str, object] | None = None
    captured_execution_result: dict[str, object] | None = None
    protected_file_hashes: dict[str, str] | None = None


@dataclass(frozen=True)
class DurableRunSummary:
    mandate_id: str
    starting_stage: str
    ending_stage: str
    starting_cycle_number: int
    ending_cycle_number: int
    executed_objective_ids: tuple[str, ...]
    evidence_ids_created: tuple[str, ...]
    mandate_status: MandateStatus
    next_active_objective_id: str | None
    pending_escalation_id: str | None
    is_terminal: bool


def run_durable_cycles(
    workspace: Path | str,
    *,
    max_cycles: int,
    codex_executable: str | None = None,
    command_function: CommandFunction | None = None,
    fixture_path: Path | None = None,
    schema_directory: Path | None = None,
) -> DurableRunSummary:
    """Resume the Phase 6 foreground runner and commit at most max_cycles results."""
    if isinstance(max_cycles, bool) or not isinstance(max_cycles, int) or max_cycles <= 0:
        raise ValueError("max_cycles must be a positive integer")
    root = Path(workspace).resolve()
    repository = Path(__file__).resolve().parents[2]
    fixture = fixture_path or repository / "examples/fixtures/synthetic_product_opportunities.md"
    schemas = schema_directory or repository / "schemas"
    for path, label in ((fixture, "synthetic candidate fixture"),
                        (schemas / "executive_proposal.schema.json", "executive JSON Schema"),
                        (schemas / "execution_result.schema.json", "execution JSON Schema")):
        if not path.is_file():
            raise CodexDurableRunError(f"{label} does not exist: {path}")

    store, mandate, checkpoint = _initialize_or_resume(root, fixture)
    starting = checkpoint
    _validate_checkpoint(checkpoint, store, root, mandate)
    executable = _resolve_codex(codex_executable, command_function)
    executed: list[str] = []
    created_evidence: list[str] = []
    committed = 0

    while True:
        checkpoint = _load_checkpoint(root / CHECKPOINT_NAME)
        _validate_checkpoint(checkpoint, store, root, mandate)
        if checkpoint.stage in ("terminal", "needs_human"):
            break
        if committed >= max_cycles and checkpoint.stage == "objective_active":
            break
        if checkpoint.stage == "awaiting_executive":
            checkpoint = _capture_executive(
                root, store, mandate, checkpoint, executable,
                schemas / "executive_proposal.schema.json", command_function,
            )
        elif checkpoint.stage == "proposal_captured":
            checkpoint = _commit_proposal(root, store, mandate, checkpoint)
        elif checkpoint.stage == "objective_active":
            checkpoint = _capture_execution(
                root, store, mandate, checkpoint, executable,
                schemas / "execution_result.schema.json", command_function,
            )
        elif checkpoint.stage == "execution_captured":
            objective_id, evidence_ids, newly_committed = _commit_execution(
                root, store, mandate, checkpoint
            )
            if newly_committed:
                executed.append(objective_id)
                created_evidence.extend(evidence_ids)
                committed += 1

    final_checkpoint = _load_checkpoint(root / CHECKPOINT_NAME)
    final_state = store.load_state(mandate.id)
    return DurableRunSummary(
        mandate.id, starting.stage, final_checkpoint.stage,
        starting.cycle_number, final_checkpoint.cycle_number,
        tuple(executed), tuple(created_evidence), final_state.status,
        final_state.active_objective_id, final_state.pending_human_escalation_id,
        final_checkpoint.stage == "terminal",
    )


def _initialize_or_resume(root: Path, fixture: Path):
    checkpoint_path = root / CHECKPOINT_NAME
    store_root = root / "company-store"
    records_exist = store_root.exists() and any(store_root.rglob("*"))
    if checkpoint_path.exists():
        if not records_exist:
            raise CodexDurableRunError("checkpoint exists but company records are missing")
        store = FileCompanyStore(store_root)
        checkpoint = _load_checkpoint(checkpoint_path)
        try:
            mandate = store.load_mandate(checkpoint.mandate_id)
            store.load_state(checkpoint.mandate_id)
        except (FileNotFoundError, ValueError) as exc:
            raise CodexDurableRunError("checkpoint references missing mandate or state") from exc
        return store, mandate, checkpoint
    if records_exist:
        raise CodexDurableRunError("company records exist but the runner checkpoint is missing")

    root.mkdir(parents=True, exist_ok=True)
    candidate = root / "candidate-brief.md"
    candidate.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    mandate = _phase6_mandate()
    state = CompanyState(
        mandate_id=mandate.id, status=MandateStatus.ACTIVE,
        summary="The synthetic candidates have not yet been compared.",
        facts=("The candidate brief is synthetic and is not real demand evidence.",),
        open_questions=("Which candidate hypothesis should be validated?",),
    )
    store = FileCompanyStore(store_root)
    store.save_mandate(mandate)
    store.save_state(state)
    checkpoint = RunCheckpoint(1, mandate.id, 1, "awaiting_executive")
    _save_checkpoint(checkpoint_path, checkpoint)
    return store, mandate, checkpoint


def _phase6_mandate() -> Mandate:
    return Mandate(
        id=MANDATE_ID,
        description=(
            "Complete a staged synthetic product-validation exercise: first compare "
            "candidates and select one hypothesis, then design its real-evidence "
            "validation experiment, then assess readiness for later dogfooding."
        ),
        constraints=(
            "The fixture is synthetic; synthetic analysis is not real demand evidence.",
            "Do not perform outreach or claim real willingness to pay.",
            "External-world execution remains out of scope until Phase 7.",
            "Stage 1 must compare candidates, select exactly one hypothesis, and "
            "record uncertainty without designing the full validation experiment.",
            "Stage 2 must use the selected hypothesis and cycle-1 evidence to define "
            "a target buyer, method, commitment threshold, and unresolved risks.",
            "Stage 3 may assess whether the completed validation plan is specific "
            "enough for later Phase 7 dogfooding.",
        ),
        success_criteria=(
            "Stage 1 selected exactly one candidate hypothesis with explicit uncertainty.",
            "Stage 2 documented a concrete real-evidence validation experiment with "
            "target buyer, method, commitment threshold, and unresolved risks.",
            "Only after Stages 1 and 2, Stage 3 assessed the plan's specificity for "
            "later real-world dogfooding.",
        ),
        stop_conditions=(
            "Stop if progress requires actual outreach or authority outside this mandate.",
            "Request human input when a consequential choice cannot be made from evidence.",
        ),
    )


def _capture_executive(root, store, mandate, checkpoint, executable, schema, command_function):
    state = store.load_state(mandate.id)
    evidence = tuple(store.load_evidence(mandate.id, item) for item in state.relevant_evidence_ids)
    output = root / ".codex-output" / f"executive-{checkpoint.cycle_number}.json"
    if not output.exists():
        _invoke(executable, _executive_prompt(mandate, state, evidence, _artifact_excerpts(root), checkpoint.cycle_number),
                root, schema, output, "read-only", command_function, "executive")
    proposal = parse_executive_proposal(output)
    _validate_phase6_proposal(proposal, checkpoint.cycle_number)
    result = replace(checkpoint, stage="proposal_captured", captured_executive_proposal=proposal)
    _save_checkpoint(root / CHECKPOINT_NAME, result)
    return result


def _commit_proposal(root, store, mandate, checkpoint):
    proposal = checkpoint.captured_executive_proposal
    assert proposal is not None
    decision, objective, escalation = _proposal_records(proposal, mandate, checkpoint.cycle_number)
    state = store.load_state(mandate.id)
    expected_pre_state = _reconstruct_pre_execution_state(
        root, store, mandate, checkpoint.cycle_number
    )
    expected_post_state = apply_executive_decision(
        expected_pre_state, decision, objective, escalation
    )
    if state not in (expected_pre_state, expected_post_state):
        raise CodexDurableRunError(
            "captured proposal contradicts company state"
        )
    if objective is not None:
        store.save_objective(objective)
    if escalation is not None:
        store.save_escalation(escalation)
    store.save_decision(decision)
    if state == expected_pre_state:
        store.save_state(expected_post_state)
    stage = ("objective_active" if decision.decision_type is ExecutiveDecisionType.CONTINUE else
             "needs_human" if decision.decision_type is ExecutiveDecisionType.HUMAN_ESCALATION else "terminal")
    result = replace(checkpoint, stage=stage, captured_executive_proposal=None)
    _save_checkpoint(root / CHECKPOINT_NAME, result)
    return result


def _capture_execution(root, store, mandate, checkpoint, executable, schema, command_function):
    cycle = checkpoint.cycle_number
    objective = store.load_objective(mandate.id, f"objective-{cycle}")
    output = root / ".codex-output" / f"execution-{cycle}.json"
    if checkpoint.protected_file_hashes is None:
        if output.exists():
            raise CodexDurableRunError(
                "execution output exists without a durable pre-execution guard"
            )
        hashes = _snapshot_protected(root, cycle, output)
        checkpoint = replace(checkpoint, protected_file_hashes=hashes)
        _save_checkpoint(root / CHECKPOINT_NAME, checkpoint)
    assert checkpoint.protected_file_hashes is not None
    _verify_protected(root, cycle, output, checkpoint.protected_file_hashes)
    if not output.exists():
        _invoke(executable, _execution_prompt(mandate, objective, store.load_state(mandate.id), cycle),
                root, schema, output, "workspace-write", command_function, "bounded execution")
        _verify_protected(root, cycle, output, checkpoint.protected_file_hashes)
    execution = _parse_cycle_execution(output, root, cycle)
    result = replace(checkpoint, stage="execution_captured",
                     captured_execution_result=execution, protected_file_hashes=None)
    _save_checkpoint(root / CHECKPOINT_NAME, result)
    return result


def _commit_execution(root, store, mandate, checkpoint):
    cycle = checkpoint.cycle_number
    execution = checkpoint.captured_execution_result
    assert execution is not None
    objective = store.load_objective(mandate.id, f"objective-{cycle}")
    decision = store.load_decision(mandate.id, f"decision-{cycle}")
    state = store.load_state(mandate.id)
    pre_execution_state = _reconstruct_pre_execution_state(
        root, store, mandate, cycle
    )
    expected_active_state = replace(
        pre_execution_state, active_objective_id=objective.id
    )
    evidence, update = _execution_records(
        execution, expected_active_state, objective, decision, cycle
    )
    for item in evidence:
        store.save_evidence(item)
    if state.active_objective_id == objective.id:
        if state != expected_active_state:
            raise CodexDurableRunError(
                "execution checkpoint contradicts pre-result company state"
            )
        updated = apply_objective_result(
            state, replace(objective, status=ObjectiveStatus.SUCCEEDED), evidence, update
        )
        store.save_state(updated)
    else:
        expected_state = apply_objective_result(
            expected_active_state,
            replace(objective, status=ObjectiveStatus.SUCCEEDED),
            evidence,
            update,
        )
        if state != expected_state:
            raise CodexDurableRunError("execution checkpoint contradicts company state")
    result = RunCheckpoint(1, mandate.id, cycle + 1, "awaiting_executive")
    _save_checkpoint(root / CHECKPOINT_NAME, result)
    return objective.id, tuple(item.id for item in evidence), state == expected_active_state


def _reconstruct_pre_execution_state(root, store, mandate, cycle):
    """Rebuild the deterministic snapshot preceding one execution cycle."""
    state = CompanyState(
        mandate_id=mandate.id,
        status=MandateStatus.ACTIVE,
        summary="The synthetic candidates have not yet been compared.",
        facts=(
            "The candidate brief is synthetic and is not real demand evidence.",
        ),
        open_questions=(
            "Which candidate hypothesis should be validated?",
        ),
    )
    for prior_cycle in range(1, cycle):
        objective = store.load_objective(
            mandate.id, f"objective-{prior_cycle}"
        )
        decision = store.load_decision(
            mandate.id, f"decision-{prior_cycle}"
        )
        state = replace(state, active_objective_id=objective.id)
        result = _parse_cycle_execution(
            root / ".codex-output" / f"execution-{prior_cycle}.json",
            root,
            prior_cycle,
        )
        evidence, update = _execution_records(
            result, state, objective, decision, prior_cycle
        )
        state = apply_objective_result(
            state,
            replace(objective, status=ObjectiveStatus.SUCCEEDED),
            evidence,
            update,
        )
    return state


def _execution_records(execution, state, objective, decision, cycle):
    paths = tuple(execution["artifact_paths"])
    observations = tuple(execution["observations"])
    facts = tuple(execution["facts"])
    claims = observations + tuple(f"Worker-reported fact, not independently verified: {x}" for x in facts)
    source = f"codex-exec:{objective.id}; artifacts=" + ",".join(paths)
    evidence = tuple(Evidence(f"evidence-{cycle}-{i}", state.mandate_id, source, item,
                              objective_id=objective.id, decision_id=decision.id)
                     for i, item in enumerate(claims, 1))
    verified = f"Codex created {len(paths)} verified artifact file(s) for {objective.id}: {', '.join(paths)}."
    update = CompanyStateUpdate(
        summary=f"Objective {cycle} execution completed. Codex reported: {execution['summary']}",
        facts=_dedupe(state.facts + (verified,)),
        assumptions=_dedupe(state.assumptions + tuple(execution["assumptions"])),
        open_questions=_dedupe(tuple(execution["open_questions"])),
        relevant_evidence_ids=_dedupe(state.relevant_evidence_ids + tuple(x.id for x in evidence)),
    )
    return evidence, update


def _proposal_records(proposal, mandate, cycle):
    kind = ExecutiveDecisionType(proposal["decision_type"])
    raw_objective = proposal["objective"]
    raw_escalation = proposal["human_escalation"]
    objective = Objective(f"objective-{cycle}", mandate.id, raw_objective["outcome"], raw_objective["rationale"],
                          constraints=tuple(raw_objective["constraints"]), acceptance_criteria=tuple(raw_objective["acceptance_criteria"]),
                          expected_evidence=tuple(raw_objective["expected_evidence"])) if raw_objective else None
    escalation = HumanEscalation(f"escalation-{cycle}", mandate.id, raw_escalation["question"], raw_escalation["reason"],
                                 evidence_ids=tuple(raw_escalation["evidence_ids"]), options=tuple(raw_escalation["options"])) if raw_escalation else None
    decision = ExecutiveDecision(f"decision-{cycle}", mandate.id, kind, proposal["rationale"],
                                 objective_id=objective.id if objective else None,
                                 human_escalation_id=escalation.id if escalation else None,
                                 supporting_evidence_ids=tuple(proposal["supporting_evidence_ids"]))
    return decision, objective, escalation


def _load_checkpoint(path: Path) -> RunCheckpoint:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CodexDurableRunError("runner checkpoint contains malformed JSON") from exc
    if not isinstance(payload, dict) or set(payload) != _CHECKPOINT_KEYS:
        raise CodexDurableRunError("runner checkpoint must contain exact keys")
    if payload["schema_version"] != 1:
        raise CodexDurableRunError("unsupported runner checkpoint schema_version")
    if payload["mandate_id"] != MANDATE_ID:
        raise CodexDurableRunError("runner checkpoint mandate mismatch")
    if isinstance(payload["cycle_number"], bool) or not isinstance(payload["cycle_number"], int) or payload["cycle_number"] <= 0:
        raise CodexDurableRunError("runner checkpoint cycle_number must be positive")
    if payload["stage"] not in STAGES:
        raise CodexDurableRunError("runner checkpoint has unknown stage")
    hashes = payload["protected_file_hashes"]
    if hashes is not None and (not isinstance(hashes, dict) or any(not isinstance(k, str) or not isinstance(v, str) for k, v in hashes.items())):
        raise CodexDurableRunError("runner checkpoint protected_file_hashes is invalid")
    checkpoint = RunCheckpoint(**payload)
    _validate_captured_shapes(checkpoint)
    return checkpoint


def _validate_captured_shapes(checkpoint):
    proposal, execution, hashes = (checkpoint.captured_executive_proposal,
                                   checkpoint.captured_execution_result,
                                   checkpoint.protected_file_hashes)
    if checkpoint.stage == "proposal_captured":
        if proposal is None or execution is not None or hashes is not None:
            raise CodexDurableRunError("invalid proposal_captured checkpoint fields")
        _validate_proposal_payload(proposal)
        _validate_phase6_proposal(proposal, checkpoint.cycle_number)
    elif checkpoint.stage == "execution_captured":
        if execution is None or proposal is not None or hashes is not None:
            raise CodexDurableRunError("invalid execution_captured checkpoint fields")
        _validate_execution_payload(execution)
    elif checkpoint.stage == "objective_active":
        if proposal is not None or execution is not None:
            raise CodexDurableRunError("invalid objective_active checkpoint fields")
    elif proposal is not None or execution is not None or hashes is not None:
        raise CodexDurableRunError(f"invalid {checkpoint.stage} checkpoint fields")


def _validate_checkpoint(checkpoint, store, root, mandate):
    try:
        state = store.load_state(checkpoint.mandate_id)
    except (FileNotFoundError, ValueError) as exc:
        raise CodexDurableRunError("checkpoint references invalid company state") from exc
    if checkpoint.stage == "awaiting_executive" and not (state.status is MandateStatus.ACTIVE and state.active_objective_id is None):
        raise CodexDurableRunError("awaiting_executive requires active state without objective")
    if checkpoint.stage == "objective_active" and not (state.status is MandateStatus.ACTIVE and state.active_objective_id == f"objective-{checkpoint.cycle_number}"):
        raise CodexDurableRunError("objective_active checkpoint contradicts company state")
    if checkpoint.stage == "needs_human":
        if state.status is not MandateStatus.NEEDS_HUMAN or state.pending_human_escalation_id is None:
            raise CodexDurableRunError("needs_human checkpoint contradicts company state")
        store.load_escalation(checkpoint.mandate_id, state.pending_human_escalation_id)
    if checkpoint.stage == "terminal" and state.status not in (MandateStatus.SUCCEEDED, MandateStatus.STOPPED):
        raise CodexDurableRunError("terminal checkpoint contradicts company state")
    if checkpoint.stage == "proposal_captured":
        decision, objective, escalation = _proposal_records(
            checkpoint.captured_executive_proposal,
            mandate,
            checkpoint.cycle_number,
        )
        expected_pre_state = _reconstruct_pre_execution_state(
            root, store, mandate, checkpoint.cycle_number
        )
        expected_post_state = apply_executive_decision(
            expected_pre_state, decision, objective, escalation
        )
        if state not in (expected_pre_state, expected_post_state):
            raise CodexDurableRunError(
                "captured proposal contradicts company state"
            )
    if checkpoint.stage == "execution_captured":
        if not (state.active_objective_id == f"objective-{checkpoint.cycle_number}" or
                (state.status is MandateStatus.ACTIVE and state.active_objective_id is None)):
            raise CodexDurableRunError("execution_captured checkpoint contradicts company state")


def _save_checkpoint(path: Path, checkpoint: RunCheckpoint) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = _json_value(asdict(checkpoint))
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n"); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _snapshot_protected(root: Path, cycle: int, output: Path):
    allowed = root / "artifacts" / f"cycle-{cycle}"
    result = {}
    for path in _files(root):
        if path == output or _inside(path, allowed):
            continue
        result[path.relative_to(root).as_posix()] = _hash(path)
    return result


def _verify_protected(root: Path, cycle: int, output: Path, expected):
    checkpoint = _load_checkpoint(root / CHECKPOINT_NAME)
    if (checkpoint.stage != "objective_active"
            or checkpoint.cycle_number != cycle
            or checkpoint.protected_file_hashes != expected):
        raise CodexDurableRunError("bounded execution modified the runner checkpoint")
    allowed = root / "artifacts" / f"cycle-{cycle}"
    unexpected_links = [
        path.relative_to(root).as_posix() for path in root.rglob("*")
        if path.is_symlink() and not _inside(path, allowed)
    ]
    if unexpected_links:
        raise CodexDurableRunError(
            "bounded execution created protected symlink(s): "
            + ", ".join(sorted(unexpected_links))
        )
    current = _snapshot_protected(root, cycle, output)
    # The checkpoint's contents are validated above. Its hash necessarily changes
    # once the snapshot is embedded into that same checkpoint.
    checkpoint_key = CHECKPOINT_NAME
    current.pop(checkpoint_key, None); expected = dict(expected); expected.pop(checkpoint_key, None)
    if current != expected:
        changed = sorted(set(current) ^ set(expected) | {k for k in set(current) & set(expected) if current[k] != expected[k]})
        raise CodexDurableRunError("bounded execution modified protected files: " + ", ".join(changed))


def _files(root):
    return tuple(path for path in root.rglob("*") if path.is_file() and not path.is_symlink())


def _hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_cycle_execution(path: Path, root: Path, cycle: int):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StructuredOutputError("execution result contains malformed JSON") from exc
    _validate_execution_payload(payload)
    base = (root / "artifacts" / f"cycle-{cycle}").resolve()
    checked = []
    for raw in payload["artifact_paths"]:
        posix = PurePosixPath(raw)
        if posix.is_absolute() or ".." in posix.parts or posix.parts[:2] != ("artifacts", f"cycle-{cycle}"):
            raise StructuredOutputError(f"artifact path must be under artifacts/cycle-{cycle}/")
        target = root.joinpath(*posix.parts)
        if target.is_symlink() or not target.is_file() or not _inside(target.resolve(), base):
            raise StructuredOutputError(f"artifact path is not a regular cycle file: {raw}")
        checked.append(posix.as_posix())
    return {**payload, "observations": tuple(payload["observations"]), "artifact_paths": tuple(checked),
            "facts": tuple(payload["facts"]), "assumptions": tuple(payload["assumptions"]),
            "open_questions": tuple(payload["open_questions"])}


def _validate_execution_payload(value):
    keys = {"summary", "observations", "artifact_paths", "facts", "assumptions", "open_questions"}
    if not isinstance(value, dict) or set(value) != keys or not isinstance(value["summary"], str) or not value["summary"].strip():
        raise CodexDurableRunError("captured execution result is invalid")
    for key in keys - {"summary"}:
        if not isinstance(value[key], (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in value[key]):
            raise CodexDurableRunError("captured execution result is invalid")
    if not value["observations"] or not value["artifact_paths"]:
        raise CodexDurableRunError("captured execution result is invalid")


def _validate_proposal_payload(value):
    # Exercise the same strict parser without creating another schema implementation.
    fd, name = tempfile.mkstemp(suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        parse_executive_proposal(name)
    finally:
        Path(name).unlink(missing_ok=True)


def _validate_phase6_proposal(proposal, cycle):
    if (
        cycle < 3
        and proposal["decision_type"] == ExecutiveDecisionType.SUCCESS.value
    ):
        raise CodexDurableRunError(
            "the Phase 6 synthetic mandate cannot succeed before two "
            "objective executions"
        )


def _invoke(executable, prompt, workspace, schema, output, sandbox, command_function, role):
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [executable, "exec", "--ephemeral", "--sandbox", sandbox, "--cd", str(workspace),
               "--skip-git-repo-check", "--output-schema", str(schema), "--output-last-message", str(output), "-"]
    runner = command_function or _run_subprocess
    try:
        completed = runner(command, prompt)
    except (OSError, FileNotFoundError) as exc:
        raise CodexDurableRunError(f"Codex CLI could not be launched for {role}") from exc
    if completed.returncode != 0 or not output.is_file():
        raise CodexDurableRunError(f"Codex {role} invocation failed or produced no output")


def _run_subprocess(command, prompt):
    return subprocess.run(command, input=prompt, text=True, encoding="utf-8", errors="replace",
                          capture_output=True, check=False, shell=False)


def _resolve_codex(requested, command_function):
    if requested:
        return requested
    found = shutil.which("codex")
    if found:
        return found
    if command_function:
        return "codex"
    raise CodexDurableRunError("Codex CLI executable is unavailable")


def _executive_prompt(mandate, state, evidence, excerpts, cycle):
    if cycle == 1:
        cycle_instruction = (
            "This is executive cycle 1. You must choose CONTINUE and authorize only "
            "a bounded candidate-comparison and single-hypothesis-selection objective. "
            "Record explicit uncertainty. Do not combine or design the complete "
            "validation experiment in Objective 1. SUCCESS is prohibited because no "
            "objective has yet been executed."
        )
    elif cycle == 2:
        cycle_instruction = (
            "This is executive cycle 2. If the cycle-1 comparison completed "
            "successfully, choose CONTINUE with a distinct validation-plan objective "
            "that uses its selected hypothesis and evidence. A separate validation-plan "
            "objective must be executed before success. SUCCESS is prohibited because "
            "that objective has not yet executed. STOP or HUMAN_ESCALATION remain valid "
            "only for a real authority or safety boundary."
        )
    else:
        cycle_instruction = (
            "This is executive cycle 3 or later. Choose CONTINUE, SUCCESS, STOP, or "
            "HUMAN_ESCALATION according to the mandate, persisted state, and evidence."
        )
    return ("You are the constrained executive for Loop Engine. Select exactly one existing decision type: "
            "continue, success, stop, or human_escalation. Durable IDs are assigned by the runtime.\n\n"
            f"{cycle_instruction}\n\n"
            f"Cycle: {cycle}\nMandate: {_json_value(asdict(mandate))}\nCurrent state: {_json_value(asdict(state))}\n"
            f"Evidence: {[_json_value(asdict(x)) for x in evidence]}\nPrior artifact excerpts: {excerpts}\n\n"
            "Codex can perform one bounded workspace execution that writes only to the current cycle artifact directory. "
            "Respect mandate authority, success criteria, and stop conditions. Output only the required schema object.")


def _execution_prompt(mandate, objective, state, cycle):
    return (f"Execute only this bounded objective for cycle {cycle}.\nMandate: {_json_value(asdict(mandate))}\n"
            f"Objective: {_json_value(asdict(objective))}\nState: {_json_value(asdict(state))}\n"
            f"You may write only under artifacts/cycle-{cycle}/ and must report paths relative to the workspace. "
            "Do not select the next objective, declare mandate success, modify company state, the company store, prior outputs, or prior artifacts. "
            "The fixture is synthetic; do not perform outreach or claim real demand evidence. Output only the required schema object.")


def _artifact_excerpts(root):
    result, total = [], 0
    for path in sorted((root / "artifacts").glob("cycle-*/*")) if (root / "artifacts").exists() else ():
        if not path.is_file() or path.is_symlink():
            continue
        try:
            text = path.read_text(encoding="utf-8")[:_EXCERPT_LIMIT]
        except UnicodeDecodeError:
            continue
        remaining = _TOTAL_CONTEXT_LIMIT - total
        if remaining <= 0: break
        text = text[:remaining]; total += len(text)
        result.append((path.relative_to(root).as_posix(), text))
    return tuple(result)


def _inside(path: Path, directory: Path):
    try:
        path.relative_to(directory)
        return True
    except ValueError:
        return False


def _dedupe(values):
    return tuple(dict.fromkeys(values))


def _json_value(value):
    if isinstance(value, Enum): return value.value
    if isinstance(value, tuple): return [_json_value(x) for x in value]
    if isinstance(value, list): return [_json_value(x) for x in value]
    if isinstance(value, dict): return {k: _json_value(v) for k, v in value.items()}
    return value
