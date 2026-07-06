import pytest

from loop_engine.models import Task, TaskStatus
from loop_engine.task_graph import TaskGraph


def make_task(
    task_id: str,
    *,
    status: TaskStatus = TaskStatus.PENDING,
    dependencies: tuple[str, ...] = (),
) -> Task:
    return Task(
        task_id,
        "goal-1",
        f"Task {task_id}",
        f"Description for {task_id}",
        status,
        dependencies,
    )


def test_duplicate_task_ids_are_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate task id: task-1"):
        TaskGraph([make_task("task-1"), make_task("task-1")])


def test_missing_dependencies_are_rejected() -> None:
    task = make_task("task-1", dependencies=("missing-task",))

    with pytest.raises(ValueError, match="missing dependencies: missing-task"):
        TaskGraph([task])


def test_get_task_returns_requested_task() -> None:
    task = make_task("task-1")
    graph = TaskGraph([task])

    assert graph.get_task("task-1") is task


def test_ready_tasks_returns_tasks_with_no_dependencies() -> None:
    pending = make_task("pending")
    in_progress = make_task("in-progress", status=TaskStatus.IN_PROGRESS)
    graph = TaskGraph([pending, in_progress])

    assert graph.ready_tasks() == (pending,)


def test_ready_tasks_excludes_tasks_with_incomplete_dependencies() -> None:
    dependency = make_task("dependency")
    dependent = make_task("dependent", dependencies=(dependency.id,))
    graph = TaskGraph([dependency, dependent])

    assert graph.ready_tasks() == (dependency,)


def test_ready_tasks_returns_dependent_task_after_dependency_is_done() -> None:
    dependency = make_task("dependency", status=TaskStatus.DONE)
    dependent = make_task("dependent", dependencies=(dependency.id,))
    graph = TaskGraph([dependency, dependent])

    assert graph.ready_tasks() == (dependent,)


def test_ready_tasks_excludes_non_pending_tasks_when_dependencies_are_done() -> None:
    dependency = make_task("dependency", status=TaskStatus.DONE)
    in_progress = make_task(
        "in-progress",
        status=TaskStatus.IN_PROGRESS,
        dependencies=(dependency.id,),
    )
    graph = TaskGraph([dependency, in_progress])

    assert graph.ready_tasks() == ()
