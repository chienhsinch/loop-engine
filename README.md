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
- durable local JSON persistence; and
- bounded execution-domain foundations.

Not implemented:

- a real model-backed executive;
- real execution delegation;
- an end-to-end multi-cycle runner; or
- a real-world dogfood run.

Installation and usage instructions will be added when an executable end-to-end implementation exists. Until then, no installation process is implied or supported.

See [architecture v0.3](docs/architecture-v0.3.md) for the current direction, [architecture v0.2](docs/architecture-v0.2.md) and [architecture v0.1](docs/architecture-v0.1.md) for project history, and [the roadmap](docs/roadmap.md) for the planned implementation sequence.
