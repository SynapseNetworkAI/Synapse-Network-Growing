"""LLM provider adapter — supports OpenAI, Anthropic Claude, and GitHub Copilot.

Each provider implements the same interface:
    call(system, user, model, temperature, timeout) → (text, tokens)

Configuration is loaded from .env via server.config.

Usage:
    provider = get_provider()          # uses LLM_PROVIDER from config
    text, tokens = provider.call(...)
"""
import abc
import logging

import httpx

from server import config
from server.services.copilot_auth import CopilotAuthService

logger = logging.getLogger("ops-dashboard.llm_adapter")

PERSONAL_ACCESS_TOKEN_PREFIXES = ("github_pat_", "ghp_")
JSON_CONTENT_TYPE = "application/json"


class LLMProvider(abc.ABC):
    """Abstract base for LLM providers."""

    name: str

    @abc.abstractmethod
    def call(
        self,
        system: str,
        user: str,
        model: str,
        temperature: float,
        timeout: int,
    ) -> tuple[str, int]:
        """Send a chat completion request. Returns (response_text, total_tokens)."""


class OpenAIProvider(LLMProvider):
    """OpenAI and any OpenAI-compatible endpoint (e.g. vLLM, LiteLLM proxy)."""

    name = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = config.OPENAI_API_KEY if api_key is None else api_key
        self.base_url = (config.LLM_BASE_URL if base_url is None else base_url).rstrip("/")

    def call(self, system: str, user: str, model: str, temperature: float, timeout: int) -> tuple[str, int]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set. Configure the environment variable to enable LLM execution.")

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": JSON_CONTENT_TYPE,
            },
            timeout=timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return text, tokens


class ClaudeProvider(LLMProvider):
    """Anthropic Claude Messages API."""

    name = "claude"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = config.ANTHROPIC_API_KEY if api_key is None else api_key
        self.base_url = (config.ANTHROPIC_BASE_URL if base_url is None else base_url).rstrip("/")

    def call(self, system: str, user: str, model: str, temperature: float, timeout: int) -> tuple[str, int]:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set. Configure the environment variable to enable LLM execution.")

        resp = httpx.post(
            f"{self.base_url}/v1/messages",
            json={
                "model": model,
                "max_tokens": 4096,
                "system": system,
                "messages": [
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": JSON_CONTENT_TYPE,
            },
            timeout=timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        text = data["content"][0]["text"]
        usage = data.get("usage", {})
        tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
        return text, tokens


class CopilotProvider(LLMProvider):
    """GitHub Copilot chat completion using Copilot CLI OAuth login state."""

    name = "copilot"

    def __init__(self, api_key: str | None = None, base_url: str | None = None, auth_service: CopilotAuthService | None = None):
        self.api_key = api_key
        self.base_url = (config.COPILOT_BASE_URL if base_url is None else base_url).rstrip("/")
        self.auth_service = auth_service or CopilotAuthService()

    def call(self, system: str, user: str, model: str, temperature: float, timeout: int) -> tuple[str, int]:
        api_key = self.api_key or self._resolve_api_key()
        self._validate_api_key(api_key)

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": temperature,
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": JSON_CONTENT_TYPE,
                "Editor-Version": "vscode/1.100.0",
            },
            timeout=timeout,
        )

        if resp.status_code != 200:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")

        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        tokens = data.get("usage", {}).get("total_tokens", 0)
        return text, tokens

    def _resolve_api_key(self) -> str:
        auth = self.auth_service.resolve_stored_auth()
        if auth:
            return auth.token
        raise RuntimeError(
            "Copilot OAuth token not found. Run `copilot login` or complete the /api/copilot-auth/device-code flow. "
            "Do not use a GitHub PAT for Copilot chat completions."
        )

    def _validate_api_key(self, api_key: str) -> None:
        if api_key.startswith(PERSONAL_ACCESS_TOKEN_PREFIXES):
            raise RuntimeError(
                "Personal Access Tokens are not supported for LLM_PROVIDER=copilot direct /chat/completions calls. "
                "Use `copilot login`, or provide an OAuth user token (`gho_...` / `ghu_...`). "
                "If you want SDK/CLI token automation, prefer ORCHESTRATION_BACKEND=copilot_sdk."
            )


# ── Provider registry & factory ──────────────────────────────

PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "copilot": CopilotProvider,
}


def get_provider(name: str | None = None, **kwargs) -> LLMProvider:
    """Create a provider instance by name. Defaults to LLM_PROVIDER from config."""
    name = (name or config.LLM_PROVIDER).lower()
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown LLM provider '{name}'. Choose from: {', '.join(PROVIDERS)}")
    logger.info("Using LLM provider: %s", name)
    return cls(**kwargs)
