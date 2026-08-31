class IriError(Exception):
    """
    Base exception for errors raised by the iri_client package.

    Mirrors ``SfApiError`` from ``sfapi_client``: a simple carrier for a
    human-readable message.
    """

    def __init__(self, message):
        self.message = message

    def __str__(self):
        return str(self.message)


class ClientKeyError(IriError):
    """
    Raised when a bearer token cannot be resolved from any source.

    Kept under the same name as ``sfapi_client.ClientKeyError`` so callers
    migrating from the Superfacility client do not need to change their error
    handling for missing credentials.
    """

    def __init__(self, message):
        super().__init__(message)


class AuthError(IriError):
    """
    Raised when an authenticated API call is attempted without a bearer token.

    IRI (unlike the Superfacility API) has no token endpoint, so the client
    cannot refresh or mint a token by itself. A token must be provisioned
    out-of-band and supplied via the ``IRI_API_TOKEN`` environment variable,
    ``~/.ssh/nersc-token``, or the ``access_token`` constructor argument.
    """

    def __init__(self, message):
        super().__init__(message)


class ResourceLookupError(IriError):
    """
    Raised when a resource (compute / filesystem) cannot be unambiguously
    resolved from a name, group, or id.
    """

    def __init__(self, message):
        super().__init__(message)