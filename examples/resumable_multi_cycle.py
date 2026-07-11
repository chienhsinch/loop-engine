"""Run the concrete resumable Phase 6 Codex demonstration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from loop_engine.codex_durable_run import (  # noqa: E402
    CodexDurableRunError,
    run_durable_cycles,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run or resume the synthetic Phase 6 foreground Codex runner."
    )
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--max-cycles", required=True, type=int)
    parser.add_argument("--codex", help="Optional Codex CLI executable.")
    args = parser.parse_args()
    try:
        result = run_durable_cycles(
            args.workspace, max_cycles=args.max_cycles,
            codex_executable=args.codex,
        )
    except (CodexDurableRunError, ValueError) as exc:
        print(f"Phase 6 run failed: {exc}", file=sys.stderr)
        return 1

    print(f"Mandate: {result.mandate_id}")
    print(f"Starting durable stage: {result.starting_stage}")
    print(f"Starting cycle: {result.starting_cycle_number}")
    for objective in result.executed_objective_ids:
        print(f"Objective executed: {objective}")
    print("Evidence committed: " + (", ".join(result.evidence_ids_created) or "none"))
    print(f"Final CompanyState status: {result.mandate_status.value}")
    if result.next_active_objective_id:
        print(f"Next active objective: {result.next_active_objective_id}")
    elif result.pending_escalation_id:
        print(f"Pending escalation: {result.pending_escalation_id}")
    elif result.is_terminal:
        print("The mandate is terminal.")
    print(f"Final checkpoint stage: {result.ending_stage}")
    print("Rerun the same command to resume this workspace.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
