# Loop Engine Architecture v0.2

## Purpose and scope

Loop Engine is a lightweight runtime for pursuing long-horizon goals through an explicit, persistent, evidence-driven loop. An owner provides a high-level mandate and retains authority over its constraints. An AI executive turns that mandate into a sequence of bounded objectives, delegates each objective to suitable workers, evaluates evidence, and repeatedly decides what should happen next.

Version 0.2 adds a company-level control loop above the execution architecture described in `architecture-v0.1.md`. It defines responsibilities and boundaries, not implemented Python interfaces. The initial design uses one executive loop plus dynamically selected workers. Permanent department agents, speculative organization charts, and autonomous changes to the mandate are outside its scope.

The top-level flow is:

```text
Owner Mandate
  -> Company State
  -> Executive Decision
  -> Bounded Objective
  -> Delegated Execution
  -> Evidence
  -> State Update
  -> Continue / Success / Stop / Human Escalation
```

## Owner and mandate

The owner is the person or group that authorizes the goal pursuit. The owner provides a **mandate**: a durable statement of the desired outcome, boundaries, authority, and conditions under which the work should stop or return for human judgment.

A mandate should be high-level enough to survive multiple execution cycles. It is not a task description and is not replaced by the executive's current plan. The executive may choose objectives within the mandate, but it may not silently broaden the mandate, relax owner constraints, or claim authority the owner did not grant.

The owner does not need to prescribe every intermediate step. The runtime should make progress independently while evidence supports a safe next action, and should escalate when a consequential choice is ambiguous or outside the mandate.

## Executive loop

The executive loop is the top-level decision process:

1. Load the owner mandate and current company state.
2. Observe material changes, prior objective outcomes, available resources, constraints, risks, and unresolved questions.
3. Produce one executive decision supported by the current evidence.
4. If continuing, define one bounded objective with explicit completion criteria and delegate it to a selected worker or the lower-level task runtime.
5. Collect normalized evidence from execution and any relevant observations.
6. Update company state with the objective outcome, evidence, decisions, resource use, and newly learned facts.
7. Re-enter the loop and choose whether to continue with a new objective, declare mandate success, stop, or escalate to the owner.

The loop does not fully decompose a mandate into one static task graph at startup. Long-horizon work changes the information available to the system: an experiment may invalidate an assumption, execution may expose a blocker, or evidence may make a planned step unnecessary. The executive therefore chooses the next bounded objective from updated state after each meaningful outcome. It may record provisional future options, but those options are not committed objectives.

Only one executive decision controls the mandate at a time in the initial design. Workers can vary by objective, but they do not independently redefine company priorities.

## Core concepts

### Company State

**Company State** is the persistent, decision-relevant record used by the executive loop. “Company” names the goal-pursuing unit represented by the runtime; it does not require a legal company or simulated organization.

Company state should contain, at minimum:

- the owner mandate and its constraints;
- current status of the mandate;
- material facts, assumptions, and open questions;
- objectives and their outcomes;
- accumulated evidence and provenance;
- executive decisions and their rationale;
- relevant resource and budget usage; and
- pending human escalations or recorded owner responses.

Company state is not an unrestricted transcript or a replacement for artifact storage. It should retain the information required to resume, inspect, and justify the next decision. Updates must be explicit and attributable to evidence or a recorded decision.

### Objective

An **Objective** is the bounded outcome selected for one cycle of delegated execution. It translates the mandate and current state into work that can be completed and evaluated without giving the worker authority over the full mandate.

An objective should state:

- the intended outcome;
- why it is the appropriate next step;
- scope and constraints;
- completion or acceptance criteria;
- expected evidence; and
- an execution budget or other stopping boundary when applicable.

An objective is not necessarily one task. Simple objectives may go directly to one worker. More involved objectives may be decomposed into a `TaskGraph` and completed by the existing execution subsystem. An objective ends with evidence and an outcome; it does not decide the mandate's next objective.

### Executive Decision

An **Executive Decision** is the executive loop's recorded choice based on the current mandate, company state, and evidence. It contains a decision type, rationale, and references to the state and evidence that support it.

The decision types are:

- **Continue:** select and authorize the next bounded objective.
- **Success:** conclude that the mandate's success conditions have been met.
- **Stop:** end pursuit because continuing is unjustified, prohibited, infeasible, or no longer worth the expected cost.
- **Human Escalation:** pause for an owner decision that the runtime lacks the authority or confidence to make.

Executive decisions concern mandate-level direction. They are distinct from lower-level `TransitionDecision` records, which decide whether a task is done, should retry, or needs human attention during execution.

An executive decision may be proposed through a model-backed adapter, but the runtime remains responsible for validating the proposal and applying the state transition. A Codex-backed executive adapter is therefore a separate, constrained use of the provider from a Codex coding-worker session; it does not give a worker ownership of the mandate.

### Evidence

**Evidence** is a durable, attributable observation used to evaluate an objective, update company state, or support an executive decision. It may include worker outputs, created artifacts, review findings, test results, experiment measurements, external observations, resource usage, or a recorded human instruction.

Evidence should identify its source, the objective or decision it relates to, and enough context to inspect its meaning. Worker claims are inputs, not automatically accepted facts. Review and test outputs from the execution subsystem are evidence that the executive can use, but the evidence needed for a company-level decision may extend beyond code correctness.

Contradictory or inconclusive evidence should remain visible in company state rather than being silently resolved. The executive must account for uncertainty in its next decision or escalate when safe progress depends on resolving it.

### Human Escalation

**Human Escalation** pauses autonomous progress and asks the owner for a specific decision, clarification, approval, or change in authority. It is appropriate when:

- the mandate or constraints are materially ambiguous;
- available choices involve a consequential tradeoff not authorized by the mandate;
- evidence is insufficient or contradictory and further autonomous work is not justified;
- a budget, risk, or execution boundary has been reached; or
- execution cannot proceed safely after bounded recovery attempts.

An escalation should include the decision required, relevant evidence, attempted actions, viable options, and the consequence of waiting or stopping. The owner's response becomes part of company state before the loop resumes.

Task-level escalation from the execution subsystem does not always require an immediate owner decision. The executive may select a different bounded recovery objective if that remains within its authority. It must escalate to the owner when resolving the issue requires mandate-level judgment or new authority.

## Lower-level execution subsystem

The v0.1 task runtime remains the mechanism for carrying out bounded objectives that require structured execution:

```text
Bounded Objective
  -> Planner
  -> Task Graph
  -> Scheduler
  -> Worker Adapter
  -> Attempt
  -> Review Result + Test Result
  -> Transition Decision
     -> Done
     -> Retry
     -> Human Escalation
  -> Objective Evidence
```

The existing `Task`, `TaskGraph`, `Attempt`, `ReviewResult`, `TestResult`, and `TransitionDecision` concepts retain their v0.1 responsibilities. Coding agents such as Codex and Claude Code are worker implementations behind this boundary. They perform bounded work and report results; they are not the executive and do not own the mandate.

This separation keeps both loops small:

- the executive loop chooses **what outcome to pursue next and why**;
- the execution subsystem determines **how bounded work is attempted, checked, retried, or blocked**; and
- normalized execution results return upward as evidence rather than directly mutating mandate-level direction.

Version 0.2 does not redesign the current Python execution models. Company-level domain models and orchestration should be added incrementally around that core.

## Persistence and determinism

The runtime must persist enough company state, evidence, objective history, and executive decisions to resume after interruption and explain why an action was taken. Execution history from v0.1 remains part of that audit trail.

State updates and control-flow transitions should be deterministic where policy can make them so, including budget enforcement, terminal-state handling, and escalation boundaries. AI-produced executive decisions are not assumed to be deterministic. They should instead be constrained to a structured decision boundary, validated before state mutation, and recorded with their inputs and rationale.

## Initial implementation boundary

The smallest useful v0.2 implementation should support one mandate, one active executive loop, one bounded objective at a time, dynamically selected workers, explicit evidence ingestion, persistent state, and terminal or escalation decisions. Parallel portfolios, permanent agent hierarchies, autonomous mandate rewriting, broad plugin systems, and distributed infrastructure should follow demonstrated needs rather than precede the core loop.

## Open architecture questions

Implementation should resolve these questions with the smallest design supported by evidence:

- how an `Objective` links to the existing execution-domain `Goal` when the task runtime is used;
- which company-state fields are authoritative snapshots, derived views, or append-only history;
- what validation policy is sufficient before worker output or external observations become accepted evidence; and
- which budget dimensions and owner approvals are required for the first product-validation mandate.
