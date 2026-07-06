# Loop Engine Roadmap

This roadmap favors the smallest end-to-end increment at each phase. Scope may be refined as implementation evidence emerges, but architecture changes should be explicit.

## Phase 0 — Repository bootstrap

Establish the project description, agent working conventions, initial architecture, and incremental roadmap while preserving the MIT license.

## Phase 1 — Core task and state models

Define and test the minimal representations for goals, tasks, dependencies, attempts, review and test results, transition decisions, and lifecycle states. Keep storage and agent integrations out of scope.

## Phase 2 — Local runtime loop

Run a deterministic in-process loop that selects one ready task, records an attempt, accepts stubbed evaluation results, and applies a transition decision. Demonstrate done, retry, and escalation paths without invoking an external coding agent.

## Phase 3 — Codex worker adapter

Invoke Codex for a single local task through a narrow adapter and normalize its outcome into an attempt result. Keep agent-specific details behind the adapter boundary.

## Phase 4 — Review and test gates

Add structured review output and execution of repository-defined test commands. Feed both results into the transition decision without allowing either gate to mutate workflow state directly.

## Phase 5 — Retry and human escalation

Support bounded retries with concrete feedback and a paused state that presents a clear escalation reason and accepts a recorded human decision.

## Phase 6 — Persistent execution history

Persist goals, tasks, attempts, gate results, and transition decisions so a local execution can be inspected and resumed after interruption.

## Phase 7 — Dogfood Loop Engine on a real repository

Use Loop Engine to complete one bounded change in a real repository. Record the full history, identify friction and missing safeguards, and use that evidence to choose the next development priorities.

Framework selection, additional worker adapters, and broader deployment concerns should follow demonstrated needs rather than precede the core loop.
