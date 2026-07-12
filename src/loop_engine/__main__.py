"""Command-line interface for one personal Loop Engine project."""

from __future__ import annotations

import argparse
import sys

from loop_engine.codex_durable_run import CodexDurableRunError
from loop_engine.personal_project import (
    PersonalProjectError,
    history_text,
    initialize_project,
    load_project,
    run_personal_project,
    status_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m loop_engine",
        description="Initialize, run, and inspect one personal Loop Engine project.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="initialize a personal project workspace")
    init.add_argument("--workspace", required=True, help="new or empty workspace directory")
    init.add_argument("--mandate", required=True, help="strict JSON mandate file")
    run = commands.add_parser("run", help="run bounded foreground cycles")
    run.add_argument("--workspace", required=True, help="initialized project workspace")
    run.add_argument("--max-cycles", required=True, type=_positive_integer,
                     help="maximum objective executions to commit")
    for name, help_text in (("status", "show current durable project state"),
                            ("history", "show executive decision history")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--workspace", required=True, help="initialized project workspace")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "init":
            mandate = initialize_project(args.workspace, args.mandate)
            print(f"Initialized personal project.\nMandate ID: {mandate.id}\nCheckpoint stage: awaiting_executive\nCurrent cycle: 1")
        elif args.command == "run":
            result = run_personal_project(args.workspace, max_cycles=args.max_cycles)
            _, store, mandate, _ = load_project(args.workspace)
            state = store.load_state(mandate.id)
            escalation = store.load_escalation(mandate.id, state.pending_human_escalation_id) if state.pending_human_escalation_id else None
            print("\n".join([
                f"Mandate ID: {result.mandate_id}", f"Starting stage: {result.starting_stage}",
                f"Starting cycle: {result.starting_cycle_number}",
                f"Newly executed objectives: {_items(result.executed_objective_ids)}",
                f"Newly committed evidence: {_items(result.evidence_ids_created)}",
                f"Final mandate status: {result.mandate_status.value}",
                f"Next active objective: {result.next_active_objective_id or '(none)'}",
                f"Pending escalation: {escalation.question if escalation else '(none)'}",
                f"Final checkpoint stage: {result.ending_stage}",
            ]))
        elif args.command == "status":
            print(status_text(args.workspace))
        else:
            print(history_text(args.workspace))
    except (PersonalProjectError, CodexDurableRunError, FileNotFoundError,
            FileExistsError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def _items(values):
    return ", ".join(values) if values else "(none)"


if __name__ == "__main__":
    raise SystemExit(main())
