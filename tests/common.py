"""Shared helpers for the iri_client live test-suite.

Both a synchronous (``Client``) and asynchronous (``AsyncClient``) entry point
exist, so each module of behaviour has a ``Sync``/``Async`` test file pair that
shares ``make_jobspec``.  Live tests talk to the NERSC IRI deployment; the
``authenticated_*`` fixtures skip when no bearer token can be resolved.
"""

from iri_client._models import JobSpec


def make_jobspec(
    name: str,
    test_job_account: str,
    test_job_queue: str,
    test_tmp_dir: str,
    command: str = "/bin/sh",
    args=None,
    duration: int = 60,
) -> JobSpec:
    """A small, fast IRI job spec that should complete cleanly on the queue."""
    if args is None:
        args = ["-c", "echo 'iri-client-test'"]
    return JobSpec(
        name=name,
        executable=command,
        arguments=args,
        directory=test_tmp_dir,
        inherit_environment=False,
        attributes={
            "queue_name": test_job_queue,
            "account": test_job_account,
            "duration": duration,
        },
        resources={"node_count": 1, "processes_per_node": 1},
    )