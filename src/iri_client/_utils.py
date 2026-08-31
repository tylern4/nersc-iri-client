import asyncio
import time
from functools import wraps
from typing import Callable

from ._models import Status

# The only legitimate difference between the asynchronous and the synchronous
# implementations of this package. `unasync` rewrites `_ASYNC_SLEEP` to
# `_SLEEP` when generating the sync interface (see scripts/run.py), keeping the
# two in lock-step.
_SLEEP = time.sleep
_ASYNC_SLEEP = asyncio.sleep


def check_auth(method: Callable):
    """
    Guard an API method that requires a bearer token.

    Keeps the sfapi_client convention of allowing public read-only endpoints
    (facility, status, resource discovery) to work with an
    unauthenticated client while every privileged operation fails fast with a
    descriptive error message.
    """

    @wraps(method)
    def wrapper(self, *args, **kwargs):
        if hasattr(self, "client"):
            _client = self.client
        else:
            _client = self

        _client._require_token()

        # Optionally refuse obviously unusable resources: the IRI API carries
        # a `current_status` field on every Resource, so guard against acting
        # on a resource that is marked down.
        if hasattr(_client, "current_status") and _client.current_status in [
            Status.down
        ]:
            from .exceptions import IriError

            raise IriError(
                f"Resource {getattr(self, 'name', '?')} is currently down"
            )
        return method(self, *args, **kwargs)

    return wrapper