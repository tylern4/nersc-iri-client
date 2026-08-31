"""Compute resource abstraction.

The Superfacility client models a compute site as a fixed ``Machine`` enum
(``perlmutter``, ...).  IRI compute resources are dynamic (each is a UUID), so
in this client a compute site is bound to one discovered resource id and
submits/lists jobs against that resource.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, PrivateAttr

from .._models import JobSpec
from .jobs import AsyncJob


class AsyncCompute(BaseModel):
    """
    Models a compute resource and its job management operations.
    """

    id: str
    name: Optional[str] = None

    _client: Any = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def __init__(self, id: str, name: Optional[str] = None, client: Any = None, **kwargs):
        super().__init__(id=id, name=name, **kwargs)
        self._client = client

    async def submit(self, jobspec: JobSpec) -> AsyncJob:
        """
        Submit a job to the compute resource.

        :param jobspec: The job specification
        :return: The submitted job
        :rtype: AsyncJob
        """
        r = await self._client.post(
            f"compute/job/{self.id}",
            json=jobspec.model_dump(exclude_none=True),
        )

        json_response = r.json()

        return AsyncJob(id=json_response["id"], client=self._client, compute=self)

    async def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        historical: Optional[bool] = None,
        limit: Optional[int] = None,
    ) -> List[AsyncJob]:
        """
        List jobs on the compute resource.

        :param filters: Optional backend filter dictionary, e.g.
                        ``{"user": "elvis"}``
        :param historical: Whether to include jobs that finished (if the
                           backend supports the distinction); when ``None``
                           the backend default applies
        :param limit: Maximum number of jobs to return
        :return: The jobs currently known to the queue
        :rtype: List[AsyncJob]
        """
        params = {}
        if historical is not None:
            params["historical"] = historical
        if limit is not None:
            params["limit"] = limit

        r = await self._client.post(
            f"compute/status/{self.id}",
            json=filters or {},
            params=params,
        )

        return [
            AsyncJob(id=job["id"], client=self._client, compute=self)
            for job in r.json()
        ]

    async def run(self, jobspec: JobSpec) -> AsyncJob:
        """
        Submit a job and block until it finishes.

        :param jobspec: The job specification
        :return: The finished job
        :rtype: AsyncJob
        """
        job = await self.submit(jobspec)
        return await job.wait()

    async def job(self, jobid: str) -> AsyncJob:
        """
        Get a job by id.

        The queue view used by :meth:`list` can lag newly submitted jobs, so
        this provides a direct per-job handle.  Job state is fetched lazily
        from ``compute/status/{id}/{jobid}`` on access.

        :param jobid: The job id
        :return: A handle to the job
        :rtype: AsyncJob
        """
        return AsyncJob(id=jobid, client=self._client, compute=self)