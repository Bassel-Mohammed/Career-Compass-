"""
CareerCompass — Constrained LLM Selection

The last stage of the RAG taxonomy pipeline, and the only one that calls a
generative model. It runs only for ambiguous terms: retrieval and reranking
have already reduced the taxonomy to a short list, but cannot choose a clear
winner.

Four providers are supported:

    ollama      local, open-weight models through Ollama; defaults to
                qwen3:8b and requires no Python SDK or API key
    anthropic   hosted Claude models through the optional anthropic SDK
    gemini      hosted Google models over the REST API, standard library only,
                authenticated with GEMINI_API_KEY
    openrouter  hosted free/paid models through OpenRouter's OpenAI-compatible
                REST API, authenticated with OPENROUTER_API_KEY

`gemini` exists for deployments with no GPU and too little CPU to run a local
model inside a request budget — a small free VM being the usual case. It uses
Gemini's JSON Schema response mode and `decide` still re-validates the returned
id against the shortlist before the result can reach the matcher.

`openrouter` serves the same constrained and prose operations without an SDK.
The default `openrouter/free` router chooses only zero-price models. Structured
calls require providers to honor JSON Schema, and every request denies provider
data collection by default. These privacy and routing constraints fail closed
when no compatible free endpoint is available.

The model never writes an unrestricted identifier. It receives a JSON schema
whose canonical_id is an enum containing only the retrieved IDs plus
"no_match". The selected ID is validated against that shortlist again before
it can reach the matcher.

Enable the stage with CC_MATCH_LLM=1 or the CLI's --llm option. Without an
available provider, ambiguous terms safely remain in manual review.
"""

import json
import logging
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger("careercompass.llm")

DEFAULT_PROVIDER = "ollama"
DEFAULT_OLLAMA_MODEL = "qwen3:8b"
DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_OPENROUTER_MODEL = "openrouter/free"
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TIMEOUT = 300.0

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
# Hosted call over the public internet, so this is a network timeout rather than
# an inference budget. Kept well under the backend's 90s quiz deadline so a slow
# response fails here with a logged reason instead of timing out upstream.
DEFAULT_GEMINI_TIMEOUT = 60.0
OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_OPENROUTER_TIMEOUT = 60.0

VALID_PROVIDERS = ("ollama", "anthropic", "gemini", "openrouter")
NO_MATCH = "no_match"

# How long Ollama should hold the model in memory between calls.
DEFAULT_KEEP_ALIVE = "30m"

# A ceiling on one match decision, not a budget to aim at. `_ollama_text` treats
# a length stop as a failure and sends the term to review, so a tight cap would
# silently change decisions — which is exactly what this must not do. Measured
# across 447 real decisions the `reason` field runs mean 199 / max 325
# characters (~81 tokens), so this is over 3x the worst case observed and can
# only ever catch a runaway generation.
DECISION_MAX_TOKENS = 256

# The two documents the pipeline reads. The rules for resolving a phrase
# are identical; only what the phrase was drawn from differs, and saying
# so plainly is worth more than it costs — "Java" in a syllabus week and
# "Java" in a requirements bullet want the same taxonomy entry, but the
# surrounding evidence reads very differently, and the model does better
# when it knows which it is looking at.
DOMAINS = {
    "syllabus": {
        "corpus": "course-syllabus skill phrases",
        "source": "one phrase extracted from a syllabus, the syllabus text it came from",
    },
    "job_posting": {
        "corpus": "job-posting skill phrases",
        "source": ("one phrase extracted from job postings, the posting lines it was "
                   "drawn from"),
    },
}
DEFAULT_DOMAIN = "syllabus"

SYSTEM_PROMPT = """You resolve {corpus} onto a fixed skill taxonomy for CareerCompass, a system that compares what a university course teaches against what job postings ask for.

You are given {source}, and a shortlist of taxonomy entries retrieved for it. Select the entry that names the same skill.

Rules:
- Choose an entry only when it means the same skill as the phrase, not merely a related or broader topic. "Kinematics" is not "Dynamics"; "ROS 2 node development" is not "software engineering".
- A different wording for the same skill is a match ("HRI" and "human-robot interaction"; "GazeboSim Harmonic" and "Gazebo simulator").
- An entry that is one level broader is acceptable only when no more specific entry is shortlisted and the phrase clearly falls inside it.
- Return no_match when nothing on the shortlist fits. An honest no_match is more useful than a wrong id: unmatched terms go to human review, wrong ids do not.
- confidence is your probability that the selected entry is correct, from 0.0 to 1.0. Report it honestly; a low confidence routes the term to review.
- reason is one sentence naming the evidence you used."""


def system_prompt(domain: str = DEFAULT_DOMAIN) -> str:
    """The system prompt phrased for the document the term came from."""
    return SYSTEM_PROMPT.format(**DOMAINS.get(domain, DOMAINS[DEFAULT_DOMAIN]))


def _enabled(value) -> bool:
    """Interpret the environment's common true values."""
    if isinstance(value, bool):
        return value
    return str(value or "").lower() in ("1", "true", "yes", "on")


def _timeout(value, default: float = DEFAULT_OLLAMA_TIMEOUT) -> float:
    """Parse a provider timeout without letting a bad env value break startup."""
    try:
        return max(1.0, float(value))
    except (TypeError, ValueError):
        return default


def _candidate_block(candidates: list) -> str:
    """Render the shortlist the model must choose from."""
    lines = []
    for position, (skill, score) in enumerate(candidates, start=1):
        parts = [f"{position}. id: {skill['id']}", f"   label: {skill['label']}"]
        if skill.get("aliases"):
            parts.append(f"   also called: {', '.join(skill['aliases'][:8])}")
        if skill.get("description"):
            parts.append(f"   description: {skill['description'][:280]}")
        parts.append(f"   source: {skill['source']} | retrieval score: {score:.3f}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


class LLMDecider:
    """Selects one retrieved taxonomy ID through a configured LLM provider."""

    def __init__(self, model: str = "", provider: str = "", enabled=None,
                 ollama_url: str = "", client=None, domain: str = DEFAULT_DOMAIN):
        self.provider = (
            provider or os.getenv("CC_MATCH_LLM_PROVIDER", DEFAULT_PROVIDER)
        ).strip().lower()
        default_model = {
            "anthropic": DEFAULT_ANTHROPIC_MODEL,
            "gemini": DEFAULT_GEMINI_MODEL,
            "openrouter": DEFAULT_OPENROUTER_MODEL,
        }.get(self.provider, DEFAULT_OLLAMA_MODEL)
        self.model = model or os.getenv("CC_MATCH_MODEL", default_model)
        self.ollama_url = (
            ollama_url or os.getenv("CC_OLLAMA_URL", DEFAULT_OLLAMA_URL)
        ).rstrip("/")
        self.ollama_timeout = _timeout(
            os.getenv("CC_OLLAMA_TIMEOUT", DEFAULT_OLLAMA_TIMEOUT)
        )
        self.keep_alive = os.getenv("CC_OLLAMA_KEEP_ALIVE", DEFAULT_KEEP_ALIVE)
        # GOOGLE_API_KEY is accepted too: it is what Google's own tooling sets,
        # and a deployment that already exports it should not need a second copy
        # under a different name.
        self.gemini_api_key = (
            os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
        ).strip()
        self.gemini_timeout = _timeout(
            os.getenv("CC_GEMINI_TIMEOUT", DEFAULT_GEMINI_TIMEOUT),
            DEFAULT_GEMINI_TIMEOUT,
        )
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.openrouter_timeout = _timeout(
            os.getenv("CC_OPENROUTER_TIMEOUT", DEFAULT_OPENROUTER_TIMEOUT),
            DEFAULT_OPENROUTER_TIMEOUT,
        )
        self.openrouter_site_url = os.getenv("CC_OPENROUTER_SITE_URL", "").strip()
        data_collection = os.getenv("CC_OPENROUTER_DATA_COLLECTION", "deny").strip().lower()
        self.openrouter_data_collection = (
            data_collection if data_collection in ("allow", "deny") else "deny"
        )
        self.domain = domain if domain in DOMAINS else DEFAULT_DOMAIN
        self.system_prompt = system_prompt(self.domain)
        self.enabled = _enabled(os.getenv("CC_MATCH_LLM")) if enabled is None else bool(enabled)
        self.reason_unavailable = ""
        self._client = client
        self._ollama_ready = False
        self._gemini_ready = False
        self._openrouter_ready = False

        if not self.enabled:
            self.reason_unavailable = "LLM stage disabled (set CC_MATCH_LLM=1 or pass --llm)"
            return

        if self.provider not in VALID_PROVIDERS:
            self.reason_unavailable = (
                f"unknown LLM provider {self.provider!r}; "
                f"choose one of {', '.join(VALID_PROVIDERS)}"
            )
            return

        if self.provider == "ollama":
            self._configure_ollama()
        elif self.provider == "gemini":
            self._configure_gemini()
        elif self.provider == "openrouter":
            self._configure_openrouter()
        else:
            self._configure_anthropic()

    @property
    def available(self) -> bool:
        """Whether the configured provider can currently accept a decision."""
        if not self.enabled:
            return False
        if self.provider == "ollama":
            return self._ollama_ready
        if self.provider == "gemini":
            return self._gemini_ready
        if self.provider == "openrouter":
            return self._openrouter_ready
        return self._client is not None

    @property
    def display_name(self) -> str:
        """Provider and model name for CLI reports."""
        return f"{self.provider}:{self.model}"

    # ── Provider setup ─────────────────────────────────────────
    def _configure_ollama(self) -> None:
        """Check that Ollama is reachable and the requested model is installed."""
        try:
            payload = self._ollama_request("/api/tags", timeout=min(5.0, self.ollama_timeout))
        except (OSError, ValueError) as exc:
            self.reason_unavailable = f"Ollama is unavailable at {self.ollama_url}: {exc}"
            return

        installed = {
            value
            for item in payload.get("models", [])
            for value in (item.get("name"), item.get("model"))
            if value
        }
        if self.model not in installed:
            self.reason_unavailable = (
                f"Ollama model {self.model!r} is not installed "
                f"(run `ollama pull {self.model}`)"
            )
            return
        self._ollama_ready = True

    def _configure_gemini(self) -> None:
        """
        Check that a key is present. Deliberately no network call.

        A reachability probe here would add latency to every process start and
        turn a transient Google outage into a service that reports itself
        permanently unavailable. A bad key instead surfaces on first use, is
        logged with Google's own message, and sends that one term to review.
        """
        if not self.gemini_api_key:
            self.reason_unavailable = (
                "no Gemini credentials: set GEMINI_API_KEY (or GOOGLE_API_KEY)"
            )
            return
        self._gemini_ready = True

    def _configure_openrouter(self) -> None:
        """Mark OpenRouter ready when a bearer key is configured."""
        if not self.openrouter_api_key:
            self.reason_unavailable = (
                "no OpenRouter credentials: set OPENROUTER_API_KEY"
            )
            return
        self._openrouter_ready = True

    def _configure_anthropic(self) -> None:
        """Create the optional Anthropic client."""
        if self._client is not None:
            return
        try:
            import anthropic
        except ImportError:
            self.reason_unavailable = (
                "anthropic SDK not installed (install the project with the llm extra)"
            )
            return

        try:
            self._client = anthropic.Anthropic()
        except Exception as exc:  # pragma: no cover - depends on environment
            self.reason_unavailable = f"no Anthropic credentials: {exc}"
            self._client = None

    # ── Provider requests ──────────────────────────────────────
    def _ollama_request(self, path: str, payload: dict = None, timeout: float = None) -> dict:
        """Call one Ollama JSON endpoint using only the Python standard library."""
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.ollama_url}{path}",
            data=data,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urlopen(request, timeout=timeout or self.ollama_timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise OSError(f"HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise OSError(str(exc.reason if isinstance(exc, URLError) else exc)) from exc
        except json.JSONDecodeError as exc:
            raise ValueError("Ollama returned invalid JSON") from exc

    def _ollama_text(self, prompt: str, schema: dict, max_tokens: int = 0) -> str:
        """Generate one schema-constrained local response."""
        options = {"temperature": 0}
        if max_tokens:
            options["num_predict"] = max_tokens
        try:
            response = self._ollama_request("/api/chat", {
                "model": self.model,
                "stream": False,
                "think": False,
                "format": schema,
                # Hold the model in memory between calls. Unset, Ollama unloads
                # it after its own default idle window, and the next call pays
                # the reload: measured 9.7 s against a 2.4 s steady-state call.
                # A batch run of hundreds of terms should never see that twice.
                "keep_alive": self.keep_alive,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "options": options,
            })
        except (OSError, ValueError) as exc:  # pragma: no cover - service dependent
            logger.warning("Ollama selection failed: %s", exc)
            return ""

        if response.get("done_reason") in ("length", "max_tokens"):
            logger.warning("Ollama response was truncated; sending term to review")
            return ""
        return str((response.get("message") or {}).get("content") or "")

    def structured(self, prompt: str, schema: dict) -> str:
        """
        Generate one schema-constrained response, for callers outside matching.

        `decide` wraps this with a taxonomy shortlist and validates the id it
        returns. Quiz generation needs the same structural guarantee — exactly
        four options, a valid answer index — without any of the taxonomy
        machinery, so the transport is exposed rather than duplicated.

        Returns an empty string when the model is unavailable or errors; the
        caller decides whether that is fatal.
        """
        if not self.available:
            return ""
        if self.provider == "ollama":
            return self._ollama_text(prompt, schema)
        if self.provider == "gemini":
            return self._gemini_text(prompt, schema)
        if self.provider == "openrouter":
            return self._openrouter_text(prompt, schema)
        return self._anthropic_text(prompt, schema)

    def complete(self, prompt: str, max_tokens: int = 400) -> str:
        """
        Generate free prose for a prompt, with no schema and no parsing.

        `decide` is the constrained path: its output is a taxonomy id that is
        validated against the shortlist it was given, because a model must
        never be able to invent an identifier. This is the opposite case —
        the M3 narrative, where the numbers are already final and the model is
        only asked to describe them. Nothing here is parsed back into a value,
        so there is nothing to constrain.

        Returns an empty string when the model is unavailable or errors: the
        caller's output is complete without prose.
        """
        if not self.available:
            return ""

        if self.provider == "ollama":
            try:
                response = self._ollama_request("/api/chat", {
                    "model": self.model,
                    "stream": False,
                    "think": False,
                    "messages": [{"role": "user", "content": prompt}],
                    # Warmer than `decide`, which must be reproducible. Prose
                    # at temperature 0 reads like a form letter.
                    "options": {"temperature": 0.4, "num_predict": max_tokens},
                })
            except (OSError, ValueError) as exc:  # pragma: no cover
                logger.warning("Ollama completion failed: %s", exc)
                return ""
            return str((response.get("message") or {}).get("content") or "").strip()

        if self.provider == "gemini":
            # Warmer than `decide`, for the same reason the Ollama branch is.
            return self._gemini_text(
                prompt, schema=None, max_tokens=max_tokens, temperature=0.4
            )

        if self.provider == "openrouter":
            return self._openrouter_text(
                prompt, schema=None, max_tokens=max_tokens, temperature=0.4
            )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(
                block.text for block in message.content
                if getattr(block, "type", "") == "text"
            ).strip()
        except Exception as exc:  # noqa: BLE001 - pragma: no cover
            logger.warning("Anthropic completion failed: %s", exc)
            return ""

    def _gemini_text(self, prompt: str, schema: dict = None,
                     max_tokens: int = 0, temperature: float | None = None) -> str:
        """
        One Gemini REST call, standard library only — no SDK, so the image stays
        the same size and the deployment gains no new dependency.

        The schemas generated by this code use only the JSON Schema keywords
        supported by Gemini. The model is constrained in transport and the
        caller validates security-sensitive values again after parsing.
        """
        instructions = self.system_prompt
        # These tasks need instruction following, not deep reasoning. Minimal
        # thinking reduces free-tier token use and keeps quiz requests inside
        # the backend's deadline. Temperature is retained only for prose calls.
        config = {"thinkingConfig": {"thinkingLevel": "minimal"}}
        if temperature is not None:
            config["temperature"] = temperature
        if max_tokens:
            config["maxOutputTokens"] = max_tokens
        if schema is not None:
            config["responseMimeType"] = "application/json"
            config["responseJsonSchema"] = schema
            # Structured calls can otherwise inherit the model's very large
            # default output limit. This matches the Anthropic provider.
            config.setdefault("maxOutputTokens", 4096)
            instructions += "\n\nReturn only the JSON value required by the response schema."

        body = json.dumps({
            "systemInstruction": {"parts": [{"text": instructions}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": config,
        }).encode("utf-8")

        # The key travels in a header, not the query string: a URL carrying a
        # credential ends up in proxy logs and crash reports.
        request = Request(
            f"{GEMINI_ENDPOINT}/{self.model}:generateContent",
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.gemini_api_key,
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.gemini_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            # 429 is the free tier's rate limit and is expected under load, so it
            # is named rather than buried in a generic failure.
            if exc.code == 429:
                logger.warning("Gemini rate limit reached: %s", detail)
            else:
                logger.warning("Gemini request failed (%s): %s", exc.code, detail)
            return ""
        except (URLError, OSError, ValueError) as exc:
            logger.warning("Gemini request failed: %s", exc)
            return ""

        candidates = payload.get("candidates") or []
        if not candidates:
            # A blocked prompt returns no candidates and explains itself here.
            logger.warning("Gemini returned no candidates: %s",
                           str(payload.get("promptFeedback") or payload)[:200])
            return ""

        candidate = candidates[0]
        finish_reason = candidate.get("finishReason", "")
        if finish_reason and finish_reason != "STOP":
            logger.warning(
                "Gemini response ended with %s; ignoring incomplete output",
                finish_reason,
            )
            return ""

        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(part.get("text", "") for part in parts).strip()
        if not text:
            logger.warning("Gemini returned a candidate with no text")
            return ""

        # Models still fence JSON occasionally despite responseMimeType.
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            if text.endswith("```"):
                text = text[: text.rfind("```")]
        return text.strip()

    def _openrouter_text(self, prompt: str, schema: dict = None,
                         max_tokens: int = 0, temperature: float = 0.0) -> str:
        """Call OpenRouter's OpenAI-compatible chat-completions endpoint."""
        body = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
            # Deny providers that store/train on requests by default. This can
            # reduce free-model availability, which is preferable to silently
            # weakening the privacy policy.
            "provider": {
                "data_collection": self.openrouter_data_collection,
                "require_parameters": schema is not None,
            },
            "temperature": temperature,
            "max_tokens": max_tokens or (4096 if schema is not None else 400),
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "careercompass_response",
                    "strict": True,
                    "schema": schema,
                },
            }

        headers = {
            "Authorization": f"Bearer {self.openrouter_api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Title": "CareerCompass",
        }
        if self.openrouter_site_url:
            headers["HTTP-Referer"] = self.openrouter_site_url

        request = Request(
            OPENROUTER_ENDPOINT,
            data=json.dumps(body).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.openrouter_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            if exc.code == 429:
                logger.warning("OpenRouter free-model rate limit reached: %s", detail)
            else:
                logger.warning("OpenRouter request failed (%s): %s", exc.code, detail)
            return ""
        except (URLError, OSError, ValueError) as exc:
            logger.warning("OpenRouter request failed: %s", exc)
            return ""

        if payload.get("error"):
            logger.warning("OpenRouter returned an error: %s", str(payload["error"])[:300])
            return ""
        choices = payload.get("choices") or []
        if not choices:
            logger.warning("OpenRouter returned no completion choices")
            return ""

        choice = choices[0]
        finish_reason = choice.get("finish_reason", "")
        if finish_reason and finish_reason != "stop":
            logger.warning(
                "OpenRouter response ended with %s; ignoring incomplete output",
                finish_reason,
            )
            return ""

        content = (choice.get("message") or {}).get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
        text = content.strip() if isinstance(content, str) else ""
        if not text:
            logger.warning("OpenRouter returned a completion with no text")
            return ""
        return text

    def _anthropic_text(self, prompt: str, schema: dict) -> str:
        """Generate one schema-constrained Anthropic response."""
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=self.system_prompt,
                output_config={
                    "effort": "low",
                    "format": {"type": "json_schema", "schema": schema},
                },
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:  # pragma: no cover - network dependent
            logger.warning("Anthropic selection failed: %s", exc)
            return ""

        if getattr(response, "stop_reason", "") == "refusal":
            logger.warning("Anthropic declined the taxonomy decision")
            return ""
        if getattr(response, "stop_reason", "") == "max_tokens":
            logger.warning("Anthropic response was truncated; sending term to review")
            return ""
        return next((block.text for block in response.content if block.type == "text"), "")

    # ── Decision ───────────────────────────────────────────────
    def decide(self, term: str, evidence: str, candidates: list):
        """
        Ask the configured model to pick a shortlisted candidate or no_match.

        The returned canonical_id is always validated against the supplied
        candidates, regardless of the provider's structured-output guarantee.
        """
        if not self.available or not candidates:
            return None

        allowed = [skill["id"] for skill, _ in candidates]
        schema = {
            "type": "object",
            "properties": {
                "canonical_id": {
                    "type": "string",
                    "enum": allowed + [NO_MATCH],
                    "description": "The matching taxonomy ID, or no_match.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Probability that the selection is correct.",
                },
                "reason": {
                    "type": "string",
                    "description": "One sentence justifying the selection.",
                },
            },
            "required": ["canonical_id", "confidence", "reason"],
            "additionalProperties": False,
        }
        prompt = (
            f"Extracted phrase: {term}\n"
            f"Syllabus evidence: {evidence or '(none)'}\n\n"
            f"Taxonomy candidates:\n\n{_candidate_block(candidates)}\n\n"
            "Which candidate names the same skill as the extracted phrase? "
            "Return only the JSON object required by the schema."
        )

        text = (
            self._ollama_text(prompt, schema, max_tokens=DECISION_MAX_TOKENS)
            if self.provider == "ollama"
            else self._gemini_text(prompt, schema, max_tokens=DECISION_MAX_TOKENS)
            if self.provider == "gemini"
            else self._openrouter_text(prompt, schema, max_tokens=DECISION_MAX_TOKENS)
            if self.provider == "openrouter"
            else self._anthropic_text(prompt, schema)
        )
        try:
            choice = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            logger.warning("%s returned unparsable output for %r: %s",
                           self.provider, term, str(text)[:200])
            return None

        canonical_id = choice.get("canonical_id")
        if canonical_id != NO_MATCH and canonical_id not in allowed:
            logger.warning("%s returned an ID outside the shortlist for %r: %s",
                           self.provider, term, canonical_id)
            return None

        confidence = choice.get("confidence", 0.0)
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "canonical_id": canonical_id,
            "confidence": round(confidence, 3),
            "reason": str(choice.get("reason", ""))[:300],
        }
