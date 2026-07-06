# Loop Engine

Loop Engine is a lightweight runtime for coordinating existing AI coding agents through a persistent, inspectable delivery loop. It addresses the gap between asking an agent to make a change and reliably carrying that change through planning, execution, review, testing, retry, and human intervention.

The intended workflow is:

```text
User Goal
  -> Planner
  -> Task Graph
  -> Scheduler
  -> Worker
  -> Reviewer
  -> Test Gate
  -> Transition Decision
  -> Done / Retry / Human Escalation
```

Loop Engine will orchestrate coding agents such as Codex and Claude Code; it is not intended to implement a new coding agent. The project aims to provide a small, local-first execution model, explicit state transitions, persistent execution history, and clear points for human oversight.

## Status

Loop Engine is pre-alpha and under active development. The repository currently contains the initial core domain models; runtime orchestration has not been implemented.

Installation and usage instructions will be added when an executable implementation exists. Until then, no installation process is implied or supported.

See [the initial architecture](docs/architecture-v0.1.md) and [the roadmap](docs/roadmap.md) for the current direction.
