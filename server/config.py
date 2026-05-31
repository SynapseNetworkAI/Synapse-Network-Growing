from __future__ import annotations

"""Centralized configuration for Synapse Ops Dashboard."""
import json
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


def _env_flag(name: str, default: str = "false") -> bool:
    return os.environ.get(name, default).lower() in {"1", "true", "yes", "on"}


_OPS_E2E_MODE = _env_flag("OPS_E2E_MODE")


def _json_env_list(name: str, default: list[dict[str, str]]) -> list[dict[str, str]]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return default
    if not isinstance(value, list):
        return default
    items: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        items.append({str(key): str(val).strip() for key, val in item.items()})
    return items or default

# ── Paths ─────────────────────────────────────────────────────
PROJECT_ROOT = _PROJECT_ROOT
ROLES_DIR = os.environ.get("ROLES_DIR", str(PROJECT_ROOT / "roles"))
AGENTS_MEMORY_ROOT = os.environ.get("OPS_AGENTS_MEMORY_ROOT", "/Users/cliff/workspace/agent/Agents-Memory")

# ── Server ────────────────────────────────────────────────────
HOST = os.environ.get("OPS_HOST", "127.0.0.1" if ENV == "local" else "0.0.0.0")
PORT = int(os.environ.get("OPS_PORT", "9600"))
WORKERS = int(os.environ.get("OPS_WORKERS", "1" if ENV == "local" else "4"))
LOG_LEVEL = os.environ.get("OPS_LOG_LEVEL", "debug" if ENV == "local" else "info")
RELOAD = ENV == "local"
LOG_DIR = os.environ.get("OPS_LOG_DIR", str(PROJECT_ROOT / "server" / "logs"))
LOG_FILE = os.environ.get("OPS_LOG_FILE", "ops-dashboard.jsonl")
LOG_BACKUP_DAYS = max(1, int(os.environ.get("OPS_LOG_BACKUP_DAYS", "14")))
LOG_MAX_BYTES = int(os.environ.get("OPS_LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.environ.get("OPS_LOG_BACKUP_COUNT", "5"))
LARK_BOT_WEBHOOK_URL = os.environ.get("OPS_LARK_BOT_WEBHOOK_URL", "").strip()
LARK_BOT_KEYWORD = os.environ.get("OPS_LARK_BOT_KEYWORD", "告警").strip() or "告警"
LARK_REQUIREMENT_WEBHOOK_URL = os.environ.get("OPS_LARK_REQUIREMENT_WEBHOOK_URL", "").strip()
LARK_REQUIREMENT_KEYWORD = os.environ.get("OPS_LARK_REQUIREMENT_KEYWORD", "需求").strip() or "需求"
LARK_ALERT_WEBHOOK_URL = os.environ.get("OPS_LARK_ALERT_WEBHOOK_URL", LARK_BOT_WEBHOOK_URL).strip()
LARK_ALERT_KEYWORD = os.environ.get("OPS_LARK_ALERT_KEYWORD", LARK_BOT_KEYWORD).strip() or LARK_BOT_KEYWORD
LARK_APPROVAL_WEBHOOK_URL = os.environ.get("OPS_LARK_APPROVAL_WEBHOOK_URL", LARK_BOT_WEBHOOK_URL).strip()
LARK_APPROVAL_KEYWORD = os.environ.get("OPS_LARK_APPROVAL_KEYWORD", "审批").strip() or "审批"
LARK_RELEASE_WEBHOOK_URL = os.environ.get("OPS_LARK_RELEASE_WEBHOOK_URL", "").strip()
LARK_RELEASE_KEYWORD = os.environ.get("OPS_LARK_RELEASE_KEYWORD", "发布").strip() or "发布"
LARK_DELIVERY_DRY_RUN = os.environ.get("OPS_LARK_DELIVERY_DRY_RUN", "false").lower() in {"1", "true", "yes", "on"}
OPS_BASE_URL = os.environ.get("OPS_BASE_URL", "").strip().rstrip("/")
OPS_AGENT_DEPLOY_API_TOKEN = os.environ.get("OPS_AGENT_DEPLOY_API_TOKEN", "").strip()
OPS_AGENT_BUG_API_TOKEN = os.environ.get("OPS_AGENT_BUG_API_TOKEN", "").strip()
NOTIFICATION_DISPATCHER_ENABLED = _env_flag("OPS_NOTIFICATION_DISPATCHER_ENABLED", "false" if _OPS_E2E_MODE else "true")
NOTIFICATION_DISPATCH_INTERVAL_SECONDS = max(1, int(os.environ.get("OPS_NOTIFICATION_DISPATCH_INTERVAL_SECONDS", "5")))
NOTIFICATION_ALERT_BURST_PER_MINUTE = max(1, int(os.environ.get("OPS_NOTIFICATION_ALERT_BURST_PER_MINUTE", "5")))
NOTIFICATION_DEFAULT_COOLDOWN_SECONDS = max(0, int(os.environ.get("OPS_NOTIFICATION_DEFAULT_COOLDOWN_SECONDS", "900")))
NOTIFICATION_P0_COOLDOWN_SECONDS = max(0, int(os.environ.get("OPS_NOTIFICATION_P0_COOLDOWN_SECONDS", "300")))
NOTIFICATION_P1_COOLDOWN_SECONDS = max(0, int(os.environ.get("OPS_NOTIFICATION_P1_COOLDOWN_SECONDS", "900")))
NOTIFICATION_APPROVAL_REMINDER_SECONDS = max(60, int(os.environ.get("OPS_NOTIFICATION_APPROVAL_REMINDER_SECONDS", "7200")))
NOTIFICATION_MAX_DELIVERY_ATTEMPTS = max(1, int(os.environ.get("OPS_NOTIFICATION_MAX_DELIVERY_ATTEMPTS", "4")))
RUNTIME_AUTH_ALERTS_ENABLED = os.environ.get("OPS_RUNTIME_AUTH_ALERTS_ENABLED", "true").lower() in {"1", "true", "yes", "on"}
BUG_LOG_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_BUG_LOG_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
).lower() in {"1", "true", "yes", "on"}
BUG_LOG_SWEEP_INTERVAL_MINUTES = max(1, int(os.environ.get("OPS_BUG_LOG_SWEEP_INTERVAL_MINUTES", "5")))
BUG_LOG_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_BUG_LOG_SWEEP_STARTUP_DELAY_SECONDS", "15")))
BUG_LOG_SWEEP_AUTO_START = os.environ.get("OPS_BUG_LOG_SWEEP_AUTO_START", "false").lower() in {"1", "true", "yes", "on"}
BUG_LOG_SWEEP_MIN_SCORE = float(os.environ.get("OPS_BUG_LOG_SWEEP_MIN_SCORE", "70"))
BUG_LOG_SWEEP_MAX_CREATED = max(1, int(os.environ.get("OPS_BUG_LOG_SWEEP_MAX_CREATED", "3")))
BUG_LOG_SWEEP_SCHEDULER_POLL_SECONDS = max(5, int(os.environ.get("OPS_BUG_LOG_SWEEP_SCHEDULER_POLL_SECONDS", "30")))
GOAL_PLANNER_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_GOAL_PLANNER_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
).lower() in {"1", "true", "yes", "on"}
OPERATOR_TIMEZONE = os.environ.get("OPS_OPERATOR_TIMEZONE", "Asia/Kuala_Lumpur").strip() or "Asia/Kuala_Lumpur"
GOAL_PLANNER_SWEEP_LOCAL_TIME = os.environ.get("OPS_GOAL_PLANNER_SWEEP_LOCAL_TIME", "09:00").strip() or "09:00"
GOAL_PLANNER_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_GOAL_PLANNER_SWEEP_STARTUP_DELAY_SECONDS", "20")))
GOAL_PLANNER_SWEEP_SCHEDULER_POLL_SECONDS = max(30, int(os.environ.get("OPS_GOAL_PLANNER_SWEEP_SCHEDULER_POLL_SECONDS", "60")))
CI_STATUS_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_CI_STATUS_SWEEP_SCHEDULER_ENABLED",
    "false",
).lower() in {"1", "true", "yes", "on"}
CI_STATUS_SWEEP_INTERVAL_SECONDS = max(10, int(os.environ.get("OPS_CI_STATUS_SWEEP_INTERVAL_SECONDS", "60")))
CI_STATUS_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_CI_STATUS_SWEEP_STARTUP_DELAY_SECONDS", "20")))
CI_STATUS_SWEEP_RUNTIME_CAP_SECONDS = max(5, int(os.environ.get("OPS_CI_STATUS_SWEEP_RUNTIME_CAP_SECONDS", "60")))
CI_STATUS_SWEEP_STALE_LOCK_SECONDS = max(60, int(os.environ.get("OPS_CI_STATUS_SWEEP_STALE_LOCK_SECONDS", "300")))
RELEASE_PR_STATUS_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_RELEASE_PR_STATUS_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
).lower() in {"1", "true", "yes", "on"}
RELEASE_PR_STATUS_SWEEP_INTERVAL_SECONDS = max(60, int(os.environ.get("OPS_RELEASE_PR_STATUS_SWEEP_INTERVAL_SECONDS", "1800")))
RELEASE_PR_STATUS_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_RELEASE_PR_STATUS_SWEEP_STARTUP_DELAY_SECONDS", "30")))
RELEASE_DEPLOYMENT_STATUS_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_RELEASE_DEPLOYMENT_STATUS_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
).lower() in {"1", "true", "yes", "on"}
RELEASE_DEPLOYMENT_STATUS_SWEEP_INTERVAL_SECONDS = max(60, int(os.environ.get("OPS_RELEASE_DEPLOYMENT_STATUS_SWEEP_INTERVAL_SECONDS", "60")))
RELEASE_DEPLOYMENT_STATUS_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_RELEASE_DEPLOYMENT_STATUS_SWEEP_STARTUP_DELAY_SECONDS", "20")))
RELEASE_DEPLOYMENT_PENDING_RUN_ID_TIMEOUT_SECONDS = max(60, int(os.environ.get("OPS_RELEASE_DEPLOYMENT_PENDING_RUN_ID_TIMEOUT_SECONDS", "900")))
RELEASE_DEPLOYMENT_RUNNING_TIMEOUT_SECONDS = max(60, int(os.environ.get("OPS_RELEASE_DEPLOYMENT_RUNNING_TIMEOUT_SECONDS", "1800")))
RELEASE_DEPLOY_BACKEND = "local"
X_SOCIAL_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_X_SOCIAL_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
).lower() in {"1", "true", "yes", "on"}
X_SOCIAL_SWEEP_SCHEDULER_POLL_SECONDS = max(60, int(os.environ.get("OPS_X_SOCIAL_SWEEP_SCHEDULER_POLL_SECONDS", "300")))
X_SOCIAL_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_X_SOCIAL_SWEEP_STARTUP_DELAY_SECONDS", "45")))
SECRET_MANAGER_CLEANUP_SWEEP_SCHEDULER_ENABLED = os.environ.get(
    "OPS_SECRET_MANAGER_CLEANUP_SWEEP_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
).lower() in {"1", "true", "yes", "on"}
SECRET_MANAGER_CLEANUP_SWEEP_POLL_SECONDS = max(300, int(os.environ.get("OPS_SECRET_MANAGER_CLEANUP_SWEEP_POLL_SECONDS", "1800")))
SECRET_MANAGER_CLEANUP_SWEEP_STARTUP_DELAY_SECONDS = max(0, int(os.environ.get("OPS_SECRET_MANAGER_CLEANUP_SWEEP_STARTUP_DELAY_SECONDS", "60")))
COST_CONTROL_SCHEDULER_ENABLED = _env_flag(
    "OPS_COST_CONTROL_SCHEDULER_ENABLED",
    "true" if ENV == "local" and not _OPS_E2E_MODE else "false",
)
COST_CONTROL_SCHEDULER_POLL_SECONDS = max(
    300, int(os.environ.get("OPS_COST_CONTROL_SCHEDULER_POLL_SECONDS", "300"))
)
COST_CONTROL_STARTUP_DELAY_SECONDS = max(
    0, int(os.environ.get("OPS_COST_CONTROL_STARTUP_DELAY_SECONDS", "75"))
)
X_DAILY_PLANNER_GENERATING_TIMEOUT_MINUTES = max(1, int(os.environ.get("OPS_X_DAILY_PLANNER_GENERATING_TIMEOUT_MINUTES", "15")))
X_DAILY_PLANNER_MAX_CREATED_PER_TICK = max(1, int(os.environ.get("OPS_X_DAILY_PLANNER_MAX_CREATED_PER_TICK", "3")))
X_READ_DAILY_REQUEST_BUDGET = max(0, int(os.environ.get("OPS_X_READ_DAILY_REQUEST_BUDGET", "20")))
X_TREND_DAILY_SOURCE_POST_BUDGET = max(0, int(os.environ.get("OPS_X_TREND_DAILY_SOURCE_POST_BUDGET", "20")))
X_WATCHLIST_SYNC_INTERVAL_MINUTES = max(5, int(os.environ.get("OPS_X_WATCHLIST_SYNC_INTERVAL_MINUTES", "60")))
X_WATCHLIST_MAX_ACCOUNTS_PER_SWEEP = max(1, int(os.environ.get("OPS_X_WATCHLIST_MAX_ACCOUNTS_PER_SWEEP", "5")))
X_WATCHLIST_TWEETS_PER_ACCOUNT = max(5, int(os.environ.get("OPS_X_WATCHLIST_TWEETS_PER_ACCOUNT", "5")))
X_TREND_MIN_TEXT_CHARS = max(1, int(os.environ.get("OPS_X_TREND_MIN_TEXT_CHARS", "50")))
X_AI_REPLY_APPROVAL_REF = os.environ.get("X_AI_REPLY_APPROVAL_REF", "").strip()
CI_FINAL_REGRESSION_TIMEOUT_SECONDS = max(30, int(os.environ.get("OPS_CI_FINAL_REGRESSION_TIMEOUT_SECONDS", "600")))
WORKFLOW_RUNNER_STALE_AGENT_SELF_REPAIR_SECONDS = max(60, int(os.environ.get("OPS_WORKFLOW_RUNNER_STALE_AGENT_SELF_REPAIR_SECONDS", "900")))
WORKFLOW_RUNNER_STALE_DEFAULT_SECONDS = max(60, int(os.environ.get("OPS_WORKFLOW_RUNNER_STALE_DEFAULT_SECONDS", "1800")))
FORUM_FEEDBACK_GATEWAY_ADMIN_BASE_URL = os.environ.get("OPS_FORUM_FEEDBACK_GATEWAY_ADMIN_BASE_URL", "http://127.0.0.1:8300").strip().rstrip("/")
FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN = os.environ.get("OPS_FORUM_FEEDBACK_GATEWAY_ADMIN_TOKEN", "").strip()
FORUM_FEEDBACK_DEFAULT_PROJECT_KEY = os.environ.get("OPS_FORUM_FEEDBACK_DEFAULT_PROJECT_KEY", "synapse-network").strip() or "synapse-network"
FORUM_FEEDBACK_DEFAULT_GOAL_KEY = os.environ.get("OPS_FORUM_FEEDBACK_DEFAULT_GOAL_KEY", "community_support").strip() or "community_support"
FORUM_FEEDBACK_MAX_TASKS = max(1, int(os.environ.get("OPS_FORUM_FEEDBACK_MAX_TASKS", "10")))

# ── Database ──────────────────────────────────────────────────
_raw_database_url = os.environ.get("OPS_DATABASE_URL", "").strip()
if not _raw_database_url:
    raise RuntimeError(  # pragma: no cover - exercised by subprocess config smoke tests
        "OPS_DATABASE_URL is required. Synapse-Network-Growing runtime is PostgreSQL-only; "
        "use postgresql+psycopg://synapse_growing:synapse_growing_dev@127.0.0.1:54329/synapse_growing_local locally."
    )
if not _raw_database_url.startswith(("postgresql://", "postgresql+psycopg://", "postgresql+psycopg2://")):
    raise RuntimeError(  # pragma: no cover - exercised by subprocess config smoke tests
        "OPS_DATABASE_URL must be a PostgreSQL URL. SQLite is supported only as an input to "
        "scripts/db/migrate_sqlite_to_postgres.py, never as app runtime/test storage."
    )
DATABASE_URL = _raw_database_url
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
SOCIAL_CONTENT_LLM_PROVIDER = os.environ.get("SOCIAL_CONTENT_LLM_PROVIDER", "codex").strip().lower() or "codex"
SOCIAL_CONTENT_LLM_MODEL = os.environ.get("SOCIAL_CONTENT_LLM_MODEL", "gpt-5.4").strip() or "gpt-5.4"
SOCIAL_CONTENT_LLM_FALLBACK_MODEL = os.environ.get("SOCIAL_CONTENT_LLM_FALLBACK_MODEL", "gpt-5.4").strip() or "gpt-5.4"
SOCIAL_CONTENT_LLM_TIMEOUT = int(os.environ.get("SOCIAL_CONTENT_LLM_TIMEOUT", "180"))
SOCIAL_IMAGE_PROVIDER = os.environ.get("SOCIAL_IMAGE_PROVIDER", "openai_images").strip().lower() or "openai_images"
SOCIAL_IMAGE_MODEL = os.environ.get("SOCIAL_IMAGE_MODEL", "gpt-image-1.5").strip() or "gpt-image-1.5"
SOCIAL_IMAGE_TIMEOUT = int(os.environ.get("SOCIAL_IMAGE_TIMEOUT", "90"))
X_OAUTH_CLIENT_ID = os.environ.get("X_OAUTH_CLIENT_ID", "").strip()
X_OAUTH_CLIENT_SECRET = os.environ.get("X_OAUTH_CLIENT_SECRET", "").strip()
X_OAUTH_REFRESH_TOKEN_STORAGE = os.environ.get("X_OAUTH_REFRESH_TOKEN_STORAGE", "local_db").strip().lower() or "local_db"  # local_db only for runtime; Secret Manager is migration-only
X_OAUTH_REFRESH_TOKEN_LOCAL_KEY = os.environ.get("X_OAUTH_REFRESH_TOKEN_LOCAL_KEY", "x-official-oauth2-refresh-token").strip() or "x-official-oauth2-refresh-token"
OPS_LOCAL_SECRET_ENCRYPTION_KEY = os.environ.get("OPS_LOCAL_SECRET_ENCRYPTION_KEY", "").strip()
X_OAUTH_REDIRECT_URI = os.environ.get("X_OAUTH_REDIRECT_URI", "http://127.0.0.1:9600/api/social/x/oauth/callback").strip() or "http://127.0.0.1:9600/api/social/x/oauth/callback"
GMAIL_OAUTH_CLIENT_ID = os.environ.get("GMAIL_OAUTH_CLIENT_ID", "").strip()
GMAIL_OAUTH_CLIENT_SECRET = os.environ.get("GMAIL_OAUTH_CLIENT_SECRET", "").strip()
GMAIL_OAUTH_REFRESH_TOKEN_LOCAL_KEY = os.environ.get("GMAIL_OAUTH_REFRESH_TOKEN_LOCAL_KEY", "gmail-oauth-refresh-token").strip() or "gmail-oauth-refresh-token"
GMAIL_SENDER_EMAIL = os.environ.get("GMAIL_SENDER_EMAIL", "").strip()
SECRET_MANAGER_CLEANUP_PROJECTS = [
    item.strip()
    for item in os.environ.get("OPS_SECRET_MANAGER_CLEANUP_PROJECTS", "fabled-archive-494108-k5,synapse-network-prod").split(",")
    if item.strip()
]
SECRET_MANAGER_CLEANUP_KEEP_VERSIONS = max(1, int(os.environ.get("OPS_SECRET_MANAGER_CLEANUP_KEEP_VERSIONS", "2")))
ARTIFACT_REGISTRY_CLEANUP_PROJECTS = [
    item.strip()
    for item in os.environ.get("OPS_ARTIFACT_REGISTRY_CLEANUP_PROJECTS", "fabled-archive-494108-k5,synapse-network-prod").split(",")
    if item.strip()
]
ARTIFACT_REGISTRY_CLEANUP_REGION = os.environ.get("OPS_ARTIFACT_REGISTRY_CLEANUP_REGION", "us-central1").strip() or "us-central1"
ARTIFACT_REGISTRY_CLEANUP_REPOSITORY = os.environ.get("OPS_ARTIFACT_REGISTRY_CLEANUP_REPOSITORY", "synapse-staging").strip() or "synapse-staging"
ARTIFACT_REGISTRY_CLEANUP_KEEP_VERSIONS = max(1, int(os.environ.get("OPS_ARTIFACT_REGISTRY_CLEANUP_KEEP_VERSIONS", "3")))
ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS = max(0, int(os.environ.get("OPS_ARTIFACT_REGISTRY_CLEANUP_OLDER_THAN_DAYS", "0")))
ARTIFACT_REGISTRY_CLEANUP_TARGETS = _json_env_list(
    "OPS_ARTIFACT_REGISTRY_CLEANUP_TARGETS_JSON",
    [
        {
            "project": "fabled-archive-494108-k5",
            "region": ARTIFACT_REGISTRY_CLEANUP_REGION,
            "repository": ARTIFACT_REGISTRY_CLEANUP_REPOSITORY,
        },
        {
            "project": "synapse-network-prod",
            "region": ARTIFACT_REGISTRY_CLEANUP_REGION,
            "repository": "synapse-prod",
        },
    ],
)
STAGING_ENVIRONMENT_PROJECT = os.environ.get("OPS_STAGING_ENVIRONMENT_PROJECT", "fabled-archive-494108-k5").strip() or "fabled-archive-494108-k5"
STAGING_ENVIRONMENT_REGION = os.environ.get("OPS_STAGING_ENVIRONMENT_REGION", "us-central1").strip() or "us-central1"
STAGING_CLOUD_SQL_INSTANCE = os.environ.get("OPS_STAGING_CLOUD_SQL_INSTANCE", "synapse-staging-postgres").strip()
STAGING_CLOUD_RUN_SERVICES = [
    item.strip()
    for item in os.environ.get(
        "OPS_STAGING_CLOUD_RUN_SERVICES",
        "synapse-staging-gateway,synapse-staging-gateway-admin,synapse-staging-user-front,synapse-staging-admin-front,synapse-staging-docs-front,synapse-staging-provider",
    ).split(",")
    if item.strip()
]
MAX_CONTEXT_SIZE = int(os.environ.get("MAX_CONTEXT_SIZE", "500000"))
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE", "100000"))

# ── Orchestration ─────────────────────────────────────────────
ORCHESTRATION_BACKEND_OVERRIDE = os.environ.get("ORCHESTRATION_BACKEND", "").strip().lower()
PLANNER_BACKEND = os.environ.get("PLANNER_BACKEND", "").strip().lower()
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "").strip()
PLANNER_FALLBACK_MODEL = os.environ.get("PLANNER_FALLBACK_MODEL", "gpt-5.4,gpt-5.3-codex").strip()
PLANNER_TIMEOUT = int(os.environ.get("PLANNER_TIMEOUT", "300"))
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
CODEX_SDK_MODEL = os.environ.get("CODEX_SDK_MODEL", CODEX_CLI_MODEL or LLM_MODEL).strip()
CODEX_SDK_TIMEOUT = int(os.environ.get("CODEX_SDK_TIMEOUT", "0"))
CODEX_SDK_PLAN_TIMEOUT = int(os.environ.get("CODEX_SDK_PLAN_TIMEOUT", "300"))
CODEX_SDK_MAX_ACTIVE_SECONDS = max(0, int(os.environ.get("CODEX_SDK_MAX_ACTIVE_SECONDS", "7200")))
CODEX_SDK_STALE_AFTER_SEC = float(os.environ.get("CODEX_SDK_STALE_AFTER_SEC", "300"))
CODEX_SDK_SANDBOX = os.environ.get("CODEX_SDK_SANDBOX", "workspace-write").strip() or "workspace-write"
DELIVERY_VCS_TIMEOUT_SECONDS = max(1, int(os.environ.get("OPS_DELIVERY_VCS_TIMEOUT_SECONDS", "120")))
DELIVERY_VCS_REMOTE_NAME = os.environ.get("OPS_DELIVERY_VCS_REMOTE_NAME", "origin").strip() or "origin"
DELIVERY_PR_TIMEOUT_SECONDS = max(1, int(os.environ.get("OPS_DELIVERY_PR_TIMEOUT_SECONDS", "60")))
DELIVERY_PR_REMOTE_NAME = os.environ.get("OPS_DELIVERY_PR_REMOTE_NAME", DELIVERY_VCS_REMOTE_NAME).strip() or DELIVERY_VCS_REMOTE_NAME
DEPLOY_GITHUB_API_BASE_URL = os.environ.get("OPS_DEPLOY_GITHUB_API_BASE_URL", "https://api.github.com").strip() or "https://api.github.com"
DEPLOY_TIMEOUT_SECONDS = max(1, int(os.environ.get("OPS_DEPLOY_TIMEOUT_SECONDS", "60")))
DEPLOY_PUBLIC_BASE_URL = os.environ.get("OPS_DEPLOY_PUBLIC_BASE_URL", "").strip()
DEPLOY_WEBHOOK_TOKEN = os.environ.get("OPS_DEPLOY_WEBHOOK_TOKEN", "").strip()
RUNTIME_TIER_MINI_BACKEND = os.environ.get("OPS_RUNTIME_TIER_MINI_BACKEND", "").strip().lower()
RUNTIME_TIER_MINI_PROVIDER = os.environ.get("OPS_RUNTIME_TIER_MINI_PROVIDER", "").strip().lower()
RUNTIME_TIER_MINI_MODEL = os.environ.get("OPS_RUNTIME_TIER_MINI_MODEL", "").strip()
RUNTIME_TIER_STANDARD_BACKEND = os.environ.get("OPS_RUNTIME_TIER_STANDARD_BACKEND", "").strip().lower()
RUNTIME_TIER_STANDARD_PROVIDER = os.environ.get("OPS_RUNTIME_TIER_STANDARD_PROVIDER", "").strip().lower()
RUNTIME_TIER_STANDARD_MODEL = os.environ.get("OPS_RUNTIME_TIER_STANDARD_MODEL", "").strip()
RUNTIME_TIER_MAX_BACKEND = os.environ.get("OPS_RUNTIME_TIER_MAX_BACKEND", "").strip().lower()
RUNTIME_TIER_MAX_PROVIDER = os.environ.get("OPS_RUNTIME_TIER_MAX_PROVIDER", "").strip().lower()
RUNTIME_TIER_MAX_MODEL = os.environ.get("OPS_RUNTIME_TIER_MAX_MODEL", "").strip()
E2E_MODE = _OPS_E2E_MODE
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
SUPPORTED_ORCHESTRATION_BACKENDS = {"legacy", "copilot_sdk", "openai_responses", "codex_cli", "codex_sdk"}


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
