"""DataWise LLM Provider Abstraction.

Implements lightweight, dual/multi-provider LLM integration (Gemini, Anthropic, OpenAI,
and local OpenAI-compatible endpoints) with structured JSON generation and strict schema validation.

Per decision.md:
- Deterministic heuristic fallback is always available when no LLM key is configured.
- Only metadata (DataProfile) is provided to LLM providers — never raw dataset rows.
- Structured JSON output is parsed and strictly validated using Pydantic schemas.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, Optional, Type, TypeVar
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _clean_json_markdown(raw_text: str) -> str:
    """Extract raw JSON from possible markdown fences (e.g. ```json ... ```)."""
    text = raw_text.strip()
    # Match markdown code block if present
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


class LLMProvider(ABC):
    """Abstract base class for structured LLM providers."""

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[T] | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate structured JSON conforming to a prompt or schema."""
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the display name of the provider."""
        pass


class GeminiProvider(LLMProvider):
    """Google Gemini LLM provider using direct REST API (zero third-party dependencies)."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash") -> None:
        self.api_key = api_key
        self.model = model

    def get_provider_name(self) -> str:
        return f"Google Gemini ({self.model})"

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[T] | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        
        full_system = (
            system_prompt + "\n\nCRITICAL: You MUST respond ONLY with valid JSON. "
            "Do not include markdown explanation, preamble, or commentary outside the JSON."
        )

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            }
        }
        if full_system:
            payload["systemInstruction"] = {
                "parts": [{"text": full_system}]
            }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                candidates = data.get("candidates", [])
                if not candidates:
                    raise ValueError(f"Gemini returned no candidates: {data}")
                part = candidates[0].get("content", {}).get("parts", [{}])[0]
                text = part.get("text", "{}")
                clean = _clean_json_markdown(text)
                return json.loads(clean)
        except Exception as exc:
            log.warning("GeminiProvider generate_structured failed: %s", exc)
            raise


class AnthropicProvider(LLMProvider):
    """Anthropic Claude LLM provider using direct REST API."""

    def __init__(self, api_key: str, model: str = "claude-3-5-sonnet-20241022") -> None:
        self.api_key = api_key
        self.model = model

    def get_provider_name(self) -> str:
        return f"Anthropic Claude ({self.model})"

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[T] | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = "https://api.anthropic.com/v1/messages"
        
        full_system = (
            system_prompt + "\n\nCRITICAL: You MUST reply with a raw JSON object only. "
            "Never enclose in conversational remarks."
        )

        payload = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": 0.1,
            "system": full_system,
            "messages": [
                {"role": "user", "content": prompt}
            ]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                content_blocks = data.get("content", [])
                text = content_blocks[0].get("text", "{}") if content_blocks else "{}"
                clean = _clean_json_markdown(text)
                return json.loads(clean)
        except Exception as exc:
            log.warning("AnthropicProvider generate_structured failed: %s", exc)
            raise


class OpenAIProvider(LLMProvider):
    """OpenAI / Compatible REST provider (supports OpenAI, Groq, Ollama, vLLM)."""

    def __init__(
        self,
        api_key: str = "sk-none",
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def get_provider_name(self) -> str:
        return f"OpenAI/Compatible ({self.model})"

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[T] | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        
        full_system = (
            system_prompt + "\n\nCRITICAL: Respond ONLY with a valid JSON object matching the requested schema."
        )

        payload: Dict[str, Any] = {
            "model": self.model,
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user", "content": prompt},
            ],
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data.get("choices", [{}])[0]
                text = choice.get("message", {}).get("content", "{}")
                clean = _clean_json_markdown(text)
                return json.loads(clean)
        except Exception as exc:
            log.warning("OpenAIProvider generate_structured failed: %s", exc)
            raise


class MockLLMProvider(LLMProvider):
    """Mock LLM provider for unit testing structured planning without external API keys."""

    def __init__(self, canned_response: Dict[str, Any] | None = None) -> None:
        self.canned_response = canned_response or {}
        self.calls: list[dict] = []

    def get_provider_name(self) -> str:
        return "Mock LLM Provider (Test)"

    def generate_structured(
        self,
        prompt: str,
        system_prompt: str = "",
        schema: Optional[Type[T] | Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt})
        return dict(self.canned_response)


def get_default_llm_provider(
    explicit_key: str | None = None,
    explicit_provider: str | None = None,
) -> LLMProvider | None:
    """Resolve the active LLM provider from explicit arguments or environment variables.

    Priority:
    1. Explicit arguments if passed
    2. GEMINI_API_KEY / GOOGLE_API_KEY
    3. ANTHROPIC_API_KEY
    4. OPENAI_API_KEY or OPENAI_BASE_URL (for local Ollama/vLLM)
    5. None (falls back to deterministic heuristic planning)
    """
    gemini_key = explicit_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if gemini_key and (not explicit_provider or explicit_provider.lower() == "gemini"):
        return GeminiProvider(api_key=gemini_key)

    anthropic_key = explicit_key or os.environ.get("ANTHROPIC_API_KEY")
    if anthropic_key and (not explicit_provider or explicit_provider.lower() == "anthropic"):
        return AnthropicProvider(api_key=anthropic_key)

    openai_key = explicit_key or os.environ.get("OPENAI_API_KEY")
    local_url = os.environ.get("OPENAI_BASE_URL") or os.environ.get("LOCAL_LLM_URL")
    if (openai_key or local_url) and (not explicit_provider or explicit_provider.lower() == "openai"):
        return OpenAIProvider(
            api_key=openai_key or "sk-local",
            base_url=local_url or "https://api.openai.com/v1",
        )

    return None
