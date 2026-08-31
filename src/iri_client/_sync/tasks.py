"""Task abstraction.

Every IRI filesystem operation is *asynchronous*: the API accepts the request,
returns a ``TaskSubmitResponse`` immediately, and the caller polls
``GET /api/v1/task/{task_id}`` until the task reaches a terminal state and its
result is available.

This module models that with an awaitable ``Task`` object, mirroring the
``CommandTask`` pattern from ``sfapi_client``. Filesystem helpers submit a
task and wait on it; callers who want the raw task (e.g. to inspect
intermediate state or to cancel it) can use the ``submit_*`` helpers on the
filesystem object.
"""

from __future__ import annotations

import math
import sys
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..exceptions import IriError
from .._models import Task as TaskResponse
from .._models import TaskStatus
from .._utils import _SLEEP

# IRI task lifecycle: pending -> active -> completed | failed | canceled
# (not to be confused with the Job lifecycle, which is modelled in jobs.py).
TERMINAL_TASK_STATES: List[TaskStatus] = [
    TaskStatus.completed,
    TaskStatus.failed,
    TaskStatus.canceled,
]


class Task(BaseModel):
    """
    Models an asynchronous IRI task, the result of a filesystem operation.
    """

    id: str
    status: Optional[TaskStatus] = None
    result: Optional[Dict[str, Any]] = None

    _client: Any = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, id: Optional[str] = None, client: Any = None, **kwargs):
        super().__init__(id=id, **kwargs)
        self._client = client

    def _fetch(self) -> TaskResponse:
        r = self._client.get(f"task/{self.id}")
        data = r.json()
        return TaskResponse.model_validate(data)

    @property
    def output(self) -> Any:
        """
        The ``output`` member of the task result, if present.

        Task results are dicts whose keys vary by command (``ls`` produces
        ``output`` holding a list of entries, ``stat`` a stat object, ``view``
        file text, ...). Commands that have no payload still return a
        confirmation object.
        """
        if self.result is None:
            return None
        return self.result.get("output")

    def update(self) -> "Task":
        """
        Refresh the task state from the API.

        The IRI backend reports some failures (e.g. a missing path or bad
        command argument) as a *completed* task whose result carries an
        ``error`` member; those are normalized to ``IriError`` here so callers
        observe a single, consistent failure mode.

        :return: The updated task.
        """
        task = self._fetch()
        self.status = task.status
        if task.status in TERMINAL_TASK_STATES:
            self.result = task.result
            if isinstance(task.result, dict) and task.result.get("error"):
                raise IriError(
                    f"task {self.id} failed: {task.result.get('error')}"
                )
        return self

    def _wait(self, timeout: int = sys.maxsize) -> "Task":
        max_iteration = math.ceil(timeout / self._client._wait_interval)
        iteration = 0

        while self.status not in TERMINAL_TASK_STATES:
            self.update()
            if self.status in TERMINAL_TASK_STATES:
                break
            _SLEEP(self._client._wait_interval)

            if iteration == max_iteration:
                raise TimeoutError(
                    f"task {self.id} did not reach a terminal state within "
                    f"{timeout}s"
                )
            iteration += 1

        if self.status == TaskStatus.failed:
            raise IriError(
                f"task {self.id} failed: {self.result}"
            )
        if self.status == TaskStatus.canceled:
            raise IriError(f"task {self.id} was cancelled")

        return self

    def wait(self, timeout: Optional[int] = None) -> "Task":
        """
        Block until the task reaches a terminal state.

        :param timeout: Seconds to wait before raising ``TimeoutError``
        :return: The completed task
        :rtype: Task
        """
        return self._wait(timeout=timeout or sys.maxsize)

    def __await__(self):
        """Allow ``task`` to block until the task completes."""
        return self.wait().__await__()

    def cancel(self) -> None:
        """
        Cancel the running task.
        """
        self._client.delete(f"task/{self.id}")