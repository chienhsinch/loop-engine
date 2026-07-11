# Agent Guidelines

## Project context

Loop Engine is a thin executive harness for long-horizon, evidence-driven goal pursuit. An owner supplies a durable mandate. An executive agent observes persistent decision-relevant state and evidence, selects the next bounded objective, delegates it to a powerful existing execution capability, updates the durable workspace from the result, and decides whether to continue, declare success, stop, or request human input.

The current architecture direction is documented in `docs/architecture-v0.3.md`. Loop Engine owns the mandate, current state, decision history, evidence references, authority boundaries, human escalation, and outer-loop orchestration. It does not own the internal planning or retry loops of Codex and other execution capabilities, generic workflow DAGs, or a simulated organization of permanent agent roles.

The execution architectures documented in `docs/architecture-v0.1.md` and `docs/architecture-v0.2.md` remain project history and describe a lower-level subsystem that is still preserved. A bounded objective may use the existing `TaskGraph` runtime when explicit tasks, attempts, review and test gates, and retries provide concrete value. This path is optional, not mandatory for every objective. The executive level decides what outcome to pursue and whether the mandate should continue; the execution level decides how to complete and validate currently bounded work. Do not collapse these decision scopes.

The project is pre-alpha. Documentation may describe intended behavior that has not yet been implemented.

## Working conventions

- Inspect the existing repository, relevant code, and documentation before editing.
- Keep changes minimal and scoped to the requested task.
- Preserve established terminology and boundaries. Architectural changes, including changes to the executive/execution boundary, must be explicit; document and escalate proposed changes before implementing them.
- Delegate bounded work to existing agent capabilities instead of reimplementing their internal planning, decomposition, retry, or test loops.
- Require evidence from a concrete end-to-end use case before adding abstractions.
- Avoid speculative lifecycle records, generic worker frameworks, simulated organization structures, and permanent agent personas or departments.
- Optimize for the shortest path to a real multi-cycle vertical slice.
- Preserve the executive/execution boundary: mandate progress and objective selection belong to the executive harness; bounded planning, attempts, review, testing, and retry belong to the selected execution capability or optional task runtime.
- Do not add dependencies without a concrete need and explicit justification.
- Do not invent commands, interfaces, behavior, or project structure that do not exist.
- Avoid placeholder source directories and speculative abstractions.
- Preserve the MIT license.
- Prefer precise engineering language and simple designs appropriate to the current phase.
- Escalate ambiguous product or architecture decisions rather than guessing.

## Validation and completion

Run all relevant tests and checks that exist for the area changed before declaring work complete. If no applicable tests or commands exist, state that explicitly; do not invent them.

Every completion report must include:

- files changed;
- tests or checks run, including when none exist;
- unresolved issues or open questions;
- architectural decisions introduced, or an explicit statement that none were introduced.
