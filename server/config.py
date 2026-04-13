from __future__ import annotations

"""Centralized configuration for Synapse Ops Dashboard."""
import os
from pathlib import Path

# ── .env file loader (no python-dotenv needed) ───────────────
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

def _load_dotenv(path: Path) -> None:
    """Load key=value pairs from a .env file into os.environ (won't overwrite)."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)

_load_dotenv(_PROJECT_ROOT / ".env")

# ── Environment ───────────────────────────────────────────────
ENV = os.environ.get("OPS_ENV", "local")  # local | prod

# ── Paths ─────────────────────────────────────────────────────
PROJECT_ROOT = _PROJECT_ROOT
ROLES_DIR = os.environ.get("ROLES_DIR", str(PROJECT_ROOT / "roles"))

# ── Server ────────────────────────────────────────────────────
HOST = os.environ.get("OPS_HOST", "127.0.0.1" if ENV == "local" else "0.0.0.0")
PORT = int(os.environ.get("OPS_PORT", "9600"))
WORKERS = int(os.environ.get("OPS_WORKERS", "1" if ENV == "local" else "4"))
LOG_LEVEL = os.environ.get("OPS_LOG_LEVEL", "debug" if ENV == "local" else "info")
RELOAD = ENV == "local"
LOG_DIR = os.environ.get("OPS_LOG_DIR", str(PROJECT_ROOT / "server" / "logs"))
LOG_FILE = os.environ.get("OPS_LOG_FILE", "ops-dashboard.log")
LOG_MAX_BYTES = int(os.environ.get("OPS_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.environ.get("OPS_LOG_BACKUP_COUNT", "5"))
LARK_BOT_WEBHOOK_URL = os.environ.get("OPS_LARK_BOT_WEBHOOK_URL", "").strip()
LARK_BOT_KEYWORD = os.environ.get("OPS_LARK_BOT_KEYWORD", "告警").strip() or "告警"
RUNTIME_AUTH_ALERTS_ENABLED = os.environ.get("OPS_RUNTIME_AUTH_ALERTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
BUG_LOG_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_BUG_LOG_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" else "false",
).lower() in {"1", "true", "yes", "on"}
BUG_LOG_SWEEP_INTERVAL_MINUTES = max(1, int(os.environ.get("OPS_BUG_LOG_SWEEP_INTERVAL_MINUTES", "5")))
BUG_LOG_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_BUG_LOG_SWEEP_STARTUP_DELAY_SECONDS", "15")))
BUG_LOG_SWEEP_AUTO_START = os.environ.get("OPS_BUG_LOG_SWEEP_AUTO_START", "false").lower() in {"1", "true", "yes", "on"}
BUG_LOG_SWEEP_MIN_SCORE = float(os.environ.get("OPS_BUG_LOG_SWEEP_MIN_SCORE", "70"))
BUG_LOG_SWEEP_MAX_CREATED = max(1, int(os.environ.get("OPS_BUG_LOG_SWEEP_MAX_CREATED", "3")))
BUG_LOG_SWEEP_SCHEDULER_POLL_SECONDS = max(5, int(os.environ.get("OPS_BUG_LOG_SWEEP_SCHEDULER_POLL_SECONDS", "30")))

# ── Database ──────────────────────────────────────────────────
DB_PATH = os.environ.get("OPS_DB_PATH", str(PROJECT_ROOT / "server" / "ops.db"))
DATABASE_URL = os.environ.get("OPS_DATABASE_URL", f"sqlite:///{DB_PATH}")
DB_POOL_SIZE = int(os.environ.get("OPS_DB_POOL_SIZE", "12"))
DB_MAX_OVERFLOW = int(os.environ.get("OPS_DB_MAX_OVERFLOW", "24"))
DB_POOL_TIMEOUT = int(os.environ.get("OPS_DB_POOL_TIMEOUT", "60"))
DB_POOL_RECYCLE = int(os.environ.get("OPS_DB_POOL_RECYCLE", "1800"))
DB_POOL_PRE_PING = os.environ.get("OPS_DB_POOL_PRE_PING", "true").lower() in {"1", "true", "yes", "on"}

# ── LLM ───────────────────────────────────────────────────────
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # openai | claude | copilot | codex
LLM_MODEL = os.environ.get("LLM_MODEL", "gpt-4o")
LLM_EXECUTION_MODE = os.environ.get("LLM_EXECUTION_MODE", "sync").strip().lower() or "sync"  # sync | session
LLM_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "300"))
MAX_CONTEXT_SIZE = int(os.environ.get("MAX_CONTEXT_SIZE", "500000"))
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "100000"))

# ── Orchestration ─────────────────────────────────────────────
ORCHESTRATION_BACKEND_OVERRIDE = os.environ.get("ORCHESTRATION_BACKEND", "").strip().lower()
COPILOT_SDK_MODEL = os.environ.get("COPILOT_SDK_MODEL", LLM_MODEL)
COPILOT_SDK_TIMEOUT = int(os.environ.get("COPILOT_SDK_TIMEOUT", str(LLM_TIMEOUT)))
COPILOT_SDK_MONITOR_ENABLED = os.environ.get("COPILOT_SDK_MONITOR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
COPILOT_SDK_POLL_INTERVAL_SEC = float(os.environ.get("COPILOT_SDK_POLL_INTERVAL_SEC", "3"))
COPILOT_SDK_STALE_AFTER_SEC = float(os.environ.get("COPILOT_SDK_STALE_AFTER_SEC", "30"))
COPILOT_SDK_AUTO_USER_INPUT = os.environ.get("COPILOT_SDK_AUTO_USER_INPUT", "true").lower() in {"1", "true", "yes", "on"}
COPILOT_SDK_AUTO_USER_INPUT_TEXT = os.environ.get(
    "COPILOT_SDK_AUTO_USER_INPUT_TEXT",
    "Proceed automatically using best effort. Do not wait for additional user input.",
)
COPILOT_SDK_NODE_BIN = os.environ.get("COPILOT_SDK_NODE_BIN", "node")
COPILOT_SDK_RUNNER_PATH = os.environ.get(
    "COPILOT_SDK_RUNNER_PATH",
    str(PROJECT_ROOT / "copilot-sdk-runner" / "run_session.mjs"),
)
COPILOT_SDK_DB_ANALYST_MCP_COMMAND = os.environ.get("COPILOT_SDK_DB_ANALYST_MCP_COMMAND", "")
COPILOT_SDK_DB_ANALYST_MCP_ARGS_JSON = os.environ.get("COPILOT_SDK_DB_ANALYST_MCP_ARGS_JSON", "[]")
OPENAI_RESPONSES_MONITOR_ENABLED = os.environ.get("OPENAI_RESPONSES_MONITOR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
OPENAI_RESPONSES_POLL_INTERVAL_SEC = float(os.environ.get("OPENAI_RESPONSES_POLL_INTERVAL_SEC", "3"))
CODEX_CLI_BIN = os.environ.get("CODEX_CLI_BIN", "codex").strip() or "codex"
CODEX_CLI_MODEL = os.environ.get("CODEX_CLI_MODEL", "").strip()
CODEX_CLI_TIMEOUT = int(os.environ.get("CODEX_CLI_TIMEOUT", str(LLM_TIMEOUT)))
CODEX_CLI_TASK_TIMEOUT = int(os.environ.get("CODEX_CLI_TASK_TIMEOUT", "0"))
CODEX_CLI_SANDBOX = os.environ.get("CODEX_CLI_SANDBOX", "workspace-write").strip() or "workspace-write"
CODEX_CLI_FULL_AUTO = os.environ.get("CODEX_CLI_FULL_AUTO", "true").lower() in {"1", "true", "yes", "on"}
CODEX_CLI_SKIP_GIT_REPO_CHECK = os.environ.get("CODEX_CLI_SKIP_GIT_REPO_CHECK", "false").lower() in {"1", "true", "yes", "on"}
CODEX_CLI_JSON_EVENTS = os.environ.get("CODEX_CLI_JSON_EVENTS", "true").lower() in {"1", "true", "yes", "on"}
CODEX_CLI_PERSONA_CHAR_LIMIT = max(200, int(os.environ.get("CODEX_CLI_PERSONA_CHAR_LIMIT", "900")))
CODEX_CLI_SECTION_CHAR_LIMIT = max(200, int(os.environ.get("CODEX_CLI_SECTION_CHAR_LIMIT", "1600")))
CODEX_CLI_PROMPT_CHAR_LIMIT = max(1200, int(os.environ.get("CODEX_CLI_PROMPT_CHAR_LIMIT", "6500")))
CODEX_CLI_MONITOR_ENABLED = os.environ.get("CODEX_CLI_MONITOR_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
CODEX_CLI_POLL_INTERVAL_SEC = float(os.environ.get("CODEX_CLI_POLL_INTERVAL_SEC", "5"))
CODEX_CLI_STALE_AFTER_SEC = float(os.environ.get("CODEX_CLI_STALE_AFTER_SEC", "180"))
CODEX_CLI_MAX_ACTIVE_SECONDS = max(0, int(os.environ.get("CODEX_CLI_MAX_ACTIVE_SECONDS", "3600")))
CODEX_CLI_SESSION_REUSE_TTL_SECONDS = max(60, int(os.environ.get("CODEX_CLI_SESSION_REUSE_TTL_SECONDS", "7200")))
CODEX_CLI_SESSION_MAX_TURNS = max(0, int(os.environ.get("CODEX_CLI_SESSION_MAX_TURNS", "8")))
CODEX_CLI_SESSION_MAX_CACHED_INPUT_TOKENS = max(0, int(os.environ.get("CODEX_CLI_SESSION_MAX_CACHED_INPUT_TOKENS", "1000000")))
CODEX_CLI_SESSION_MAX_INPUT_TOKENS = max(0, int(os.environ.get("CODEX_CLI_SESSION_MAX_INPUT_TOKENS", "1500000")))
CODEX_CLI_RESUME_MAX_ATTEMPTS = max(0, int(os.environ.get("CODEX_CLI_RESUME_MAX_ATTEMPTS", "2")))
CODEX_CLI_MONITOR_STARTUP_GRACE_SEC = float(os.environ.get("CODEX_CLI_MONITOR_STARTUP_GRACE_SEC", "20"))
DELIVERY_VCS_TIMEOUT_SECONDS = max(1, int(os.environ.get("OPS_DELIVERY_VCS_TIMEOUT_SECONDS", "120")))
DELIVERY_VCS_REMOTE_NAME = os.environ.get("OPS_DELIVERY_VCS_REMOTE_NAME", "origin").strip() or "origin"
RUNTIME_TIER_MINI_BACKEND = os.environ.get("OPS_RUNTIME_TIER_MINI_BACKEND", "").strip().lower()
RUNTIME_TIER_MINI_PROVIDER = os.environ.get("OPS_RUNTIME_TIER_MINI_PROVIDER", "").strip().lower()
RUNTIME_TIER_MINI_MODEL = os.environ.get("OPS_RUNTIME_TIER_MINI_MODEL", "").strip()
RUNTIME_TIER_STANDARD_BACKEND = os.environ.get("OPS_RUNTIME_TIER_STANDARD_BACKEND", "").strip().lower()
RUNTIME_TIER_STANDARD_PROVIDER = os.environ.get("OPS_RUNTIME_TIER_STANDARD_PROVIDER", "").strip().lower()
RUNTIME_TIER_STANDARD_MODEL = os.environ.get("OPS_RUNTIME_TIER_STANDARD_MODEL", "").strip()
RUNTIME_TIER_MAX_BACKEND = os.environ.get("OPS_RUNTIME_TIER_MAX_BACKEND", "").strip().lower()
RUNTIME_TIER_MAX_PROVIDER = os.environ.get("OPS_RUNTIME_TIER_MAX_PROVIDER", "").strip().lower()
RUNTIME_TIER_MAX_MODEL = os.environ.get("OPS_RUNTIME_TIER_MAX_MODEL", "").strip()
E2E_MODE = os.environ.get("OPS_E2E_MODE", "false").lower() in {"1", "true", "yes", "on"}
E2E_SYNC_DISPATCH = os.environ.get("OPS_E2E_SYNC_DISPATCH", "false").lower() in {"1", "true", "yes", "on"}

# Per-provider credentials (loaded from .env or environment)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
COPILOT_GITHUB_TOKEN = os.environ.get("COPILOT_GITHUB_TOKEN", "")
GH_TOKEN = os.environ.get("GH_TOKEN", "")
COPILOT_OAUTH_TOKEN = os.environ.get("COPILOT_OAUTH_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
COPILOT_BASE_URL = os.environ.get("COPILOT_BASE_URL", "https://api.githubcopilot.com")

# ── CORS ──────────────────────────────────────────────────────
CORS_ORIGINS = os.environ.get("OPS_CORS_ORIGINS", "*").split(",")


SUPPORTED_LLM_EXECUTION_MODES = {"sync", "session"}
SUPPORTED_ORCHESTRATION_BACKENDS = {"legacy", "copilot_sdk", "openai_responses", "codex_cli"}


def resolve_orchestration_backend(
    *,
    provider: str | None = None,
    execution_mode: str | None = None,
    override: str | None = None,
) -> str:
    provider_name = (provider or LLM_PROVIDER or "openai").strip().lower()
    mode = (execution_mode or LLM_EXECUTION_MODE or "sync").strip().lower()
    backend_override = (override if override is not None else ORCHESTRATION_BACKEND_OVERRIDE).strip().lower()

    if mode not in SUPPORTED_LLM_EXECUTION_MODES:
        raise ValueError(
            f"Unsupported LLM_EXECUTION_MODE '{mode}'. Choose from: {', '.join(sorted(SUPPORTED_LLM_EXECUTION_MODES))}"
        )

    if backend_override:
        if backend_override not in SUPPORTED_ORCHESTRATION_BACKENDS:
            raise ValueError(
                f"Unsupported ORCHESTRATION_BACKEND '{backend_override}'. "
                f"Choose from: {', '.join(sorted(SUPPORTED_ORCHESTRATION_BACKENDS))}"
            )
        return backend_override

    if provider_name == "codex":
        return "codex_cli"

    if mode == "session":
        if provider_name == "openai":
            return "openai_responses"
        if provider_name == "copilot":
            return "copilot_sdk"
        if provider_name == "codex":
            return "codex_cli"
        raise ValueError(
            f"LLM_PROVIDER '{provider_name}' does not support LLM_EXECUTION_MODE=session. "
            "Set ORCHESTRATION_BACKEND explicitly or switch to openai/copilot."
        )

    return "legacy"


ORCHESTRATION_BACKEND = resolve_orchestration_backend()
