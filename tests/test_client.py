import httpx
import pytest

from iri_client import Client, AsyncClient
from iri_client.exceptions import ResourceLookupError


def test_public_facility(public_client):
    with public_client as client:
        facility = client.facility.info()
        assert facility.id
        assert facility.organization_name


def test_public_sites(public_client):
    with public_client as client:
        sites = client.facility.sites()
        assert len(sites) > 0


def test_public_status(public_client):
    with public_client as client:
        statuses = client.status.statuses()
        assert len(statuses) > 0
        assert all(v in ("up", "down", "degraded", "unknown") for v in statuses.values())


def test_public_resource_discovery(public_client):
    with public_client as client:
        compute = client.compute_resources()
        assert len(compute) > 0
        filesystems = client.filesystem_resources()
        assert len(filesystems) > 0


def test_compute_default_binding(public_client):
    with public_client as client:
        compute = client.compute("jobs")
        assert compute.id
        assert compute.name


def test_filesystem_default_binding(public_client):
    with public_client as client:
        fs = client.filesystem("scratch")
        assert fs.id


def test_compute_lookup_by_id(public_client):
    with public_client as client:
        resources = client.compute_resources()
        compute = client.compute(resources[0].id)
        assert compute.id == resources[0].id


def test_resource_lookup_error(public_client):
    with public_client as client:
        with pytest.raises(ResourceLookupError):
            client.compute("does-not-exist")


def test_sync_async_are_separate_implementations():
    assert Client is not AsyncClient
    assert "iri_client._sync" in Client.__module__
    assert "iri_client._async" in AsyncClient.__module__


def test_token_resolution_unauthenticated_is_lazy(api_base_url, monkeypatch):
    monkeypatch.delenv("IRI_API_TOKEN", raising=False)
    monkeypatch.setattr(
        "iri_client._async.client.IRI_TOKEN_FILE",
        "/no/such/token/file",
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "id": "urn:iri:facility:nersc",
                "organization_name": "Lawrence Berkeley National Laboratory",
                "self_uri": "urn:iri:facility:nersc",
                "site_uris": [],
                "last_modified": "2026-01-01T00:00:00Z",
            },
        )
    )
    client = Client(api_base_url=api_base_url, transport=transport)
    try:
        # Public calls work with no token at all.
        facility = client.facility.info()
        assert facility.id
    finally:
        client.close()