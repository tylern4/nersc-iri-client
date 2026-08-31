import os
import tempfile

import pytest


def make_local_file(content: bytes = b"iri filesystem test\n") -> str:
    local = tempfile.NamedTemporaryFile(suffix=".txt", delete=False)
    local.write(content)
    local.close()
    return local.name


@pytest.fixture
def test_dir(test_tmp_dir):
    if not test_tmp_dir:
        pytest.skip("no TEST_TMP_DIR configured")
    import random
    import string

    rand = "".join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{test_tmp_dir}/iri_test_{rand}"


@pytest.mark.api_auth
def test_filesystem_roundtrip(authenticated_client, test_dir):
    with authenticated_client as client:
        fs = client.filesystem("scratch")
        try:
            fs.rm(test_dir)
        except Exception:
            pass

        fs.mkdir(test_dir, parent=True)
        fs.mkdir(f"{test_dir}/sub")

        local = make_local_file()
        try:
            fs.upload(local, f"{test_dir}/hello.txt")

            entries = {e["name"]: e for e in fs.list(test_dir)}
            assert any(e["type"] == "f" for e in entries.values())
            assert any(e["type"] == "d" for e in entries.values())

            # view/head/tail unwrap the content payload for you.
            assert fs.view(f"{test_dir}/hello.txt").startswith("iri filesystem test")
            assert fs.head(f"{test_dir}/hello.txt", lines=1) == "iri filesystem test\n"
            assert fs.tail(f"{test_dir}/hello.txt", lines=1) == "iri filesystem test\n"

            info = fs.stat(f"{test_dir}/hello.txt")
            assert info["size"] == len(b"iri filesystem test\n")

            # checksum unwraps the hash string.
            assert isinstance(fs.checksum(f"{test_dir}/hello.txt"), str)

            downloaded = fs.download(f"{test_dir}/hello.txt")
            assert downloaded == "iri filesystem test\n"

            fs.copy(f"{test_dir}/hello.txt", f"{test_dir}/copy.txt")
            fs.move(f"{test_dir}/copy.txt", f"{test_dir}/moved.txt")
            fs.chmod(f"{test_dir}/moved.txt", "640")
            fs.chown(f"{test_dir}/moved.txt", group="elvis")
            fs.symlink(f"{test_dir}/hello.txt", f"{test_dir}/link")
            fs.compress(f"{test_dir}/hello.txt", f"{test_dir}/hello.tar.gz", "gzip")

            names = {e["name"] for e in fs.list(test_dir)}
            assert f"{test_dir}/moved.txt" in names
            assert f"{test_dir}/link" in names

            # Task submissions are explicit; verify awaiting works too.
            task = fs.submit_view(f"{test_dir}/hello.txt")
            task.wait(timeout=120)
            assert task.status.value == "completed"
            assert task.output["content"]
        finally:
            fs.rm(test_dir)
            try:
                os.unlink(local)
            except OSError:
                pass


@pytest.mark.api_auth
def test_filesystem_task_failure(authenticated_client, test_dir):
    with authenticated_client as client:
        fs = client.filesystem("scratch")
        # head/tail/checksum on a missing path is a genuine backend error
        # (view silently returns empty content).
        task = fs.submit_head(f"{test_dir}/does_not_exist", lines=1)
        with pytest.raises(Exception):
            task.wait(timeout=120)