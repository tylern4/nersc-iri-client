import pytest


@pytest.mark.asyncio
async def test_async_job_lifecycle(
    async_authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    from iri_client._models import JobState
    from tests.common import make_jobspec

    async with async_authenticated_client as client:
        compute = await client.compute("jobs")
        spec = make_jobspec(
            "iri_test_lifecycle_async",
            test_job_account,
            test_job_queue,
            test_tmp_dir,
        )
        job = await compute.submit(spec)
        assert job.id

        await job.wait(timeout=300)

        status = await job.status
        assert status.state == JobState.completed
        assert status.exit_code == 0
        # Awaiting the job object itself must also resolve to completion.
        job2 = await compute.submit(
            make_jobspec(
                "iri_test_awaitable_async",
                test_job_account,
                test_job_queue,
                test_tmp_dir,
            )
        )
        await job2
        assert (await job2.status).state == JobState.completed

        # A handle can also be re-fetched by id once the job is terminal.
        fetched = await compute.job(job.id)
        assert (await fetched.status).state == JobState.completed


@pytest.mark.asyncio
async def test_async_job_cancel(
    async_authenticated_client, test_job_account, test_job_queue, test_tmp_dir
):
    from iri_client._models import JobState
    from tests.common import make_jobspec

    async with async_authenticated_client as client:
        compute = await client.compute("jobs")
        spec = make_jobspec(
            "iri_test_cancel_async",
            test_job_account,
            test_job_queue,
            test_tmp_dir,
            args=["-c", "sleep 300"],
            duration=600,
        )
        job = await compute.submit(spec)

        await job.cancel()

        status = await job.status
        assert status.state in (JobState.canceled, JobState.completed)