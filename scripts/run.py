"""Development tools for nersc-iri-client.

Mirrors the workflow of NERSC/sfapi_client:

* `models`   — generate pydantic models from the IRI OpenAPI spec.
* `unasync`  — generate the synchronous interface (`_sync/`) from the
  asynchronous implementation (`_async/`), keeping a single source of truth.
"""

import re
from pathlib import Path

import typer
import unasync

cli = typer.Typer()

SRC = Path(__file__).parent.parent / "src" / "iri_client"
ASYNC_DIR = "src/iri_client/_async"
SYNC_DIR = "src/iri_client/_sync"
OPENAPI_URL = "https://api.iri.nersc.gov/openapi.json"


# The IRI OpenAPI spec does not provide literal values for many of its string
# enums (JobState, TaskStatus, Status, ...). datamodel-code-generator emits them
# as bare `Enum` classes; patch them to `str, Enum` so they compare cleanly
# against the lowercase strings returned by the API.
def _to_str_enum(code: str) -> str:
    pattern = re.compile(r"(.*)\(Enum\)(.*)", re.DOTALL)

    while pattern.match(code):
        code = re.sub(pattern, r"\1(str, Enum)\2", code)

    return code


#
# Generate pydantic models from the IRI OpenAPI spec.
#
@cli.command(name="models")
def models_codegen(
    output: Path = typer.Option(
        SRC / "_models" / "__init__.py",
        dir_okay=False,
        writable=True,
    ),
):
    with output.open("w") as fp:
        fp.write(_from_open_api())

    print(f"wrote {output}")


def _from_open_api() -> str:
    import subprocess

    result = subprocess.run(
        [
            "datamodel-codegen",
            "--url",
            OPENAPI_URL,
            "--input-file-type",
            "openapi",
            "--use-subclass-enum",
            "--use-double-quotes",
            "--output",
            "/tmp/iri_models.py",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    code = Path("/tmp/iri_models.py").read_text()
    code = _to_str_enum(code)
    return code


#
# Generate the synchronous client from the async implementation using unasync.
# Only the files that live in `_async/` are transformed; shared code (models,
# jobs base classes, monitors, utils) is imported as-is.
#
@cli.command(name="unasync")
def run_unasync():
    additional_replacements = {
        "AsyncClient": "Client",
        "AsyncAccount": "Account",
        "AsyncFacility": "Facility",
        "AsyncStatus": "Status",
        "AsyncCompute": "Compute",
        "AsyncFilesystem": "Filesystem",
        "AsyncJob": "Job",
        "AsyncPath": "RemotePath",
        "AsyncTask": "Task",
        "aclose": "close",
        "_ASYNC_SLEEP": "_SLEEP",
    }
    rules = [
        unasync.Rule(
            fromdir=f"/{ASYNC_DIR}/",
            todir=f"/{SYNC_DIR}/",
            additional_replacements=additional_replacements,
        ),
    ]

    filepaths = []
    for p in (Path(__file__).parent.parent / "src" / "iri_client" / "_async").glob(
        "**/*.py"
    ):
        filepaths.append(str(p))

    unasync.unasync_files(filepaths, rules)

    # unasync doesn't touch docstrings, clean them up with a regex pass
    subs = [
        ("Async", ""),
        ("await ", ""),
        ("async ", ""),
    ]

    for path in (
        Path(__file__).parent.parent / "src" / "iri_client" / "_sync"
    ).glob("**/*.py"):
        with path.open() as fp:
            code = fp.read()

        for target, replacement in subs:
            pattern = re.compile(rf"(.*\"\"\".*){target}(.*\"\"\".*)", re.DOTALL)

            modified = False
            while pattern.match(code):
                code = re.sub(pattern, rf"\1{replacement}\2", code)
                modified = True

            if modified:
                with path.open("w") as fp:
                    fp.write(code)

    print("generated _sync/")


if __name__ == "__main__":
    cli()