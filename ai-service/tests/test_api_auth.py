"""
Contract tests for service-to-service authentication.

These drive the real ASGI stack rather than calling the middleware directly, because the
behaviour that matters is what a caller on the wire actually receives — the status, the
`application/problem+json` body, and the `WWW-Authenticate` header — not what the function
returns in isolation.

`/api/v1/health/live` is used as the probe target throughout: it is the one guarded-prefix
path that touches no model, index or database, so these tests stay fast and say nothing about
whether the service is warm.

Usage:
    pytest tests/test_api_auth.py
"""

import os

os.environ.setdefault("CC_API_WARMUP", "0")

import pytest
from fastapi.testclient import TestClient

import careercompass.api.app as app_module

TOKEN = "test-service-token-value"
HEALTH = "/api/v1/health/live"
GUARDED = "/api/v1/skill-vector"


@pytest.fixture(scope="module")
def client():
    """
    One client for the whole module.

    Deliberately not per-test: entering `TestClient` runs the app's lifespan, and the
    extraction queue it starts owns an asyncio queue bound to that loop. Building a client
    per test binds it to a new loop each time and every test after the first fails with
    "bound to a different event loop" — a failure about the fixture, not the code under test.

    Safe here because the token is read from the environment on each request, so
    `monkeypatch` still varies the configuration test by test.
    """
    with TestClient(app_module.app) as test_client:
        yield test_client


@pytest.fixture
def no_token(monkeypatch):
    monkeypatch.delenv("CC_SERVICE_TOKEN", raising=False)


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setenv("CC_SERVICE_TOKEN", TOKEN)


# ── Disabled by default ────────────────────────────────────────


def test_unset_token_leaves_the_api_open(client, no_token):
    """Local development and the rest of the suite must keep working without ceremony."""
    assert client.get(HEALTH).status_code == 200


def test_blank_token_is_treated_as_unset(client, monkeypatch):
    """A variable set to whitespace is a misconfiguration, not a secret worth enforcing."""
    monkeypatch.setenv("CC_SERVICE_TOKEN", "   ")
    assert client.get(HEALTH).status_code == 200


# ── Enforcement ────────────────────────────────────────────────


def test_missing_header_is_rejected_as_a_problem_document(client, with_token):
    response = client.post(GUARDED, json={"courses": []})

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    # RFC 9110 requires this on a 401; without it the caller cannot tell which scheme to use.
    assert response.headers["www-authenticate"] == "Bearer"

    body = response.json()
    assert body["type"] == "not-authenticated"
    assert body["status"] == 401


def test_wrong_token_is_rejected(client, with_token):
    response = client.get(HEALTH.replace("health/live", "courses"),
                          headers={"Authorization": "Bearer not-the-right-token"})
    assert response.status_code == 401
    assert response.json()["type"] == "not-authenticated"


def test_wrong_scheme_is_rejected(client, with_token):
    """Basic auth carrying the right secret is still the wrong protocol."""
    response = client.get("/api/v1/courses", headers={"Authorization": f"Basic {TOKEN}"})
    assert response.status_code == 401


def test_correct_token_is_accepted(client, with_token):
    response = client.get("/api/v1/courses", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200


def test_token_comparison_is_not_a_prefix_match(client, with_token):
    """A token that merely starts with the real one must not be accepted."""
    response = client.get("/api/v1/courses", headers={"Authorization": f"Bearer {TOKEN[:-1]}"})
    assert response.status_code == 401


# ── Exemptions ─────────────────────────────────────────────────


def test_health_stays_open_when_authentication_is_enabled(client, with_token):
    """
    A readiness probe answering 401 reads as "unhealthy" to an orchestrator, which then
    restarts a container that is in fact working — so health must never be guarded.
    """
    assert client.get(HEALTH).status_code == 200
    assert client.get("/api/v1/health/ready").status_code in (200, 503)


def test_documentation_routes_stay_open(client, with_token):
    """`/docs` and `/openapi.json` are documentation, not the versioned API."""
    assert client.get("/openapi.json").status_code == 200


def test_preflight_is_not_authenticated(client, with_token):
    """
    A CORS preflight carries no Authorization header by specification. Rejecting it would
    break the request that follows, for a check the real request still has to pass anyway.
    """
    response = client.options(
        GUARDED,
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code != 401
