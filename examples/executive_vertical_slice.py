"""Run the concrete Loop Engine Phase 5 Codex CLI demonstration."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from loop_engine.codex_vertical_slice import (  # noqa: E402
    CodexVerticalSliceError,
    run_vertical_slice,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run the synthetic two-cycle Loop Engine Codex vertical slice."
        )
    )
    parser.add_argument(
        "--workspace",
        required=True,
        type=Path,
        help="Fresh directory for durable state and synthetic artifacts.",
    )
    parser.add_argument(
        "--codex",
        help="Optional Codex CLI executable name or absolute path.",
    )
    args = parser.parse_args()

    try:
        result = run_vertical_slice(
            args.workspace, codex_executable=args.codex
        )
    except CodexVerticalSliceError as exc:
        print(f"Phase 5 demo failed: {exc}", file=sys.stderr)
        return 1

    print(f"Mandate: {result.mandate.id}")
    print(f"Objective 1: {result.objective_1.outcome}")
    print("Artifacts: " + ", ".join(result.artifact_paths))
    print("Evidence: " + ", ".join(result.evidence_ids))
    print(
        "State after Objective 1: "
        + result.state_after_objective_1.summary
    )
    print(f"Objective 2: {result.objective_2.outcome}")
    print("Why Objective 2 follows: " + result.objective_2_rationale)
    print("Objective 2 was persisted but not executed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
