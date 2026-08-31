import os
import random
import string
import tempfile

import pytest


@pytest.fixture
def test_dir(test_tmp_dir):
    if not test_tmp_dir:
        pytest.skip("no TEST_TMP_DIR configured")
    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{test_tmp_dir}/iri_test_async_{rand}"


@pytest.mark.asyncio
@pytest.mark.api_dev
async def test_filesystem_task_await(async_authenticated_client, test_dir):
    async with async_authenticated_client as client:
        fs = await client.filesystem("scratch")

        await fs.mkdir(test_dir, parent=True)

        task = await fs.submit_stat(test_dir)
        # submit_* yields the raw task; awaiting wait() blocks until it is
        # terminal and the result is available.
        task = await task.wait()
        assert task.output["mode"]

        await fs.rm(test_dir)


@pytest.mark.asyncio
@pytest.mark.api_dev
async def test_async_filesystem_blocking(async_authenticated_client, test_dir):
    async with async_authenticated_client as client:
        fs = await client.filesystem("scratch")
        local = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
        local.write(b"async content\n")
        local.close()
        try:
            await fs.mkdir(test_dir, parent=True)
            await fs.upload(local.name, f"{test_dir}/a.txt")

            output = (await fs.download(f"{test_dir}/a.txt"))
            assert output == "async content\n"

            entries = await fs.list(test_dir)
            names = {e["name"]: e for e in entries}
            assert f"{test_dir}/a.txt" in names
        finally:
            await fs.rm(test_dir)
            try:
                os.unlink(local.name)
            except OSError:
                pass