"""Offline contract tests for the Gemini LLM provider."""

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
def gemini(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("CC_MATCH_MODEL", raising=False)
    return llm.LLMDecider(provider="gemini", enabled=True)


def test_gemini_requires_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

    decider = llm.LLMDecider(provider="gemini", enabled=True)

    assert not decider.available
    assert "GEMINI_API_KEY" in decider.reason_unavailable


def test_gemini_uses_current_model_and_schema(gemini, monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["request"] = request
        captured["timeout"] = timeout
        return _Response({
            "candidates": [{
                "finishReason": "STOP",
                "content": {"parts": [{"text": '{"value":"ok"}'}]},
            }],
        })

    monkeypatch.setattr(llm, "urlopen", fake_urlopen)
    schema = {
        "type": "object",
        "properties": {"value": {"type": "string"}},
        "required": ["value"],
        "additionalProperties": False,
    }

    assert gemini.structured("return a value", schema) == '{"value":"ok"}'
    assert gemini.model == "gemini-3.6-flash"
    assert captured["request"].full_url.endswith(
        "/gemini-3.6-flash:generateContent"
    )
    assert captured["request"].get_header("X-goog-api-key") == "test-key"

    body = json.loads(captured["request"].data)
    config = body["generationConfig"]
    assert config["responseMimeType"] == "application/json"
    assert config["responseJsonSchema"] == schema
    assert config["thinkingConfig"] == {"thinkingLevel": "minimal"}
    assert config["maxOutputTokens"] == 4096


@pytest.mark.parametrize("finish_reason", ["MAX_TOKENS", "SAFETY", "RECITATION"])
def test_gemini_rejects_incomplete_or_blocked_output(gemini, monkeypatch, finish_reason):
    monkeypatch.setattr(
        llm,
        "urlopen",
        lambda *_args, **_kwargs: _Response({
            "candidates": [{
                "finishReason": finish_reason,
                "content": {"parts": [{"text": '{"unsafe":"partial"}'}]},
            }],
        }),
    )

    assert gemini.complete("hello") == ""


def test_gemini_handles_rate_limit(gemini, monkeypatch, caplog):
    def rate_limited(*_args, **_kwargs):
        raise HTTPError(
            "https://example.invalid",
            429,
            "Too Many Requests",
            {},
            io.BytesIO(b'{"error":"quota"}'),
        )

    monkeypatch.setattr(llm, "urlopen", rate_limited)

    assert gemini.complete("hello") == ""
    assert "rate limit" in caplog.text.lower()


def test_invalid_gemini_timeout_uses_gemini_default(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CC_GEMINI_TIMEOUT", "not-a-number")

    decider = llm.LLMDecider(provider="gemini", enabled=True)

    assert decider.gemini_timeout == llm.DEFAULT_GEMINI_TIMEOUT
