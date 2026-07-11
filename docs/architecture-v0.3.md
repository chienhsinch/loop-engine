# Loop Engine Architecture v0.3

## Purpose and positioning

Loop Engine is a thin executive harness above powerful existing agents and tools. Its purpose is to sustain long-horizon, evidence-driven goal pursuit across bounded execution cycles without rebuilding the capabilities that already know how to research, browse, write code, plan implementation work, run tests, or recover from local failures.

An owner supplies a durable mandate: the desired outcome, constraints, authority, success criteria, and stop conditions. An executive agent reads that mandate together with the current decision-relevant workspace, chooses the next bounded objective, and delegates execution. Evidence and artifact references return to the workspace before the executive decides what should happen next.

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

This is an outer feedback loop, not an attempt to own every step inside execution. The executive chooses the next outcome from current state and evidence after each meaningful cycle. It does not fully decompose the mandate into a static plan at intake.

Version 0.3 narrows the direction described in `architecture-v0.2.md`; it does not replace or delete the implemented domain foundations. Versions 0.1 and 0.2 remain project history.

## Durable workspace

The durable workspace is the executive agent's persistent decision context. It combines the owner mandate and current `CompanyState` with durable records and references needed to resume and justify the next decision. It should keep:

- the mandate and its authority, success, and stop boundaries;
- the current decision-relevant state;
- bounded objectives and executive decision history;
- evidence with provenance;
- references to artifacts produced or inspected by external capabilities; and
- pending human escalations and recorded owner input.

The workspace is not an unrestricted transcript and need not copy every external artifact into Loop Engine storage. Large outputs may remain in their native repository, document store, or tool environment as long as the evidence record contains a durable, inspectable reference and enough context for the executive to interpret it.

The current implementation provides immutable company-domain records, a replaceable `CompanyState` snapshot, deterministic transition validation, local JSON persistence, and one concrete resumable Codex runner. Dedicated artifact-reference domain fields are not implemented; the runner retains cycle-specific relative paths in evidence provenance.

For the concrete resumable Codex runner, bounded execution receives workspace-write access only to a dedicated `execution-workspace/`. The company store, orchestration checkpoint, canonical inputs, and executive outputs remain in the durable root outside that writable boundary. Protected-file hashing and symlink checks remain defense in depth; this separation is not a claim of container-level isolation or a general sandbox architecture.

## Executive cycle

One executive cycle is:

1. Load the mandate, current `CompanyState`, relevant prior decisions, evidence, artifact references, and unresolved escalations.
2. Ask a constrained executive model to choose one action: continue with a bounded objective, declare success, stop, or request human input.
3. Validate the proposed `ExecutiveDecision` against the mandate, known evidence, current state, and authority boundaries before changing state.
4. If continuing, authorize one `Objective` with a bounded outcome, rationale, constraints, acceptance criteria, and expected evidence.
5. Select a concrete external execution capability suited to that objective and delegate the bounded work.
6. Persist attributable evidence and artifact references from execution, then apply an explicit durable workspace update.
7. Return control to the executive agent, which reads the changed workspace and chooses the next action.

The executive model is responsible for deciding **what outcome should be pursued next and why**. The selected execution capability is responsible for deciding **how to perform the bounded work within the authority it received**. Worker output cannot silently change the mandate or select the next mandate-level objective.

## Ownership boundary

Loop Engine owns:

- the durable owner mandate;
- the current decision-relevant state;
- executive decision and objective history;
- durable evidence and artifact references;
- authority and stopping boundaries;
- human escalation;
- validation of outer-loop state transitions; and
- orchestration of the outer feedback loop.

Loop Engine does not own:

- Codex internal planning or other execution-capability internals;
- coding-task decomposition unless a specific bounded objective demonstrably needs it;
- coding-agent retries, review mechanics, and test loops;
- permanent AI departments, personas, or agent hierarchies;
- generic workflow DAGs;
- arbitrary agent-to-agent conversation protocols;
- a generic worker framework or plugin system; or
- the storage and lifecycle of every external artifact.

Thinness is a product boundary, not merely an implementation preference. New orchestration abstractions require evidence from a concrete end-to-end use case that the outer loop cannot remain reliable without them.

## External execution capabilities

Execution should use strong capabilities that already exist. Depending on the objective, that may be a Codex coding session, research or browser tools, an external coding-agent orchestrator, or a future specialized tool. Loop Engine supplies the bounded objective, relevant context, constraints, evidence expectations, and stopping boundary. The capability performs the work using its own internal planning and control mechanisms.

The initial vertical slice should integrate one concrete capability directly. A generic worker protocol, registry, lifecycle model, or conversation bus is intentionally deferred until multiple real integrations demonstrate a stable shared need.

Execution results are inputs to the executive workspace, not automatically accepted truth. Evidence must identify its source and related objective, retain useful provenance, and distinguish worker claims from facts accepted into `CompanyState`. Contradictory or incomplete evidence remains visible or triggers focused human escalation when progress would exceed the executive's authority.

## Optional `TaskGraph` execution subsystem

The existing v0.1 task runtime is preserved without redesign. It provides bounded execution-domain foundations for objectives that genuinely benefit from explicit `Task` dependencies, `Attempt` records, review and test gates, `TransitionDecision` records, and retries.

```text
Bounded Objective
  -> optional TaskGraph execution subsystem
     -> Tasks and Attempts
     -> Review and Test Gates
     -> Done / Retry / Human Escalation
  -> Evidence and Artifact References
  -> Executive Workspace
```

`TaskGraph` is not mandatory for every objective. A capable external agent may receive a simple bounded objective directly and use its own planning, testing, and recovery loop. Loop Engine should select the optional subsystem only when explicit task-level state and deterministic gates add value that the external capability does not already provide.

When used, the execution subsystem remains below the executive boundary. Its task-level transition decides whether bounded work is done, retried, or blocked; it does not decide whether the mandate has succeeded, should stop, or which objective comes next.

## Authority, validation, and escalation

The owner retains authority over the mandate. The executive may select objectives only within its constraints and may not silently broaden the desired outcome, relax a stop condition, or claim new authority. Model proposals and external execution results pass through deterministic validation before they change the durable state where existing invariants can decide the outcome.

Human escalation is an outer-loop control for a specific decision, clarification, approval, or authority change. It is appropriate when consequential ambiguity, risk, contradictory evidence, a boundary, or an exhausted resource prevents safe progress. An escalation should contain the question, reason, relevant evidence, viable options, and the related objective when applicable. The durable workspace records the owner's response before autonomous progress resumes.

A task-level blocker from the optional execution subsystem does not automatically become a mandate-level escalation. The executive may choose another recovery objective if the mandate already grants that authority. It must ask the owner when resolution requires mandate-level judgment.

## Implementation status and next proof

The repository already implements:

- company-domain models for mandates, `CompanyState`, `Objective`, `ExecutiveDecision`, `Evidence`, state updates, and human escalation;
- deterministic validation for executive decisions and terminal objective results;
- durable local JSON persistence for company records;
- the separate bounded execution-domain models and minimal `TaskGraph` runtime; and
- one concrete synthetic vertical slice using Codex CLI as both the constrained executive model and the bounded execution capability.

The vertical slice runs two executive cycles around one bounded execution, persists the first cycle's evidence, provides referenced artifact contents to the second executive call, and stops after a materially different Objective 2 is selected. It is a demonstration integration, not a general model provider, worker framework, resumable runner, or claim of autonomous operation.

The existing immutable Objective persistence has a known lifecycle limitation in this slice. Objective 1 remains persisted in its original pending form; a terminal-status copy is constructed only in memory for the existing objective-result transition. Version 0.3 preserves that limitation rather than adding a new domain record or redesigning `Objective`.

The resumable multi-cycle runner is implemented as a foreground, manually invoked Codex integration with a small atomic orchestration checkpoint. The next architectural proof is one real product-validation mandate. Additional worker types, richer budgets, `TaskGraph` integration, escalation resolution, background operation, and parallel execution still require evidence from concrete runs.

## Intentionally deferred abstractions

Until the vertical slice produces evidence of need, version 0.3 intentionally defers:

- generic worker protocols, registries, and lifecycle records;
- permanent worker roles, departments, personas, and agent hierarchies;
- generic workflow or conversation frameworks;
- plugin systems;
- broad budget and policy frameworks;
- parallel objective execution; and
- speculative changes to `Objective` or additional objective-result records.

The architecture should evolve from observed failures and constraints in real multi-cycle use, with the shortest reliable path to that evidence taking priority over framework completeness.
