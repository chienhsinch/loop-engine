# Loop Engine

Loop Engine is a lightweight runtime for long-horizon, evidence-driven goal pursuit. An owner provides a high-level mandate; an AI executive repeatedly observes persistent company state, chooses the next bounded objective, delegates execution, evaluates the resulting evidence, and decides whether to continue, declare success, stop, or escalate to the owner.

The intended workflow is:

```text
Owner Mandate
  -> Company State
  -> Executive Decision
  -> Bounded Objective
  -> Delegated Execution
  -> Evidence
  -> State Update
  -> Continue / Success / Stop / Human Escalation
```

Objectives are selected dynamically as state and evidence change, rather than decomposing the entire mandate into one static task graph at the beginning. Coding agents such as Codex and Claude Code are workers that can execute bounded objectives; they are not the top-level intelligence responsible for pursuing the mandate.

The existing task runtime remains part of the design as a lower-level execution subsystem. It can plan a bounded objective into tasks, schedule attempts, apply review and test gates, retry work, and escalate execution blockers. Above it, the executive loop owns objective selection, interpretation of company-level evidence, and the decision to continue or end pursuit of the mandate.

## Status

Loop Engine is pre-alpha and under active development. The current implementation contains the initial company-level domain models and the lower-level execution-domain models for goals, tasks, task graphs, attempts, review and test results, and transition decisions. The executive loop, persistence, and agent integrations described by the new architecture have not yet been implemented.

Installation and usage instructions will be added when an executable implementation exists. Until then, no installation process is implied or supported.

See [architecture v0.2](docs/architecture-v0.2.md) for the current direction, [architecture v0.1](docs/architecture-v0.1.md) for the historical execution-focused design, and [the roadmap](docs/roadmap.md) for the planned implementation sequence.
