import os
from pathlib import Path
from typing import Optional

import httpx
import pytest
from pydantic_settings import BaseSettings, SettingsConfigDict

from iri_client import AsyncClient, Client
from iri_client._async.client import IRI_TOKEN_ENV, IRI_TOKEN_FILE


class Settings(BaseSettings):
    """Test settings; every value also falls back to an environment variable.

    The defaults match the live NERSC IRI deployment these tests were written
    against (Perlmutter).  Override via environment variables or a ``.env``
    file.
    """

    IRI_API_BASE_URL: str = "https://api.iri.nersc.gov/api/v1"
    IRI_ACCESS_TOKEN: Optional[str] = None
    TEST_JOB_ACCOUNT: Optional[str] = "m0000"
    TEST_JOB_QUEUE: Optional[str] = "debug"
    TEST_TMP_DIR: Optional[str] = "/pscratch/sd/e/elvis/tmp/iri_client_tests"
    TEST_USERNAME: Optional[str] = "elvis"

    model_config = SettingsConfigDict(case_sensitive=True, env_file=".env")


settings = Settings(_env_file=".env")


def resolve_token() -> Optional[str]:
    """Resolve a bearer token the same priority order as the client."""
    sources = [
        settings.IRI_ACCESS_TOKEN,
        os.environ.get(IRI_TOKEN_ENV),
    ]
    path = Path(IRI_TOKEN_FILE).expanduser().resolve()
    if path.exists():
        sources.append(path.read_text().strip())

    return next((t for t in sources if t), None)


@pytest.fixture
def api_base_url():
    return settings.IRI_API_BASE_URL


@pytest.fixture
def test_job_account():
    return settings.TEST_JOB_ACCOUNT


@pytest.fixture
def test_job_queue():
    return settings.TEST_JOB_QUEUE


@pytest.fixture
def test_tmp_dir():
    return settings.TEST_TMP_DIR


@pytest.fixture
def test_username():
    return settings.TEST_USERNAME


@pytest.fixture
def access_token():
    return resolve_token()


@pytest.fixture
def authenticated_client(api_base_url, access_token):
    if access_token is None:
        pytest.skip("no IRI bearer token found (IRI_API_TOKEN or ~/.ssh/nersc-token)")
    return Client(api_base_url=api_base_url, access_token=access_token)


@pytest.fixture
def async_authenticated_client(api_base_url, access_token):
    if access_token is None:
        pytest.skip("no IRI bearer token found (IRI_API_TOKEN or ~/.ssh/nersc-token)")
    return AsyncClient(api_base_url=api_base_url, access_token=access_token)


#
# Hermetic fixtures for the no-token public endpoints.  The public read-only
# routes (facility, status, resource discovery) are tested with a mocked httpx
# transport so CI exercises the client's request pipeline (including the
# auth guard) deterministically, without a live network or bearer token.
#
def _pub_resource(resource_id, name, group, status="up"):
    return {
        "id": resource_id,
        "name": name,
        "group": group,
        "resource_type": "compute",
        "current_status": status,
        "site_uri": "urn:site:perlmutter",
        "self_uri": resource_id,
        "capability_uris": [],
        "last_modified": "2026-01-01T00:00:00Z",
    }


def _pub_facility():
    site_uri = "urn:site:perlmutter"
    return {
        "id": "urn:iri:facility:nersc",
        "name": "NERSC",
        "short_name": "NERSC",
        "organization_name": "Lawrence Berkeley National Laboratory",
        "self_uri": "urn:iri:facility:nersc",
        "site_uris": [site_uri],
        "last_modified": "2026-01-01T00:00:00Z",
    }


def _pub_site():
    return {
        "id": "urn:site:perlmutter",
        "name": "Perlmutter",
        "operating_organization": "Lawrence Berkeley National Laboratory",
        "self_uri": "urn:site:perlmutter",
        "resource_uris": [],
        "last_modified": "2026-01-01T00:00:00Z",
    }


PUBLIC_ROUTES = {
    "facility": _pub_facility(),
    "facility/sites": [_pub_site()],
    "compute/resources": [
        _pub_resource("urn:iri:resource:jobs", "Perlmutter", "jobs"),
        _pub_resource("urn:iri:resource:compute", "Perlmutter GPU", "compute"),
    ],
    "filesystem/resources": [
        _pub_resource("urn:iri:resource:scratch", "Perlmutter Scratch", "scratch"),
        _pub_resource("urn:iri:resource:homes", "Storage Homes", "homes"),
        _pub_resource("urn:iri:resource:jobs", "Perlmutter", "jobs"),
    ],
    "status/resources": [
        _pub_resource("urn:iri:resource:jobs", "Perlmutter", "jobs"),
        _pub_resource("urn:iri:resource:scratch", "Perlmutter Scratch", "scratch", "unknown"),
    ],
    "status/incidents": [
        {
            "id": "urn:iri:incident:1",
            "name": "Planned maintenance",
            "status": "up",
            "type": "planned",
            "resolution": "completed",
            "start": "2026-01-01T00:00:00Z",
            "self_uri": "urn:iri:incident:1",
            "event_uris": [],
            "resource_uris": [],
            "last_modified": "2026-01-01T00:00:00Z",
        }
    ],
    "status/events": [
        {
            "id": "urn:iri:event:1",
            "name": "Perlmutter reached up",
            "status": "up",
            "occurred_at": "2026-01-01T00:00:00Z",
            "self_uri": "urn:iri:event:1",
            "resource_uri": "urn:iri:resource:jobs",
            "incident_uri": None,
            "last_modified": "2026-01-01T00:00:00Z",
        }
    ],
}


def _public_transport_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path.split("/api/v1/", 1)[-1]
    payload = PUBLIC_ROUTES.get(path)
    if payload is None:
        return httpx.Response(404, json={"error": f"no mock for {path}"})
    return httpx.Response(200, json=payload)


@pytest.fixture
def public_client(api_base_url):
    transport = httpx.MockTransport(_public_transport_handler)
    return Client(api_base_url=api_base_url, transport=transport)


@pytest.fixture
def async_public_client(api_base_url):
    transport = httpx.MockTransport(_public_transport_handler)
    return AsyncClient(api_base_url=api_base_url, transport=transport)