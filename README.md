# Loop Engine

Loop Engine is a thin executive harness for long-horizon, evidence-driven goal pursuit. It gives powerful existing agents a durable owner mandate, persistent decision-relevant state, evidence and artifact references, authority and escalation boundaries, and an outer feedback loop.

The executive model reads the current durable workspace and dynamically chooses the next bounded objective. Loop Engine then delegates that objective to an existing execution capability, such as Codex, research or browser tools, an external coding-agent orchestrator, or a future specialized tool. The resulting evidence and artifact references return to the workspace before the executive chooses what happens next.

```text
Owner Mandate
  -> Durable Workspace
  -> Executive Agent
  -> Next Bounded Objective
  -> External Execution Capability
  -> Evidence and Artifacts
  -> Durable Workspace Update
  -> Executive Agent
  -> repeat
```

Loop Engine owns mandate continuity, decision-relevant state, decision history, evidence references, authority boundaries, human escalation, and outer-loop orchestration. It does not reimplement the internal planning, coding-task decomposition, retry loops, or test loops of capable agents, and it is not a generic workflow engine or a simulated multi-agent company.

The existing `TaskGraph` runtime remains available as an optional lower-level execution subsystem. A bounded objective may use it when explicit tasks, attempts, review and test gates, and retries provide concrete value. It is not a mandatory path for every objective.

## Status

Loop Engine is pre-alpha and under active development.

Already implemented:

- company domain models;
- deterministic executive transitions;
- durable local JSON persistence;
- bounded execution-domain foundations; and
- one concrete synthetic Phase 5 vertical slice using non-interactive Codex CLI calls.

Not implemented:

- a general-purpose model-backed executive or execution-routing layer;
- a resumable multi-cycle runner; or
- a real-world dogfood run.

The Phase 5 slice is a controlled demonstration, not general autonomous operation. It uses the existing records, transitions, and local store directly; it does not introduce a worker framework or use `TaskGraph`.

## Phase 5 synthetic vertical slice

The runnable example uses three non-interactive `codex exec` calls:

1. a read-only executive selects Objective 1 from the initial durable state;
2. a workspace-write Codex execution inspects the synthetic fixture and creates analysis artifacts; and
3. a read-only executive receives the persisted evidence and artifact contents and selects a materially different Objective 2.

The run stops after Objective 2 is persisted. It does not execute Objective 2 or claim that the synthetic fixture demonstrates market demand.

Requirements are Python 3.12 and an installed, already authenticated Codex CLI. `codex login status` checks authentication without starting a login flow. The example never reads or copies Codex credential files.

Run the real demonstration once with a fresh workspace:

```text
python examples/executive_vertical_slice.py --workspace ./phase5-demo
```

The workspace contains `company-store/` for durable Loop Engine records and a separate `execution-workspace/` containing the copied fixture, structured Codex outputs, and generated `artifacts/`. Codex receives write access only to `execution-workspace/`; the company store remains outside that writable root.

Known limitation: Objective 1 is persisted as its original immutable pending record. The vertical slice constructs a terminal-status copy in memory for `apply_objective_result()` and does not persist that lifecycle change. This preserves the existing `Objective` design and intentionally does not add a separate objective-result record.

See [architecture v0.3](docs/architecture-v0.3.md) for the current direction, [architecture v0.2](docs/architecture-v0.2.md) and [architecture v0.1](docs/architecture-v0.1.md) for project history, and [the roadmap](docs/roadmap.md) for the planned implementation sequence.
