# Loop Engine Roadmap

This roadmap moves Loop Engine from its existing bounded task runtime toward the executive architecture in `architecture-v0.2.md`. Each phase should deliver the smallest inspectable increment, preserve explicit state transitions, and use implementation evidence to refine later phases. Architecture changes must remain explicit.

## Phase 0 — Preserve the existing execution core

Retain and test the current `Task`, `TaskGraph`, `Attempt`, `ReviewResult`, `TestResult`, and `TransitionDecision` models as the lower-level subsystem for bounded objectives. Clarify its boundary without redesigning it or treating the v0.1 architecture as discarded.

## Phase 1 — Company-level domain models

Define minimal representations for owner mandates, company state, bounded objectives, executive decisions, evidence, and human escalations. Keep these records separate from task-level models and avoid adding agent integrations or speculative organization structures.

## Phase 2 — Deterministic executive loop with stubs

Implement an in-process loop that loads a mandate and company state, accepts a stubbed structured executive decision, authorizes at most one bounded objective, records evidence, applies a state update, and reaches continue, success, stop, and human-escalation paths. Validate decisions and state transitions before adding model-driven judgment.

## Phase 3 — Codex-backed executive decision adapter

Add a narrow adapter that asks Codex to propose a structured executive decision from the mandate and current company state. Validate the proposal against allowed decision types, authority, budgets, and state invariants before committing it. Keep Codex-specific behavior behind the adapter boundary.

## Phase 4 — Delegated worker execution

Connect an authorized bounded objective to a dynamically selected worker. Route objectives that need structured planning, attempts, review, tests, or retry through the existing execution subsystem, then normalize their outcomes into objective-level evidence. Workers must not select the next company objective or change the mandate.

## Phase 5 — Persistent company state

Persist mandates, company state updates, objectives, evidence, executive decisions, and links to lower-level execution history. Support inspection and resumption after interruption while preserving the provenance of decision-relevant facts.

## Phase 6 — Budget controls and human escalation

Enforce explicit limits on objective attempts, time, cost, and other configured resources. Pause with a focused escalation when authority, risk, ambiguity, or exhausted budgets prevent safe progress, and record the owner's response before resuming.

## Phase 7 — Dogfood one product-validation mandate

Use Loop Engine to pursue one real-world product-validation goal across multiple dynamically chosen objectives. Record the complete mandate, decisions, delegated work, evidence, state changes, resource use, and owner interventions. Use that history to identify missing safeguards and select the next development priorities.

Parallel portfolios, permanent department agents, additional executive adapters, and distributed deployment should follow demonstrated needs rather than precede a reliable single-executive loop.
