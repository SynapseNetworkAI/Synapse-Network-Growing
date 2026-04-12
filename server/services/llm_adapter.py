from __future__ import annotations

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
from server.services.codex_cli import run_codex_exec
from server.services.copilot_auth import CopilotAuthService

logger = logging.getLogger("ops-dashboard.llm_adapter")

PERSONAL_ACCESS_TOKEN_PREFIXES = ("github_pat_", "ghp_")
JSON_CONTENT_TYPE = "application/json"
_MODEL_ALIASES = {
    "openai": {
        "openai": "gpt-4o",
        "gpt": "gpt-4o",
        "responses": "gpt-4o",
    },
    "claude": {
        "claude": "claude-3-7-sonnet-latest",
        "anthropic": "claude-3-7-sonnet-latest",
    },
    "copilot": {
        "copilot": "gpt-4o",
        "github-copilot": "gpt-4o",
    },
    "codex": {},
}


def normalize_model_name(provider_name: str, model: str) -> str:
    raw = str(model or "").strip()
    if not raw:
        return raw
    alias = _MODEL_ALIASES.get(provider_name, {}).get(raw.lower())
    if alias and alias != raw:
        logger.warning("Normalizing %s model alias '%s' to '%s'", provider_name, raw, alias)
        return alias
    return raw


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
        self._require_api_key()
        resolved_model = normalize_model_name(self.name, model)

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": resolved_model,
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

    def create_response(
        self,
        *,
        instructions: str,
        user_input: str,
        model: str,
        temperature: float,
        timeout: int,
        background: bool,
        previous_response_id: str | None = None,
    ) -> dict:
        self._require_api_key()
        resolved_model = normalize_model_name(self.name, model)
        payload = {
            "model": resolved_model,
            "instructions": instructions,
            "input": user_input,
            "temperature": temperature,
            "background": background,
        }
        if previous_response_id:
            payload["previous_response_id"] = previous_response_id

        resp = httpx.post(
            f"{self.base_url}/responses",
            json=payload,
            headers=self._headers(),
            timeout=timeout,
        )
        if resp.status_code not in {200, 201}:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def retrieve_response(self, response_id: str, timeout: int) -> dict:
        self._require_api_key()
        resp = httpx.get(
            f"{self.base_url}/responses/{response_id}",
            headers=self._headers(),
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def cancel_response(self, response_id: str, timeout: int) -> dict:
        self._require_api_key()
        resp = httpx.post(
            f"{self.base_url}/responses/{response_id}/cancel",
            headers=self._headers(),
            timeout=timeout,
        )
        if resp.status_code not in {200, 202}:
            raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:500]}")
        return resp.json()

    def extract_response_text(self, data: dict) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text

        text_parts: list[str] = []
        for item in data.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "message":
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                content_type = str(content.get("type") or "")
                if content_type in {"output_text", "text"}:
                    text = content.get("text")
                    if isinstance(text, str) and text:
                        text_parts.append(text)
        return "\n".join(text_parts).strip()

    def extract_response_tokens(self, data: dict) -> int:
        usage = data.get("usage", {}) or {}
        total_tokens = usage.get("total_tokens")
        if total_tokens is not None:
            return int(total_tokens)
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return input_tokens + output_tokens

    def extract_response_error(self, data: dict) -> str | None:
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if message:
                return str(message)
        incomplete = data.get("incomplete_details")
        if isinstance(incomplete, dict):
            reason = incomplete.get("reason")
            if reason:
                return f"Response incomplete: {reason}"
        return None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": JSON_CONTENT_TYPE,
        }

    def _require_api_key(self) -> None:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY not set. Configure the environment variable to enable LLM execution.")


class ClaudeProvider(LLMProvider):
    """Anthropic Claude Messages API."""

    name = "claude"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = config.ANTHROPIC_API_KEY if api_key is None else api_key
        self.base_url = (config.ANTHROPIC_BASE_URL if base_url is None else base_url).rstrip("/")

    def call(self, system: str, user: str, model: str, temperature: float, timeout: int) -> tuple[str, int]:
        if not self.api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not set. Configure the environment variable to enable LLM execution.")
        resolved_model = normalize_model_name(self.name, model)

        resp = httpx.post(
            f"{self.base_url}/v1/messages",
            json={
                "model": resolved_model,
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
        resolved_model = normalize_model_name(self.name, model)

        resp = httpx.post(
            f"{self.base_url}/chat/completions",
            json={
                "model": resolved_model,
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


class CodexCLIProvider(LLMProvider):
    """Codex CLI provider using the local authenticated Codex installation."""

    name = "codex"

    def call(self, system: str, user: str, model: str, temperature: float, timeout: int) -> tuple[str, int]:
        del temperature
        prompt = "\n\n".join(
            [
                "# System Instructions",
                system,
                "# User Request",
                user,
                "Return only the final answer content with no surrounding commentary.",
            ]
        )
        output_path = config.PROJECT_ROOT / "runtime" / "codex-cli-provider" / "last-message.txt"
        result = run_codex_exec(
            prompt=prompt,
            cwd=config.PROJECT_ROOT,
            output_path=output_path,
            model=model,
            timeout=timeout,
            add_dirs=[config.PROJECT_ROOT],
        )
        if result.exit_code != 0:
            detail = (result.stderr or result.stdout or result.text or "Codex CLI execution failed").strip()
            raise RuntimeError(detail[:1000])
        return result.text.strip(), 0


# ── Provider registry & factory ──────────────────────────────

PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
    "claude": ClaudeProvider,
    "copilot": CopilotProvider,
    "codex": CodexCLIProvider,
}


def get_provider(name: str | None = None, **kwargs) -> LLMProvider:
    """Create a provider instance by name. Defaults to LLM_PROVIDER from config."""
    name = (name or config.LLM_PROVIDER).lower()
    cls = PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown LLM provider '{name}'. Choose from: {', '.join(PROVIDERS)}")
    logger.info("Using LLM provider: %s", name)
    return cls(**kwargs)
