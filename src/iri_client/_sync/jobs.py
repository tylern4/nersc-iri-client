"""Job abstraction.

The Superfacility API exposes different job views upstream of the scheduler
(squeue) and in the accounting database (sacct), modelled as the two job types
``JobSqueue`` and ``JobSacct``.  IRI collapses the distinction: a job
has a single ``Job`` document with one ``status`` whose ``meta_data`` carries
the backend (scheduler or accounting) details.  This is modelled as a
single awaitable ``Job``.
"""

from __future__ import annotations

import math
import sys
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, PrivateAttr

from ..exceptions import IriError
from .._models import JobState, JobStatus
from .._utils import _SLEEP

TERMINAL_JOB_STATES: list[JobState] = [
    JobState.completed,
    JobState.failed,
    JobState.canceled,
]


class Job(BaseModel):
    """
    Models a submitted IRI job and provides submission monitoring and job
    controls.
    """

    id: str

    _client: Any = PrivateAttr(default=None)
    _compute: Any = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, id: str, client: Any = None, compute: Any = None, **kwargs):
        super().__init__(id=id, **kwargs)
        self._client = client
        self._compute = compute

    def _job_status(self) -> JobStatus:
        if self._compute is None:
            raise IriError("job is not associated with a compute resource")

        r = self._client.get(
            f"compute/status/{self._compute.id}/{self.id}",
            params={"include_spec": True},
        )
        data = r.json()
        return JobStatus.model_validate(data.get("status", data))

    @property
    def status(self) -> JobStatus:
        """
        The current job status: its state, scheduler message, exit code, and
        ``meta_data`` (squeue / sacct output from the backend).
        """
        return self._job_status()

    def _wait(self, timeout: int = sys.maxsize) -> "Job":
        max_iteration = math.ceil(timeout / self._client._wait_interval)
        iteration = 0

        while True:
            if self._compute is None:
                raise IriError("job is not associated with a compute resource")

            status = self._job_status()
            if status.state in TERMINAL_JOB_STATES:
                if status.state == JobState.failed:
                    raise IriError(
                        f"job {self.id} failed: {status.message or 'no message'}"
                    )
                if status.state == JobState.canceled:
                    raise IriError(f"job {self.id} was cancelled")
                break

            if iteration == max_iteration:
                raise TimeoutError(
                    f"job {self.id} did not reach a terminal state within {timeout}s"
                )

            iteration += 1
            _SLEEP(self._client._wait_interval)

        return self

    def wait(self, timeout: Optional[int] = None) -> "Job":
        """
        Block until the job completes, fails, or is cancelled.

        :param timeout: Seconds to wait before raising ``TimeoutError``
        :return: The finished job
        :rtype: Job
        """
        return self._wait(timeout=timeout or sys.maxsize)

    def __await__(self):
        """Allow ``job`` to block until the job finishes."""
        return self._wait().__await__()

    def cancel(self) -> None:
        """
        Cancel the job.
        """
        if self._compute is None:
            raise IriError("job is not associated with a compute resource")

        self._client.delete(f"compute/cancel/{self._compute.id}/{self.id}")