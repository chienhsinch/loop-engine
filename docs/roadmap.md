# Loop Engine Roadmap

Loop Engine concluded as a research prototype after Phase 6, its final validated milestone. This roadmap records completed work, experimental work retained outside the stable main branch, and work that was not pursued. It does not describe active future commitments.

## Completed

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

### Phase 5 - End-to-end executive vertical slice

Implemented the shortest concrete path through two evidence-linked executive cycles using non-interactive Codex CLI calls and checked-in JSON Schemas. The synthetic vertical slice now demonstrates, in order:

1. one durable owner mandate is loaded;
2. a real model-backed executive reads the current state;
3. objective 1 is selected from that state;
4. one concrete execution capability performs the bounded objective;
5. the resulting evidence is persisted in the durable workspace;
6. the executive reads the updated state and new evidence; and
7. a materially different objective 2 is selected because of what was learned.

The implementation uses canned subprocess outputs in normal orchestration tests and never calls the real Codex service during pytest. A real Phase 5 smoke run completed successfully on Windows; subprocess output is decoded explicitly as UTF-8 so the run does not depend on `PYTHONUTF8`. The slice intentionally does not introduce a generic worker protocol or route the objective through `TaskGraph`.

### Phase 6 - Durable multi-cycle run

Implemented and validated a concrete foreground Codex runner that crosses process interruptions and repeats the executive -> objective -> execution -> evidence -> state-update cycle. It uses an atomic local checkpoint, deterministic cycle IDs, protected-file snapshots, cycle-isolated artifacts, exact crash-recovery reconciliation, and idempotent replay guarded by durable state before external execution. `--max-cycles` counts committed objective executions and stabilizes the workspace by persisting the next executive outcome before exit. Automated validation and a real two-invocation Windows Codex smoke run passed. The demonstration remains synthetic, retains the immutable Objective lifecycle limitation, and does not resolve escalations.

## Experimental but unmerged

### Personal-project workspace prototype

The `feat/personal-project-workspace` branch implemented a generic personal-project workspace and passed its offline tests. The branch was intentionally not merged, and its closed experimental pull request remains implementation history. It must not be treated as part of the stable Phase 6 milestone or as having passed real execution validation.

### Native-Windows artifact ACL investigation

Native-Windows real execution of the personal-project prototype remained blocked by permission behavior on artifacts created inside the Codex sandbox. This was a technically informative host/sandbox filesystem ownership boundary discovered during validation, not a production failure. It showed that an otherwise-correct isolation and persistence architecture can still be invalidated by operating-system ownership and access-control behavior.

## Not pursued

The project concluded without implementing or validating:

- owner evidence ingestion;
- escalation resolution;
- generic execution routing;
- background operation;
- real-world dogfooding; and
- production packaging.

These items are closure boundaries, not active roadmap commitments.
