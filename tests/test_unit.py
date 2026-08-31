"""Offline unit tests: no network access, no token required.

These exercise token resolution order and the ``AuthError`` fail-fast guard on
the client, plus job/task waiter helpers with stub responses.
"""

import pytest

from iri_client import Client, AsyncClient
from iri_client.exceptions import AuthError


def _no_token(monkeypatch):
    monkeypatch.delenv("IRI_API_TOKEN", raising=False)
    for mod in ("_async", "_sync"):
        monkeypatch.setattr(
            f"iri_client.{mod}.client.IRI_TOKEN_FILE", "/no/such/token"
        )


def _token_file(monkeypatch, path):
    monkeypatch.delenv("IRI_API_TOKEN", raising=False)
    for mod in ("_async", "_sync"):
        monkeypatch.setattr(
            f"iri_client.{mod}.client.IRI_TOKEN_FILE", str(path)
        )


def test_auth_error_without_any_token(monkeypatch):
    _no_token(monkeypatch)

    client = Client(api_base_url="http://127.0.0.1:1")
    try:
        with pytest.raises(AuthError):
            client.account.projects()
    finally:
        client.close()


@pytest.mark.asyncio
async def test_async_auth_error_without_any_token(monkeypatch):
    _no_token(monkeypatch)

    client = AsyncClient(api_base_url="http://127.0.0.1:1")
    try:
        with pytest.raises(AuthError):
            await client.account.projects()
    finally:
        await client.close()


def test_token_precedence_access_token_beats_env(monkeypatch):
    monkeypatch.setenv("IRI_API_TOKEN", "env-token")
    client = Client(access_token="arg-token", api_base_url="http://127.0.0.1:1")
    try:
        resolved = client._get_token()
        assert resolved == "arg-token"
    finally:
        client.close()


def test_token_precedence_env_beats_file(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("file-token\n")
    _token_file(monkeypatch, token_file)
    monkeypatch.setenv("IRI_API_TOKEN", "env-token")

    client = Client(api_base_url="http://127.0.0.1:1")
    try:
        resolved = client._get_token()
        assert resolved == "env-token"
    finally:
        client.close()


def test_token_from_file_without_env(monkeypatch, tmp_path):
    token_file = tmp_path / "token"
    token_file.write_text("  file-token  \n")
    _token_file(monkeypatch, token_file)

    client = Client(api_base_url="http://127.0.0.1:1")
    try:
        resolved = client._get_token()
        assert resolved == "file-token"
    finally:
        client.close()


def test_resource_match_helpers(monkeypatch):
    from iri_client.exceptions import ResourceLookupError
    from iri_client._models import Resource, ResourceType, Status

    def make_resource(resource_id, name, group=None):
        return Resource(
            id=resource_id,
            name=name,
            group=group,
            description="test",
            last_modified="2026-02-21T12:00:00Z",
            resource_type=ResourceType.compute,
            current_status=Status.up,
            site_uri="urn:site:0",
            self_uri=f"urn:resource:{resource_id}",
            capability_uris=[],
        )

    jobs = make_resource("uuid-jobs", "jobs resource", group="jobs")
    compute = make_resource("uuid-compute", "compute resource", group="compute")

    assert AsyncClient._match_resource([jobs, compute], "jobs").id == "uuid-jobs"
    assert AsyncClient._match_resource([jobs, compute], "uuid-compute").id == "uuid-compute"

    with pytest.raises(ResourceLookupError):
        AsyncClient._match_resource([jobs, compute], "nope")

    with pytest.raises(ResourceLookupError):
        AsyncClient._match_resource([jobs, compute], None)


def test_resource_match_by_enum(monkeypatch):
    from iri_client._models import Resource, ResourceType, Status
    from iri_client import ComputeResourceName, FilesystemResourceName
    from iri_client._sync.client import (
        ComputeResourceName as SyncComputeResourceName,
        FilesystemResourceName as SyncFilesystemResourceName,
    )

    def make_resource(resource_id, name, group=None):
        return Resource(
            id=resource_id,
            name=name,
            group=group,
            description="test",
            last_modified="2026-02-21T12:00:00Z",
            resource_type=ResourceType.compute,
            current_status=Status.up,
            site_uri="urn:site:0",
            self_uri=f"urn:resource:{resource_id}",
            capability_uris=[],
        )

    scratch = make_resource(
        "uuid-scratch", "scratch", group="perlmutter"
    )
    jobs = make_resource("uuid-jobs", "jobs", group="perlmutter")

    # The top-level (async-module) enum resolves in the async matcher.
    assert (
        AsyncClient._match_resource([scratch, jobs], FilesystemResourceName.scratch).id
        == "uuid-scratch"
    )
    assert (
        AsyncClient._match_resource([scratch, jobs], ComputeResourceName.jobs).id
        == "uuid-jobs"
    )

    # A str-Enum member resolves via its `.value`, not `str()` (which yields
    # the "<EnumName>.<member>" repr).  Both clients' enum classes work.
    assert (
        AsyncClient._match_resource(
            [scratch, jobs], SyncFilesystemResourceName.scratch
        ).id
        == "uuid-scratch"
    )
    assert (
        AsyncClient._match_resource(
            [scratch, jobs], SyncComputeResourceName.jobs
        ).id
        == "uuid-jobs"
    )