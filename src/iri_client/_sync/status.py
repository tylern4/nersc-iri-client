"""Status and incident information.

The Superfacility API exposes outages, notes, and per-resource status via the
``status`` router.  IRI replaces these with a resource-centric event/incident
model: ``status/resources`` (resources and their ``current_status``),
``status/events`` (status changes), and ``status/incidents`` (planned and
unplanned incidents affecting resources).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Union

from .._models import Event, Incident, Resource
from .._models import Status as StatusModel

# StatusModel is aliased: the synchronous client renames this wrapper to
# ``Status``, which would otherwise shadow the pydantic enum import.


class Status:
    def __init__(self, client: Any):
        self._client = client

    def statuses(
        self,
        resource_name: Optional[str] = None,
    ) -> Union[Dict[str, StatusModel], StatusModel]:
        """
        Get the current status of resources.

        :param resource_name: The resource name (or id) to query; when omitted,
                              all resources are returned as a name -> status map
        :return: The resource status, or a map of resource name to status
        :rtype: Union[Dict[str, Status], Status]
        """
        response = self._client.get("status/resources")
        resources = [Resource.model_validate(r) for r in response.json()]

        if resource_name:
            for r in resources:
                if r.name == resource_name or r.id == resource_name:
                    return r.current_status
            raise ValueError(f"unknown resource: {resource_name}")

        return {r.name: r.current_status for r in resources if r.name}

    def resources(self) -> List[Resource]:
        """
        Get the list of resources and their current status.

        :return: The IRI resources
        :rtype: List[Resource]
        """
        response = self._client.get("status/resources")
        return [Resource.model_validate(r) for r in response.json()]

    def incidents(
        self, incident_id: Optional[str] = None
    ) -> Union[List[Incident], Incident]:
        """
        Get incidents.

        :param incident_id: A specific incident id; when omitted, all incidents
        :return: The incidents
        :rtype: Union[List[Incident], Incident]
        """
        url = "status/incidents" if incident_id is None else f"status/incidents/{incident_id}"
        response = self._client.get(url)
        if incident_id:
            return Incident.model_validate(response.json())
        return [Incident.model_validate(i) for i in response.json()]

    def events(self) -> List[Event]:
        """
        Get status-change events.

        :return: The events
        :rtype: List[Event]
        """
        response = self._client.get("status/events")
        return [Event.model_validate(e) for e in response.json()]