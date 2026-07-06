"""Minimal task dependency graph."""

from collections.abc import Iterable

from loop_engine.models import Task, TaskStatus


class TaskGraph:
    def __init__(self, tasks: Iterable[Task]) -> None:
        self._tasks: dict[str, Task] = {}

        for task in tasks:
            if task.id in self._tasks:
                raise ValueError(f"duplicate task id: {task.id}")
            self._tasks[task.id] = task

        task_ids = set(self._tasks)
        for task in self._tasks.values():
            if task.id in task.dependencies:
                raise ValueError(f"task {task.id} must not depend on itself")
            missing = set(task.dependencies) - task_ids
            if missing:
                missing_ids = ", ".join(sorted(missing))
                raise ValueError(
                    f"task {task.id} has missing dependencies: {missing_ids}"
                )

    def get_task(self, task_id: str) -> Task:
        return self._tasks[task_id]

    def ready_tasks(self) -> tuple[Task, ...]:
        return tuple(
            task
            for task in self._tasks.values()
            if task.status is TaskStatus.PENDING
            and all(
                self._tasks[dependency_id].status is TaskStatus.DONE
                for dependency_id in task.dependencies
            )
        )
