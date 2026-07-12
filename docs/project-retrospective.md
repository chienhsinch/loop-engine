# Loop Engine Project Retrospective

## Original thesis

Loop Engine began from the thesis that powerful execution agents still benefit from a thin outer harness that preserves a durable owner mandate, decision-relevant state, evidence, authority boundaries, and continuity across bounded objectives. The harness would decide what outcome to pursue next while delegating the internal planning, attempts, testing, and retries of bounded work to an existing execution capability.

The intended differentiator was not another task planner or simulated organization. It was reliable mandate-level continuity: observe durable state, select one bounded objective, authorize isolated execution, validate the result, commit evidence and state atomically, and decide whether to continue, stop, succeed, or request human input.

## Architecture developed

The project developed two deliberately separate layers. The executive layer owns the mandate, current company state, executive decisions, evidence references, authority boundaries, escalation records, and outer-loop orchestration. The execution layer owns bounded work and may use either an external capability such as Codex or the optional lower-level `TaskGraph` runtime.

The durable company store and orchestration checkpoint remain physically outside the bounded writable execution workspace. Model proposals and execution results cross that boundary only through deterministic validation. The Phase 6 runner adds atomic checkpoints, deterministic cycle identifiers, cycle-isolated outputs and artifacts, protected-file snapshots, durable replay guards, and exact reconciliation after interruption.

The final architecture is documented in [architecture v0.3](architecture-v0.3.md). [Architecture v0.2](architecture-v0.2.md) and [architecture v0.1](architecture-v0.1.md) remain historical records of earlier execution-level designs.

## Validated milestones

Phases 0 through 4 established the bounded execution models, company-level records, deterministic transitions, durable local JSON persistence, and the thin executive/executor boundary.

Phase 5 validated a synthetic end-to-end vertical slice using non-interactive Codex CLI calls. A model-backed executive selected an objective, bounded execution produced artifacts, evidence was persisted, and a subsequent executive cycle selected a materially different objective from the updated state. Automated tests used controlled subprocess outputs, and a real Windows smoke run completed.

Phase 6 is the final validated milestone. It demonstrated resumable multi-cycle Codex CLI execution with bounded writable isolation, evidence and artifact persistence, atomic checkpoints, deterministic cycle identities, exact crash-recovery reconciliation, and idempotent replay. Phase 6 passed automated validation and a real two-invocation Windows Codex smoke run. It remained a synthetic foreground demonstration and did not establish production readiness.

## Experimental work not merged

The `feat/personal-project-workspace` branch implemented a generic personal-project workspace. Its offline tests passed, but native-Windows real execution remained blocked by permission behavior on artifacts created inside the Codex sandbox. The experimental pull request was closed, the branch was intentionally not merged, and the work remains implementation history rather than part of the stable milestone.

This result is best understood as a technically informative boundary discovered during validation. The workspace design could satisfy its logical isolation and persistence invariants while still failing at the host/sandbox filesystem ownership boundary. The personal-project CLI therefore did not pass real execution validation, but the experiment produced a concrete systems lesson rather than a claim of production failure.

## Why development stopped

First-party goal-oriented agent products increasingly cover much of the general orchestration surface that motivated Loop Engine. That reduced the value of continuing a standalone general orchestration platform. General orchestration is becoming commoditized; recreating broad planning, routing, and goal-pursuit capabilities would offer less differentiation than applying the validated lessons to a bounded domain.

The project therefore concluded after Phase 6. Generic personal-project operation, owner evidence ingestion, escalation resolution, execution routing, background operation, real-world dogfooding, and production packaging were not completed.

## Technical lessons

- Durable state should remain physically outside bounded writable execution. Logical conventions and prompts are not substitutes for an operating-system-enforced boundary.
- Structured model output alone is insufficient. Filesystem effects, artifact presence and contents, path confinement, and schema conformance must also be validated before durable state changes.
- Crash recovery requires deterministic reconstruction and exact acceptance of only the expected pre-commit or post-commit state. Broadly accepting a plausible intermediate state weakens recovery guarantees.
- Idempotent replay requires durable guards before external execution. A guard written only after a call cannot prevent the call from being repeated after interruption.
- Host and sandbox filesystem ownership can invalidate otherwise-correct architecture, especially on native Windows. Access-control behavior must be tested in the real execution environment.
- General orchestration is becoming commoditized by first-party agent products.
- The strongest future differentiation is domain-specific evidence, evaluation, workflows, and policy rather than recreating general planning.

## Reusable components

The repository retains useful prototype components and patterns: durable mandate and company-state records; deterministic executive transitions; local JSON persistence with reference validation; physical separation of durable and writable roots; bounded authorized-input copying; schema, path, artifact, and filesystem validation; atomic checkpoint replacement; deterministic cycle identifiers; protected-file snapshots; exact recovery reconciliation; and durable replay guards.

These components are research-prototype assets, not a production framework. Reuse should preserve the executive/execution boundary and select only the mechanisms justified by a concrete end-to-end case.

## Future reuse

The architecture and lessons may be reused in poker analysis, research automation, or another bounded domain. The most promising direction is to combine durable state and evidence discipline with domain-specific sources, evaluations, workflows, and policy constraints.

Future reuse should begin with one real vertical slice and its failure modes. It should avoid rebuilding a generic agent platform unless concrete domain evidence shows that first-party execution capabilities cannot supply the required outer-loop behavior.
