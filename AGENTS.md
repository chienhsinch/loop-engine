# Agent Guidelines

## Project context

Loop Engine is a lightweight runtime for orchestrating existing AI coding agents, such as Codex and Claude Code, through persistent planning, execution, review, testing, retry, and human-escalation loops. It coordinates agents; it does not implement a new coding agent.

The current architecture direction is documented in `docs/architecture-v0.1.md`. At a high level, a user goal is planned into a task graph, scheduled to a worker adapter, evaluated by review and test gates, and resolved by a transition engine. Execution state and history are persistent, and ambiguous or blocked work can be escalated to a human.

The project is pre-alpha. Documentation may describe intended behavior that has not yet been implemented.

## Working conventions

- Inspect the existing repository, relevant code, and documentation before editing.
- Keep changes minimal and scoped to the requested task.
- Preserve established terminology and boundaries. Do not silently change the architecture; document and escalate proposed changes first.
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
