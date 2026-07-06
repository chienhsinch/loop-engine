# Loop Engine Architecture v0.1

## Purpose and scope

Loop Engine coordinates existing AI coding agents through a small, persistent execution loop. Version 0.1 defines responsibilities and boundaries for a local runtime; it does not prescribe a framework or implementation language.

The top-level flow is:

```text
User Goal
  -> Goal Intake
  -> Planner
  -> Task Graph
  -> Scheduler
  -> Worker Adapter
  -> Reviewer
  -> Test Gate
  -> Transition Engine
  -> Done / Retry / Human Escalation

Persistent State records the workflow throughout.
```

## Components

### Goal Intake

- **Responsibility:** Capture a user's requested outcome and the constraints needed to plan it.
- **Receives:** A user goal, repository context, and explicit constraints.
- **Produces:** A normalized goal record suitable for planning, or a request for clarification.
- **Does not own:** Task decomposition, execution, or decisions about whether an attempt passed.

### Planner

- **Responsibility:** Decompose a normalized goal into the smallest useful set of tasks and dependencies.
- **Receives:** A normalized goal and relevant repository context.
- **Produces:** A task graph with task descriptions, dependencies, and completion criteria.
- **Does not own:** Task execution, scheduling policy, review outcomes, or retry decisions.

### Task Graph

- **Responsibility:** Represent tasks, dependencies, and task lifecycle status for one goal.
- **Receives:** Planned tasks and dependency relationships from the Planner, plus status updates from the runtime.
- **Produces:** A queryable view of ready, blocked, active, and terminal tasks.
- **Does not own:** Planning logic, worker invocation, evaluation, or transition policy.

### Scheduler

- **Responsibility:** Select the next eligible task and initiate an attempt through a worker adapter.
- **Receives:** The current task graph, execution state, and configured runtime limits.
- **Produces:** A task assignment and attempt record, or an indication that no task is currently runnable.
- **Does not own:** Task content, agent internals, review judgments, or final transition decisions.

### Worker Adapter

- **Responsibility:** Translate a task assignment into an invocation of an existing coding agent and normalize the result.
- **Receives:** A task assignment, repository context, constraints, and agent-specific configuration.
- **Produces:** An attempt result containing the agent's outcome, reported changes, and execution metadata.
- **Does not own:** The coding agent's reasoning, task scheduling, acceptance criteria, review policy, or retry policy.

### Reviewer

- **Responsibility:** Evaluate an attempt against the task description, completion criteria, constraints, and resulting changes.
- **Receives:** The task, attempt result, and relevant repository state or diff.
- **Produces:** A structured review result with a pass/fail outcome and actionable findings.
- **Does not own:** Running the worker, executing tests, mutating the task graph, or choosing the next transition.

### Test Gate

- **Responsibility:** Run the relevant available checks and report whether the attempt satisfies the test requirements.
- **Receives:** The task, repository state, and the test commands or checks defined by the repository or task.
- **Produces:** A structured test result containing commands run, outcomes, and useful failure details.
- **Does not own:** Inventing missing tests, reviewing product intent, fixing failures, or selecting retry behavior.

### Transition Engine

- **Responsibility:** Apply explicit transition rules to determine the next state after an attempt is evaluated.
- **Receives:** The task and attempt state, review result, test result, retry limits, and escalation conditions.
- **Produces:** One decision: mark the task done, schedule a retry with feedback, or request human escalation.
- **Does not own:** Performing work, producing review or test evidence, or changing policy during an execution.

### Persistent State

- **Responsibility:** Durably record goals, task graphs, attempts, results, decisions, and execution history.
- **Receives:** State changes and appendable events from runtime components.
- **Produces:** Recoverable current state and an inspectable history for resuming and auditing executions.
- **Does not own:** Workflow policy, scheduling, agent execution, evaluation, or transition decisions.

### Human Escalation

- **Responsibility:** Pause automated progress and present a specific decision, ambiguity, or blocker to a person.
- **Receives:** The relevant goal, task, attempt history, evidence, and reason automation cannot safely continue.
- **Produces:** A recorded human decision, clarification, or instruction that can resume or terminate the workflow.
- **Does not own:** Silently choosing an answer, rewriting architecture, or bypassing review and test requirements.

## Core execution loop

The smallest execution unit is an attempt on one task:

```text
Task
  -> Attempt
  -> Review Result + Test Result
  -> Transition Decision
     -> Done
     -> Retry
     -> Human Escalation
```

1. The Scheduler selects a ready task and creates an attempt.
2. A Worker Adapter invokes a configured coding agent for that attempt.
3. The Reviewer and Test Gate independently produce evidence about the result.
4. The Transition Engine applies the configured rules to that evidence.
5. A successful task becomes done. A recoverable failure creates a retry with concrete feedback. Ambiguity, exhausted retries, or a decision outside the runtime's authority triggers human escalation.
6. Persistent State records each step so interrupted work can be inspected and resumed.

Version 0.1 should keep records and state transitions explicit. Given the same task state, evaluation results, and transition policy, the Transition Engine should produce the same decision. Distributed execution, web interfaces, cloud infrastructure, complex plugin systems, and autonomous self-modification are outside this architecture.
