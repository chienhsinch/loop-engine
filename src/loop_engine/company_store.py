"""Local persistence for company-level records."""

import json
import os
import tempfile
from dataclasses import asdict
from enum import Enum
from pathlib import Path
from typing import Protocol, Union
from urllib.parse import quote

from loop_engine.company_models import (
    CompanyState,
    Evidence,
    ExecutiveDecision,
    ExecutiveDecisionType,
    HumanEscalation,
    Mandate,
    MandateStatus,
    Objective,
    ObjectiveStatus,
)


class CompanyStore(Protocol):
    """Minimal persistence operations required by the company runtime."""

    def save_mandate(self, mandate: Mandate) -> None: ...

    def load_mandate(self, mandate_id: str) -> Mandate: ...

    def save_state(self, state: CompanyState) -> None: ...

    def load_state(self, mandate_id: str) -> CompanyState: ...

    def save_objective(self, objective: Objective) -> None: ...

    def load_objective(self, mandate_id: str, objective_id: str) -> Objective: ...

    def save_decision(self, decision: ExecutiveDecision) -> None: ...

    def load_decision(
        self, mandate_id: str, decision_id: str
    ) -> ExecutiveDecision: ...

    def save_evidence(self, evidence: Evidence) -> None: ...

    def load_evidence(self, mandate_id: str, evidence_id: str) -> Evidence: ...

    def save_escalation(self, escalation: HumanEscalation) -> None: ...

    def load_escalation(
        self, mandate_id: str, escalation_id: str
    ) -> HumanEscalation: ...


class FileCompanyStore:
    """JSON-backed company store rooted in one local directory."""

    def __init__(self, root: Union[str, Path]) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def save_mandate(self, mandate: Mandate) -> None:
        self._save_immutable(
            self._mandate_dir(mandate.id) / "mandate.json",
            _serialize(mandate),
            "mandate",
            mandate.id,
        )

    def load_mandate(self, mandate_id: str) -> Mandate:
        payload = self._read_json(
            self._mandate_dir(mandate_id) / "mandate.json",
            "mandate",
            mandate_id,
        )
        mandate = _load_mandate(payload)
        if mandate.id != mandate_id:
            raise ValueError("stored mandate ID does not match the requested ID")
        return mandate

    def save_state(self, state: CompanyState) -> None:
        self._validate_state_references(state)
        self._atomic_write_json(
            self._mandate_dir(state.mandate_id) / "state.json",
            _serialize(state),
        )

    def load_state(self, mandate_id: str) -> CompanyState:
        payload = self._read_json(
            self._mandate_dir(mandate_id) / "state.json",
            "company state",
            mandate_id,
        )
        state = _load_state(payload)
        if state.mandate_id != mandate_id:
            raise ValueError("stored company state belongs to a different mandate")
        self._validate_state_references(state)
        return state

    def save_objective(self, objective: Objective) -> None:
        self.load_mandate(objective.mandate_id)
        self._save_immutable(
            self._record_path(
                objective.mandate_id, "objectives", objective.id
            ),
            _serialize(objective),
            "objective",
            objective.id,
        )

    def load_objective(self, mandate_id: str, objective_id: str) -> Objective:
        self.load_mandate(mandate_id)
        payload = self._read_json(
            self._record_path(mandate_id, "objectives", objective_id),
            "objective",
            objective_id,
        )
        return _load_child_record(
            _load_objective(payload),
            mandate_id,
            objective_id,
            "objective",
        )

    def save_decision(self, decision: ExecutiveDecision) -> None:
        self.load_mandate(decision.mandate_id)
        self._save_immutable(
            self._record_path(
                decision.mandate_id, "decisions", decision.id
            ),
            _serialize(decision),
            "executive decision",
            decision.id,
        )

    def load_decision(
        self, mandate_id: str, decision_id: str
    ) -> ExecutiveDecision:
        self.load_mandate(mandate_id)
        payload = self._read_json(
            self._record_path(mandate_id, "decisions", decision_id),
            "executive decision",
            decision_id,
        )
        return _load_child_record(
            _load_decision(payload),
            mandate_id,
            decision_id,
            "executive decision",
        )

    def save_evidence(self, evidence: Evidence) -> None:
        self.load_mandate(evidence.mandate_id)
        self._save_immutable(
            self._record_path(
                evidence.mandate_id, "evidence", evidence.id
            ),
            _serialize(evidence),
            "evidence",
            evidence.id,
        )

    def load_evidence(self, mandate_id: str, evidence_id: str) -> Evidence:
        self.load_mandate(mandate_id)
        payload = self._read_json(
            self._record_path(mandate_id, "evidence", evidence_id),
            "evidence",
            evidence_id,
        )
        return _load_child_record(
            _load_evidence(payload),
            mandate_id,
            evidence_id,
            "evidence",
        )

    def save_escalation(self, escalation: HumanEscalation) -> None:
        self.load_mandate(escalation.mandate_id)
        self._save_immutable(
            self._record_path(
                escalation.mandate_id, "escalations", escalation.id
            ),
            _serialize(escalation),
            "human escalation",
            escalation.id,
        )

    def load_escalation(
        self, mandate_id: str, escalation_id: str
    ) -> HumanEscalation:
        self.load_mandate(mandate_id)
        payload = self._read_json(
            self._record_path(mandate_id, "escalations", escalation_id),
            "human escalation",
            escalation_id,
        )
        return _load_child_record(
            _load_escalation(payload),
            mandate_id,
            escalation_id,
            "human escalation",
        )

    def _validate_state_references(self, state: CompanyState) -> None:
        self.load_mandate(state.mandate_id)

        if state.active_objective_id is not None:
            try:
                objective = self.load_objective(
                    state.mandate_id, state.active_objective_id
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    "company state references missing active objective: "
                    f"{state.active_objective_id}"
                ) from exc
            if objective.mandate_id != state.mandate_id:
                raise ValueError(
                    "company state active objective belongs to a different mandate"
                )

        for evidence_id in state.relevant_evidence_ids:
            try:
                evidence = self.load_evidence(state.mandate_id, evidence_id)
            except FileNotFoundError as exc:
                raise ValueError(
                    f"company state references missing evidence: {evidence_id}"
                ) from exc
            if evidence.mandate_id != state.mandate_id:
                raise ValueError(
                    "company state evidence belongs to a different mandate"
                )

        if state.pending_human_escalation_id is not None:
            try:
                escalation = self.load_escalation(
                    state.mandate_id, state.pending_human_escalation_id
                )
            except FileNotFoundError as exc:
                raise ValueError(
                    "company state references missing human escalation: "
                    f"{state.pending_human_escalation_id}"
                ) from exc
            if escalation.mandate_id != state.mandate_id:
                raise ValueError(
                    "company state human escalation belongs to a different mandate"
                )

    def _save_immutable(
        self,
        path: Path,
        payload: dict[str, object],
        record_type: str,
        record_id: str,
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = self._read_json(path, record_type, record_id)
            if existing == payload:
                return
            raise FileExistsError(
                f"{record_type} {record_id} already exists with different content"
            )

        temporary_path = self._write_temporary_json(path, payload)
        try:
            try:
                os.link(temporary_path, path)
            except FileExistsError:
                existing = self._read_json(path, record_type, record_id)
                if existing != payload:
                    raise FileExistsError(
                        f"{record_type} {record_id} already exists "
                        "with different content"
                    )
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _atomic_write_json(
        self, path: Path, payload: dict[str, object]
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self._write_temporary_json(path, payload)
        try:
            os.replace(temporary_path, path)
        finally:
            if temporary_path.exists():
                temporary_path.unlink()

    def _write_temporary_json(
        self, path: Path, payload: dict[str, object]
    ) -> Path:
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as file:
                _write_json(file, payload)
        except Exception:
            if temporary_path.exists():
                temporary_path.unlink()
            raise
        return temporary_path

    def _read_json(
        self, path: Path, record_type: str, record_id: str
    ) -> dict[str, object]:
        if not path.is_file():
            raise FileNotFoundError(f"{record_type} {record_id} does not exist")
        try:
            with path.open(encoding="utf-8") as file:
                payload = json.load(file)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError(
                f"{record_type} {record_id} contains malformed JSON"
            ) from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{record_type} {record_id} must contain a JSON object")
        return payload

    def _mandate_dir(self, mandate_id: str) -> Path:
        return self._root / "mandates" / _encode_id(mandate_id)

    def _record_path(
        self, mandate_id: str, collection: str, record_id: str
    ) -> Path:
        return (
            self._mandate_dir(mandate_id)
            / collection
            / f"{_encode_id(record_id)}.json"
        )


def _serialize(record: object) -> dict[str, object]:
    return _json_value(asdict(record))


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _load_mandate(payload: dict[str, object]) -> Mandate:
    return _construct_record(
        "mandate",
        lambda: Mandate(
            id=payload["id"],
            description=payload["description"],
            constraints=_load_tuple(payload, "constraints"),
            success_criteria=_load_tuple(payload, "success_criteria"),
            stop_conditions=_load_tuple(payload, "stop_conditions"),
        ),
    )


def _load_state(payload: dict[str, object]) -> CompanyState:
    return _construct_record(
        "company state",
        lambda: CompanyState(
            mandate_id=payload["mandate_id"],
            status=MandateStatus(payload["status"]),
            summary=payload["summary"],
            active_objective_id=payload["active_objective_id"],
            facts=_load_tuple(payload, "facts"),
            assumptions=_load_tuple(payload, "assumptions"),
            open_questions=_load_tuple(payload, "open_questions"),
            relevant_evidence_ids=_load_tuple(
                payload, "relevant_evidence_ids"
            ),
            pending_human_escalation_id=payload[
                "pending_human_escalation_id"
            ],
        ),
    )


def _load_objective(payload: dict[str, object]) -> Objective:
    return _construct_record(
        "objective",
        lambda: Objective(
            id=payload["id"],
            mandate_id=payload["mandate_id"],
            outcome=payload["outcome"],
            rationale=payload["rationale"],
            status=ObjectiveStatus(payload["status"]),
            constraints=_load_tuple(payload, "constraints"),
            acceptance_criteria=_load_tuple(payload, "acceptance_criteria"),
            expected_evidence=_load_tuple(payload, "expected_evidence"),
        ),
    )


def _load_decision(payload: dict[str, object]) -> ExecutiveDecision:
    return _construct_record(
        "executive decision",
        lambda: ExecutiveDecision(
            id=payload["id"],
            mandate_id=payload["mandate_id"],
            decision_type=ExecutiveDecisionType(payload["decision_type"]),
            rationale=payload["rationale"],
            objective_id=payload["objective_id"],
            human_escalation_id=payload["human_escalation_id"],
            supporting_evidence_ids=_load_tuple(
                payload, "supporting_evidence_ids"
            ),
        ),
    )


def _load_evidence(payload: dict[str, object]) -> Evidence:
    return _construct_record(
        "evidence",
        lambda: Evidence(
            id=payload["id"],
            mandate_id=payload["mandate_id"],
            source=payload["source"],
            observation=payload["observation"],
            objective_id=payload["objective_id"],
            decision_id=payload["decision_id"],
        ),
    )


def _load_escalation(payload: dict[str, object]) -> HumanEscalation:
    return _construct_record(
        "human escalation",
        lambda: HumanEscalation(
            id=payload["id"],
            mandate_id=payload["mandate_id"],
            question=payload["question"],
            reason=payload["reason"],
            objective_id=payload["objective_id"],
            evidence_ids=_load_tuple(payload, "evidence_ids"),
            options=_load_tuple(payload, "options"),
        ),
    )


def _construct_record(record_type: str, factory):
    try:
        return factory()
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid {record_type} record: {exc}") from exc


def _load_tuple(payload: dict[str, object], field_name: str) -> tuple[str, ...]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a JSON array")
    return tuple(value)


def _load_child_record(
    record, mandate_id: str, record_id: str, record_type: str
):
    if record.mandate_id != mandate_id:
        raise ValueError(f"stored {record_type} belongs to a different mandate")
    if record.id != record_id:
        raise ValueError(
            f"stored {record_type} ID does not match the requested ID"
        )
    return record


def _write_json(file, payload: dict[str, object]) -> None:
    json.dump(payload, file, indent=2, sort_keys=True, allow_nan=False)
    file.write("\n")
    file.flush()
    os.fsync(file.fileno())


def _encode_id(record_id: str) -> str:
    encoded = quote(record_id, safe="-_")
    if encoded in (".", ".."):
        return encoded.replace(".", "%2E")
    return encoded
