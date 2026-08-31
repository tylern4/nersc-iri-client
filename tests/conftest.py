import os
from pathlib import Path
from typing import Optional

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
    TEST_JOB_ACCOUNT: Optional[str] = "m3792"
    TEST_JOB_QUEUE: Optional[str] = "debug"
    TEST_TMP_DIR: Optional[str] = "/pscratch/sd/t/tylern/tmp/iri_client_tests"
    TEST_USERNAME: Optional[str] = "tylern"

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
def unauthenticated_client(api_base_url):
    return Client(api_base_url=api_base_url)


@pytest.fixture
def async_unauthenticated_client(api_base_url):
    return AsyncClient(api_base_url=api_base_url)


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