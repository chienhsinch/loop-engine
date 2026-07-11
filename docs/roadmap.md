# Loop Engine Roadmap

This roadmap takes Loop Engine from its completed foundations to a real multi-cycle demonstration of the thin executive harness described in `architecture-v0.3.md`. Each phase should deliver the smallest inspectable increment and use concrete execution evidence to justify later abstractions.

## Completed foundations

### Phase 0 - Execution core

Implemented the bounded execution-domain foundations: `Task`, `TaskGraph`, `Attempt`, `ReviewResult`, `TestResult`, and `TransitionDecision`. This remains an optional lower-level subsystem rather than the required execution path for every objective.

### Phase 1 - Company-level models

Implemented owner mandates, durable company state, bounded objectives, executive decisions, evidence, state updates, and human escalations as records separate from the execution domain.

### Phase 2 - Deterministic transitions

Implemented validation and deterministic in-process transitions for authorizing one objective, applying its evidence and state update, continuing across objective cycles, declaring success, stopping, and requesting human input.

### Phase 3 - Durable local persistence

Implemented local JSON persistence for mandates, the current company-state snapshot, objectives, executive decisions, evidence, and human escalations, including reference validation and resumable state.

### Phase 4 - Thin executive architecture

Completed the v0.3 boundary: Loop Engine owns the durable mandate, decision-relevant workspace, decision history, evidence references, authority boundaries, human escalation, and the outer loop. Bounded execution is delegated to capable existing agents and tools. `TaskGraph` remains optional, and broader frameworks remain deferred until a real use case provides evidence for them.

## Current phase

### Phase 5 - End-to-end executive vertical slice

Implemented the shortest concrete path through two evidence-linked executive cycles using non-interactive Codex CLI calls and checked-in JSON Schemas. The synthetic vertical slice now demonstrates, in order:

1. one durable owner mandate is loaded;
2. a real model-backed executive reads the current state;
3. objective 1 is selected from that state;
4. one concrete execution capability performs the bounded objective;
5. the resulting evidence is persisted in the durable workspace;
6. the executive reads the updated state and new evidence; and
7. a materially different objective 2 is selected because of what was learned.

The implementation uses canned subprocess outputs in normal tests and never calls the real Codex service during pytest. A real smoke run remains environment-dependent on an accessible, already authenticated Codex CLI. The slice intentionally does not introduce a generic worker protocol or route the objective through `TaskGraph`.

## Next phases

### Phase 6 - Durable multi-cycle run

Turn the vertical slice into a resumable runner that can cross process interruptions and repeat the executive -> objective -> execution -> evidence -> state-update cycle. Preserve authority checks, deterministic transition validation, and focused human escalation while keeping integrations concrete and minimal.

### Phase 7 - Real product-validation mandate

Use Loop Engine on one real product-validation mandate. Record the mandate, model-backed decisions, delegated work, evidence and artifact references, state changes, and owner interventions across multiple dynamically selected objectives. Use the run history to determine whether the harness improves continuity and decision quality and to identify the next missing safeguard.

Only evidence from the Phase 5 vertical slice and subsequent real runs should justify considering:

- more worker types;
- richer budget controls;
- integration of the optional `TaskGraph` subsystem;
- sophisticated escalation resolution; or
- parallelism.

Generic workflow DAGs, worker frameworks, agent-to-agent conversation protocols, plugin systems, and simulated organization structures are not roadmap goals without concrete evidence that the thin harness needs them.
