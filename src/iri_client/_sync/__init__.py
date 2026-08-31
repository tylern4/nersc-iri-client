"""hronous implementation of the IRI client.

The asynchronous modules live here; the synchronous equivalents in
``iri_client._sync`` are generated from them with ``unasync``
(see ``scripts/run.py``).
"""

from .client import Client
from .compute import Compute
from .filesystem import Filesystem
from .jobs import Job
from .paths import RemotePath
from .tasks import Task

__all__ = [
    "Client",
    "Compute",
    "Filesystem",
    "Job",
    "RemotePath",
    "Task",
]