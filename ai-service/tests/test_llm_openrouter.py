"""Offline contract tests for the OpenRouter LLM provider."""

import io
import json
from urllib.error import HTTPError

import pytest

from careercompass.skills import llm


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


@pytest.fixture
def openrouter(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.delenv("CC_MATCH_MODEL", raising=False)
    monkeypatch.setenv("CC_OPENROUTER_SITE_URL", "https://careercompass.duckdns.org")
    return llm.LLMDecider(provider="openrouter", enabled=True)


def test_openrouter_requires_a_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    decider = llm.LLMDecider(provider="openrouter", enabled=True)

    assert not decider.available
    assert "OPENROUTER_API_KEY" in decider.reason_unavailable


def test_openrouter_uses_free_router_and_strict_schema(openrouter, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": '{"value":"ok"}'},
            }],
        })

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    assert openrouter.structured("return a value", schema) == '{"value":"ok"}'
    assert openrouter.model == "openrouter/free"
    assert captured["request"].full_url == llm.OPENROUTER_ENDPOINT
    assert captured["request"].get_header("Authorization") == (
        "Bearer test-openrouter-key"
    )
    assert captured["request"].get_header("Http-referer") == (
        "https://careercompass.duckdns.org"
    )

    body = json.loads(captured["request"].data)
    assert body["provider"] == {
        "data_collection": "deny",
        "require_parameters": True,
    }
    assert body["response_format"] == {
        "type": "json_schema",
        "json_schema": {
            "name": "careercompass_response",
            "strict": True,
            "schema": schema,
        },
    }


def test_openrouter_prose_does_not_require_structured_output(openrouter, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return _Response({
            "choices": [{
                "finish_reason": "stop",
                "message": {"content": "Plain explanation"},
            }],
        })

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)

    assert openrouter.complete("explain") == "Plain explanation"
    assert "response_format" not in captured["body"]
    assert captured["body"]["provider"]["require_parameters"] is False


@pytest.mark.parametrize("finish_reason", ["length", "content_filter", "error"])
def test_openrouter_rejects_incomplete_or_blocked_output(
    openrouter, monkeypatch, finish_reason
):
    monkeypatch.setattr(
        llm,
        "urlopen",
        lambda *_args, **_kwargs: _Response({
            "choices": [{
                "finish_reason": finish_reason,
                "message": {"content": "partial"},
            }],
        }),
    )

    assert openrouter.complete("hello") == ""


def test_openrouter_handles_free_tier_rate_limit(openrouter, monkeypatch, caplog):
    def rate_limited(*_args, **_kwargs):
        raise HTTPError(
            "https://example.invalid",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":"free-model quota"}'),
        )

    monkeypatch.setattr(llm, "urlopen", rate_limited)

    assert openrouter.complete("hello") == ""
    assert "rate limit" in caplog.text.lower()


def test_invalid_privacy_setting_fails_closed(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("CC_OPENROUTER_DATA_COLLECTION", "sometimes")

    decider = llm.LLMDecider(provider="openrouter", enabled=True)

    assert decider.openrouter_data_collection == "deny"
