"""Facility information.

The Superfacility API exposes API metadata under ``meta/changelog`` and
``meta/config``.  IRI exposes facility and site information under the
``facility`` router.
"""

from __future__ import annotations

from typing import Any, List

from .._models import Facility as FacilityModel
from .._models import Site

# Note: the model class is aliased (FacilityModel) because the generated
# synchronous client renames this wrapper class to ``Facility``, which would
# otherwise shadow the pydantic model import in the same module.


class Facility:
    def __init__(self, client: Any):
        self._client = client

    def info(self) -> FacilityModel:
        """
        Get information about the facility served by the API.

        :return: The facility
        :rtype: Facility
        """
        r = self._client.get("facility")
        return FacilityModel.model_validate(r.json())

    def sites(self) -> List[Site]:
        """
        Get the list of sites in the facility.

        :return: The sites
        :rtype: List[Site]
        """
        r = self._client.get("facility/sites")
        return [Site.model_validate(s) for s in r.json()]

    def site(self, site_id: str) -> Site:
        """
        Get a single site by id.

        :param site_id: The site id
        :return: The site
        :rtype: Site
        """
        r = self._client.get(f"facility/sites/{site_id}")
        return Site.model_validate(r.json())