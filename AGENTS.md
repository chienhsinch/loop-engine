# Agent Guidelines

## Project context

Loop Engine is a lightweight runtime for long-horizon, evidence-driven goal pursuit. An owner supplies a high-level mandate. An AI executive observes persistent company state, selects the next bounded objective, delegates execution to a suitable worker, collects evidence, updates state, and decides whether to continue, declare success, stop, or request human input.

The current architecture direction is documented in `docs/architecture-v0.2.md`. Objectives are generated dynamically from current state rather than fully planned as one task graph at mandate intake. The initial design has one executive loop and dynamically selected workers; it does not assume permanent agent roles, departments, or a fixed multi-agent organization.

The execution architecture documented in `docs/architecture-v0.1.md` remains a lower-level subsystem. A bounded objective may be decomposed into a task graph, scheduled to workers such as Codex or Claude Code, evaluated by review and test gates, and resolved by explicit transition rules. The executive level decides what objective should be pursued and whether the mandate should continue. The execution level decides how to complete and validate the currently bounded work. Do not collapse these two decision scopes.

The project is pre-alpha. Documentation may describe intended behavior that has not yet been implemented.

## Working conventions

- Inspect the existing repository, relevant code, and documentation before editing.
- Keep changes minimal and scoped to the requested task.
- Preserve established terminology and boundaries. Architectural changes, including changes to the executive/execution boundary, must be explicit; document and escalate proposed changes before implementing them.
- Do not add dependencies without a concrete need and explicit justification.
- Do not invent commands, interfaces, behavior, or project structure that do not exist.
- Avoid placeholder source directories and speculative abstractions.
- Keep executive-level decisions about mandate progress, objective selection, and company state separate from bounded execution work such as task planning, worker attempts, review, testing, and retry.
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
