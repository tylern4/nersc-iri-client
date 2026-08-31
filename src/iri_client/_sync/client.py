"""Core asynchronous client for the IRI API.

Adapted from ``sfapi_client._async.client``.  The Superfacility API authenticates
with a private-key JWT client-credentials flow through authlib; IRI instead
expects a statically-issued bearer token, so this client drops authlib entirely
and resolves a token by priority:

    1. the ``access_token`` constructor argument
    2. the ``IRI_API_TOKEN`` environment variable
    3. ``~/.ssh/nersc-token``

Resolution is lazy: public read-only endpoints (facility, status, resource
discovery) work with no token at all, and a descriptive ``AuthError`` is only
raised when a privileged call is attempted without credentials.
"""

from __future__ import annotations

import os
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, cast

import httpx
import tenacity

from .compute import Compute
from .filesystem import Filesystem
from .account import Account
from .facility import Facility
from .status import Status
from ..exceptions import AuthError, ResourceLookupError
from .._models import Resource

IRI_BASE_URL = "https://api.iri.nersc.gov/api/v1"
IRI_TOKEN_ENV = "IRI_API_TOKEN"
IRI_TOKEN_FILE = "~/.ssh/nersc-token"
MAX_RETRY = 10


class ComputeResourceName(str, Enum):
    """
    Well-known IRI compute resources.

    IRI compute resources are dynamic UUIDs, so names are a convenience: each
    member's value is a name/group the server recognises (see
    ``Client.compute``).
    """

    jobs = "jobs"
    compute = "compute"


class FilesystemResourceName(str, Enum):
    """
    Well-known IRI filesystem resources.

    ``scratch`` and ``homes`` are the per-user systems used for active work;
    ``common`` and ``cfs`` are shared storage.  ``jobs`` / ``compute`` are the
    perlmutter compute resources, which also expose a filesystem endpoint.
    """

    scratch = "scratch"
    homes = "homes"
    common = "common"
    cfs = "cfs"
    dtns = "dtns"
    jobs = "jobs"
    compute = "compute"
    login = "login"


# Retry on httpx.HTTPStatusError recoverable status codes.
class retry_if_http_status_error(tenacity.retry_if_exception):
    def __init__(self):
        super().__init__(self._retry)

    def _retry(self, e: Exception):
        retry_codes = [
            httpx.codes.TOO_MANY_REQUESTS,
            httpx.codes.BAD_GATEWAY,
            httpx.codes.SERVICE_UNAVAILABLE,
            httpx.codes.GATEWAY_TIMEOUT,
        ]
        return (
            isinstance(e, httpx.HTTPStatusError)
            and cast(httpx.HTTPStatusError, e).response.status_code in retry_codes
        )


class Client:
    def __init__(
        self,
        access_token: Optional[str] = None,
        api_base_url: Optional[str] = IRI_BASE_URL,
        wait_interval: int = 10,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        """
        Create a client instance.

        Usage:

        ```python
        >>> from iri_client import Client
        >>> with Client() as client:
        >>>     # Use client
        ```

        :param access_token: An existing IRI bearer token
        :param api_base_url: The API base URL
        :param wait_interval: Number of seconds to sleep between status polls
                              while waiting on jobs and tasks
        :param transport: An optional httpx transport (e.g. MockTransport) used
                          to test the client without a live network
        :return: The client instance
        :rtype: Client
        """
        self._access_token = access_token
        self._api_base_url = api_base_url
        self._wait_interval = wait_interval
        self._transport = transport
        self.__http_client: Optional[httpx.Client] = None
        self._account = None
        self._facility = None
        self._status = None

    def __enter__(self):
        return self

    def _token_from_env(self) -> Optional[str]:
        return os.environ.get(IRI_TOKEN_ENV)

    def _token_from_file(self) -> Optional[str]:
        _path = Path(IRI_TOKEN_FILE).expanduser().resolve()
        if _path.exists():
            with _path.open() as token_file:
                token = token_file.read().strip()
            if token:
                return token
        return None

    def _get_token(self) -> Optional[str]:
        """
        Resolve a bearer token by priority: explicit argument, environment
        variable, well-known token file.  Returns ``None`` when no source has
        a token (public endpoints do not need one).
        """
        if self._access_token is not None:
            return self._access_token

        token = self._token_from_env()
        if token is not None:
            return token

        return self._token_from_file()

    def _http_client(self) -> httpx.Client:
        headers = {"accept": "application/json"}
        if self.__http_client is None:
            token = self._get_token()
            if token is not None:
                headers.update({"Authorization": f"Bearer {token}"})
            self.__http_client = httpx.Client(
                headers=headers, transport=self._transport
            )

        return self.__http_client

    def _require_token(self) -> str:
        """
        Resolve a bearer token or fail fast with ``AuthError``.

        Mirrors the ``check_auth`` guard in ``sfapi_client``: privileged calls
        should fail with a descriptive message rather than a bare 401.
        """
        token = self._get_token()
        if token is None:
            raise AuthError(
                "no IRI bearer token available; set the IRI_API_TOKEN "
                "environment variable, place the token at ~/.ssh/nersc-token, "
                "or pass access_token to the client"
            )
        return token

    def _request(
        self,
        method: str,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        # Public read-only routes need no credentials (mirrors sfapi_client);
        # everything else fails fast with a descriptive AuthError.
        public_prefixes = (
            "facility",
            "status/",
            "account/capabilities",
            "compute/resources",
            "filesystem/resources",
        )
        if not url.startswith(public_prefixes):
            self._require_token()

        client = self._http_client()
        r = client.request(
            method,
            f"{self._api_base_url}/{url}",
            params=params,
            data=data,
            json=json,
            files=files,
        )
        r.raise_for_status()

        return r

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(httpx.TimeoutException)
        | tenacity.retry_if_exception_type(httpx.ConnectError)
        | retry_if_http_status_error(),
        wait=tenacity.wait_exponential(max=MAX_RETRY),
        stop=tenacity.stop_after_attempt(MAX_RETRY),
    )
    def get(
        self, url: str, params: Dict[str, Any] = {}
    ) -> httpx.Response:
        return self._request("GET", url, params=params)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(httpx.TimeoutException)
        | tenacity.retry_if_exception_type(httpx.ConnectError)
        | retry_if_http_status_error(),
        wait=tenacity.wait_exponential(max=MAX_RETRY),
        stop=tenacity.stop_after_attempt(MAX_RETRY),
    )
    def post(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        return self._request("POST", url, data=data, json=json, files=files, params=params)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(httpx.TimeoutException)
        | tenacity.retry_if_exception_type(httpx.ConnectError)
        | retry_if_http_status_error(),
        wait=tenacity.wait_exponential(max=MAX_RETRY),
        stop=tenacity.stop_after_attempt(MAX_RETRY),
    )
    def put(
        self,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        return self._request("PUT", url, data=data, json=json, params=params)

    @tenacity.retry(
        retry=tenacity.retry_if_exception_type(httpx.TimeoutException)
        | tenacity.retry_if_exception_type(httpx.ConnectError)
        | retry_if_http_status_error(),
        wait=tenacity.wait_exponential(max=MAX_RETRY),
        stop=tenacity.stop_after_attempt(MAX_RETRY),
    )
    def delete(self, url: str, params: Dict[str, Any] = {}) -> httpx.Response:
        return self._request("DELETE", url, params=params)

    def close(self):
        """
        Release resources associated with the client instance.
        """
        if self.__http_client is not None:
            self.__http_client.close()
            self.__http_client = None

    def __exit__(self, type, value, traceback):
        self.close()

    @property
    def token(self) -> Optional[str]:
        """
        The bearer token resolved for this client, if any.
        """
        token = self._get_token()
        if token is not None:
            return token

    @staticmethod
    def _match_resource(
        resources: List[Resource], name: Optional[str] = None
    ) -> Resource:
        """
        Resolve a resource from the discovery list by ``name``, ``group``, or
        ``id``.

        ``name`` may be a plain string or a ``FilesystemResourceName`` /
        ``ComputeResourceName`` enum member.

        If server resources are named e.g. ``"Perlmutter"`` and ``"Perlmutter
        GPU"`` simultaneously with ``"jobs"`` / ``"compute"`` groups, the match
        is either the unambiguous id/group/name hit, or the single resource in
        the list (when ``name`` is ``None``).
        """
        if name is None:
            if len(resources) == 1:
                return resources[0]
            raise ResourceLookupError(
                "multiple resources available; specify name, group, or id:\n"
                + "\n".join(_describe_resource(r) for r in resources)
            )

        # Accept a plain string or a *ResourceName enum member.  Note that
        # ``str()`` on a str-Enum member yields "<EnumName>.<member>", so the
        # value must be unwrapped via ``.value`` when present.
        name = name.value if isinstance(name, Enum) else name
        for r in resources:
            if r.id == name or r.group == name or r.name == name:
                return r

        raise ResourceLookupError(
            f"no resource named '{name}'. Available:\n"
            + "\n".join(_describe_resource(r) for r in resources)
        )

    def _discover(self, router: str) -> List[Resource]:
        r = self.get(f"{router}/resources")
        return [Resource.model_validate(item) for item in r.json()]

    def compute_resources(self) -> List[Resource]:
        """
        Discover available compute resources.

        :return: The compute resources of the site
        :rtype: List[Resource]
        """
        return self._discover("compute")

    def filesystem_resources(self) -> List[Resource]:
        """
        Discover available filesystem resources.

        :return: The filesystem resources of the site
        :rtype: List[Resource]
        """
        return self._discover("filesystem")

    def compute(
        self, name: Union[str, ComputeResourceName] = "jobs"
    ) -> Compute:
        """
        Get a compute site to submit jobs or view the queue.

        IRI compute resources are dynamic UUIDs, so the client discovers them
        from the (public) ``compute/resources`` endpoint and binds the requested
        one by name/group/id.  The default, ``"jobs"``, is the resource the IRI
        deployment expects job submission against.  ``name`` may also be a
        ``ComputeResourceName`` member or an id.

        :param name: The compute resource name, group, or id
        :return: Compute object that can be used to start jobs and view the
                 queue
        :rtype: Compute
        """
        resources = self.compute_resources()
        resource = self._match_resource(resources, name)
        return Compute(id=resource.id, name=resource.name, client=self)

    def filesystem(
        self, name: Union[str, FilesystemResourceName] = "scratch"
    ) -> Filesystem:
        """
        Get a filesystem abstraction for listing, editing, and copying files
        on a filesystem resource.

        ``name`` may be a plain string (e.g. ``"scratch"``), a
        ``FilesystemResourceName`` member, or a resource id.

        :param name: The filesystem resource name, group, or id
        :return: Object with filesystem related objects and methods
        :rtype: Filesystem
        """
        resources = self.filesystem_resources()
        resource = self._match_resource(resources, name)
        return Filesystem(id=resource.id, name=resource.name, client=self)

    @property
    def account(self) -> Account:
        """
        Account related objects and methods (projects, allocations).
        """
        if self._account is None:
            self._account = Account(self)
        return self._account

    @property
    def facility(self) -> Facility:
        """
        Facility related information (information, sites, changelog).
        """
        if self._facility is None:
            self._facility = Facility(self)
        return self._facility

    @property
    def status(self) -> Status:
        """
        Status related objects and methods (outages, notes, incidents).
        """
        if self._status is None:
            self._status = Status(self)
        return self._status


def _describe_resource(r: Resource) -> str:
    return f"  id: {r.id}  name: {r.name}  group: {r.group}"