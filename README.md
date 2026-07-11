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
- bounded execution-domain foundations;
- one concrete synthetic Phase 5 vertical slice using non-interactive Codex CLI calls; and
- a durable, resumable Phase 6 multi-cycle Codex runner.

Not implemented:

- a general-purpose model-backed executive or execution-routing layer;
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

## Phase 6 resumable multi-cycle runner

Phase 6 adds a separate synthetic mandate and a foreground, manually invoked runner. It persists a small atomic `codex-run-checkpoint.json`, uses cycle-specific structured outputs and artifact directories, and resumes completed Codex calls without repeating them. The synthetic mandate intentionally separates candidate selection from validation-plan design into at least two objective executions so the same-workspace resume path is observable. It is not a background service and does not claim autonomous business operation or real demand evidence.

Run the same workspace twice:

```text
python examples/resumable_multi_cycle.py --workspace ./phase6-demo-real --max-cycles 1
python examples/resumable_multi_cycle.py --workspace ./phase6-demo-real --max-cycles 1
```

`--max-cycles` limits objective executions committed by one Python invocation, not executive decisions. After reaching the limit, the runner asks the executive once more and durably authorizes the next objective, records a terminal decision, or records a human escalation before exiting. The first command should execute Objective 1 and leave Objective 2 active; the second should execute Objective 2 and leave Objective 3 active or the mandate terminal or paused.

The immutable Objective lifecycle limitation from Phase 5 remains: completion uses an in-memory terminal copy while the persisted Objective remains pending. Escalation resolution and all external-world execution remain out of scope; the demonstration is synthetic.

New Phase 6 workspaces physically separate durable Loop Engine state from the bounded writable workspace:

```text
<workspace>/
  company-store/
  codex-run-checkpoint.json
  candidate-brief.md
  .codex-output/
    executive-<cycle>.json
  execution-workspace/
    authorized-inputs/
      candidate-brief.md
    .codex-output/
      execution-<cycle>.json
    artifacts/
      cycle-<cycle>/
```

The read-only executive runs with `--cd <workspace>`. Bounded execution runs with `--cd <workspace>/execution-workspace --sandbox workspace-write`; `company-store/`, the checkpoint, the canonical candidate brief, and executive outputs are therefore outside its writable root. Initialization copies the canonical candidate brief byte-for-byte to `authorized-inputs/candidate-brief.md`; a differing existing authorized copy is rejected and never overwritten. Evidence records use persistent paths prefixed with `execution-workspace/`.

The physical workspace boundary is the primary protection. Hash comparisons remain defense in depth for authorized inputs, prior execution outputs and artifacts, unexpected files inside the execution workspace, and selected durable-root files. Any symlink under `execution-workspace/` is rejected. Existing Phase 6 workspaces with a checkpoint and legacy root-level execution outputs or artifacts are rejected with an incompatibility error; this version performs no automatic migration.
