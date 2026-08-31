# nersc-iri-client

Python client for the NERSC IRI API (<https://api.iri.nersc.gov>).

The package is modelled on NERSC's Superfacility API client
([sfapi_client](https://github.com/NERSC/sfapi_client)) and applies its design
principles (async/sync duality via unasync, pydantic models generated from the
OpenAPI spec, resource based client, retry with tenacity, awaitable job and task
objects) to the newer IRI API.

See [CONVERSION.md](CONVERSION.md) for a detailed description of how the design
maps between the two APIs and the rationale for every change.

## Installation

```shell
uv sync --extra dev
```

## Examples

```python
from iri_client import Client, ComputeResourceName, FilesystemResourceName

with Client() as client:
    # Discover and bind the Perlmutter compute resource (an alias for jobs)
    perlmutter = client.compute(ComputeResourceName.perlmutter)

    # Submit a short job on the debug queue
    job = perlmutter.submit_job({
        "name": "hello",
        "executable": "/bin/echo",
        "arguments": ["hello iri"],
        "directory": "/pscratch/sd/t/elvis/tmp",
        "stdout_path": "/pscratch/sd/t/elvis/tmp/hello.out",
        "stderr_path": "/pscratch/sd/t/elvis/tmp/hello.err",
        "attributes": {"queue_name": "debug", "account": "m3792", "duration": 60},
        "resources": {"node_count": 1, "processes_per_node": 1},
    })
    job.complete(timeout=300)

    # List files with the filesystem resource
    fs = client.filesystem(FilesystemResourceName.scratch)
    paths = fs.ls("/pscratch/sd/t/elvis/tmp")
```