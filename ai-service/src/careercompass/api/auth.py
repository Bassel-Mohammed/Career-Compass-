"""
Service-to-service authentication.

This API is called by the Java backend, never by a browser. What crosses the boundary is a
*service* identity, not a student's — there is no per-user login here and no session state.
A single shared bearer token is therefore the right shape (ADR-004), and the internal
contract declares it as the `serviceToken` security scheme.

Until this module existed the contract said one thing and the service did another: Java sent
`Authorization: Bearer …` on every call and the API ignored it entirely, so anything that
could reach the port could read parsed transcripts and quiz answer keys.

Enforcement is opt-in through `CC_SERVICE_TOKEN`:

* **unset or blank** — authentication is off, and a warning says so at startup. This keeps
  local development and the test suite working without ceremony, matching the contract's
  note that a blank token is tolerated on loopback.
* **set** — every `/api/v1/*` request must carry that exact token, health excepted.

The default is off rather than on because a deployment that forgets to *set* the variable
fails loudly on its first call, whereas a default token would be a shared secret published
in the repository — the same trap as a checked-in JWT signing key.
"""

import logging
import os
import secrets

from starlette.requests import Request
from starlette.responses import JSONResponse

from careercompass.api.errors import Problem

logger = logging.getLogger("careercompass.api.auth")

#: Paths served without a token. Health must stay open so an orchestrator can probe a
#: container that has not been given its secret yet — a readiness probe answering 401 reads
#: as "unhealthy" and gets the container restarted forever.
PUBLIC_PATH_PREFIXES = ("/api/v1/health",)

#: Only the versioned API is guarded. `/`, `/docs` and `/openapi.json` are documentation.
PROTECTED_PATH_PREFIX = "/api/v1"

_BEARER = "bearer"


def configured_token() -> str:
    """The expected token, or an empty string when authentication is disabled."""
    return (os.getenv("CC_SERVICE_TOKEN") or "").strip()


def _requires_token(path: str) -> bool:
    if not path.startswith(PROTECTED_PATH_PREFIX):
        return False
    return not path.startswith(PUBLIC_PATH_PREFIXES)


def _presented_token(header: str) -> str:
    """
    Pull the credential out of an `Authorization` header.

    Returns an empty string for anything that is not a well-formed bearer header, which the
    caller then treats as "no token" — an unparseable header and a missing one are the same
    failure to the client, and distinguishing them in the response would only help someone
    probing the format.
    """
    if not header:
        return ""
    scheme, _, credential = header.partition(" ")
    if scheme.strip().lower() != _BEARER:
        return ""
    return credential.strip()


def _problem_response(detail: str) -> JSONResponse:
    """
    Render a 401 in the same RFC 9457 shape as every other error.

    Built directly rather than raised: an exception thrown from middleware unwinds outside
    the application, so FastAPI's registered `Problem` handler never sees it and the caller
    gets a bare 500 instead of a problem document.
    """
    problem = Problem.not_authenticated(detail)
    return JSONResponse(
        status_code=problem.status,
        content=problem.to_dict(),
        headers=problem.headers,
        media_type="application/problem+json",
    )


async def service_token_middleware(request: Request, call_next):
    """Reject `/api/v1/*` requests that do not carry the configured service token."""
    expected = configured_token()

    # OPTIONS is never authenticated: a CORS preflight carries no Authorization header by
    # specification, so rejecting it would break the actual request that follows.
    if request.method == "OPTIONS":
        return await call_next(request)

    if not expected or not _requires_token(request.url.path):
        return await call_next(request)

    presented = _presented_token(request.headers.get("authorization", ""))

    if not presented:
        return _problem_response(
            "This endpoint requires a service token. Send it as "
            "'Authorization: Bearer <token>'."
        )

    # Constant-time: a plain `==` leaks the shared secret one character at a time to anyone
    # who can measure the response.
    if not secrets.compare_digest(presented, expected):
        # Deliberately not logged with the presented value — a near-miss token in a log file
        # is as good as the token itself.
        logger.warning("Rejected %s: service token did not match", request.url.path)
        return _problem_response("The service token presented is not valid.")

    return await call_next(request)


def log_auth_state() -> None:
    """Say at startup whether the API is guarded, so an unguarded deployment is visible."""
    if configured_token():
        logger.info("Service authentication enabled for %s/*", PROTECTED_PATH_PREFIX)
    else:
        logger.warning(
            "CC_SERVICE_TOKEN is not set — %s/* is unauthenticated. Acceptable on loopback "
            "for development; set it before exposing this service to a network.",
            PROTECTED_PATH_PREFIX,
        )
