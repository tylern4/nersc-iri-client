"""Account abstraction: the IRI analog of the Superfacility *projects* API.

The Superfacility API models a user's accounts as ``Project`` objects.  IRI
keeps the same name and adds layered allocations (project -> project
allocation -> user allocation), all under the ``account`` router.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .._models import (
    AllocationEntry,
    Project,
    ProjectAllocation,
    UserAllocation,
)


class Account:
    def __init__(self, client: Any):
        self._client = client

    def projects(self) -> List[Project]:
        """
        Get the list of projects the authenticated user belongs to.

        :return: The projects
        :rtype: List[Project]
        """
        r = self._client.get("account/projects")
        return [Project.model_validate(p) for p in r.json()]

    def project(self, project_id: str) -> Project:
        """
        Get a single project by id.

        :param project_id: The project id
        :return: The project
        :rtype: Project
        """
        r = self._client.get(f"account/projects/{project_id}")
        return Project.model_validate(r.json())

    def project_allocations(self, project_id: str) -> List[ProjectAllocation]:
        """
        Get the allocations for a project.

        :param project_id: The project id
        :return: The project allocations
        :rtype: List[ProjectAllocation]
        """
        r = self._client.get(
            f"account/projects/{project_id}/project_allocations"
        )
        return [ProjectAllocation.model_validate(a) for a in r.json()]

    def project_allocation(
        self, project_id: str, project_allocation_id: str
    ) -> ProjectAllocation:
        """
        Get a single project allocation.

        :param project_id: The project id
        :param project_allocation_id: The project allocation id
        :return: The project allocation
        :rtype: ProjectAllocation
        """
        r = self._client.get(
            f"account/projects/{project_id}/project_allocations/"
            f"{project_allocation_id}"
        )
        return ProjectAllocation.model_validate(r.json())

    def user_allocations(self, project_id: str, project_allocation_id: str) -> List[UserAllocation]:
        """
        Get the user allocations for a project allocation.

        :param project_id: The project id
        :param project_allocation_id: The project allocation id
        :return: The user allocations
        :rtype: List[UserAllocation]
        """
        r = self._client.get(
            f"account/projects/{project_id}/project_allocations/"
            f"{project_allocation_id}/user_allocations"
        )
        return [UserAllocation.model_validate(a) for a in r.json()]

    def usage(self, project_id: str) -> List[AllocationEntry]:
        """
        Get the current allocation usage for a project.

        :param project_id: The project id
        :return: The allocation entries (usage and limits)
        :rtype: List[AllocationEntry]
        """
        allocations = self.project_allocations(project_id)
        entries: List[AllocationEntry] = []
        for allocation in allocations:
            for entry in allocation.entries:
                entries.append(entry)
        return entries