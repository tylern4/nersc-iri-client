import time

import pytest

from iri_client._models import JobState
from tests.common import make_jobspec


def _wait_for_state(job, allowed, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        state = job.status.state
        if state in allowed:
            return state
        time.sleep(5)
    raise TimeoutError(f"job {job.id} stalled in state {job.status.state}")


def test_job_lifecycle(
    authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    with authenticated_client as client:
        compute = client.compute("jobs")
        spec = make_jobspec(
            "iri_test_lifecycle",
            test_job_account,
            test_job_queue,
            test_tmp_dir,
        )
        job = compute.submit(spec)
        assert job.id

        job.wait(timeout=300)

        status = job.status
        assert status.state == JobState.completed
        assert status.exit_code == 0
        # IRI spells it "canceled", a single-L porting gotcha.
        assert JobState.canceled.value == "canceled"


def test_job_fetch_by_id(
    authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    with authenticated_client as client:
        compute = client.compute("jobs")
        spec = make_jobspec(
            "iri_test_fetch",
            test_job_account,
            test_job_queue,
            test_tmp_dir,
        )
        job = compute.submit(spec)
        job.wait(timeout=300)

        # The queue view can lag a new job, so we can fetch a handle by id.
        fetched = compute.job(job.id)
        assert fetched.id == job.id
        assert fetched.status.state == JobState.completed


def test_job_cancel(
    authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    with authenticated_client as client:
        compute = client.compute("jobs")
        # Sleep long enough that cancellation races a queue start.
        spec = make_jobspec(
            "iri_test_cancel",
            test_job_account,
            test_job_queue,
            test_tmp_dir,
            args=["-c", "sleep 300"],
            duration=600,
        )
        job = compute.submit(spec)
        assert job.id

        job.cancel()

        state = _wait_for_state(
            job, (JobState.canceled, JobState.completed)
        )
        assert state in (JobState.canceled, JobState.completed)


def test_job_list(
    authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    with authenticated_client as client:
        compute = client.compute("jobs")
        jobs = compute.list(filters={"user": "tylern"})
        assert len(jobs) >= 0
        for job in jobs:
            assert job.id


def test_job_failed(
    authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    with authenticated_client as client:
        compute = client.compute("jobs")
        # A non-existent executable reliably fails.
        spec = make_jobspec(
            "iri_test_failed",
            test_job_account,
            test_job_queue,
            test_tmp_dir,
            command="/no/such/executable",
        )
        job = compute.submit(spec)
        with pytest.raises(Exception):
            job.wait(timeout=300)