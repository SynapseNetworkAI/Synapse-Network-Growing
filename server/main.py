"""FastAPI main application for Agentic Ops Dashboard."""
import logging
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server import config
from server.database import init_db, get_db, AgentRow, TaskRow, ApprovalRow
from server.logging_utils import log_event, setup_ops_logging
from server.schemas import DashboardStats
from server.routers import agents, tasks, approvals, skills, copilot_auth, requirements, project_policies, project_onboarding, optimization_signals, company_review, recurring_workflows, bugs, deployments
from server.services.agents.loader import ensure_agents_loaded
from server.services.bugs.log_scheduler import BugLogSweepScheduler
from server.services.runtime.codex_cli_monitor import CodexCLITaskMonitor
from server.services.runtime.copilot_sdk_monitor import CopilotSDKTaskMonitor
from server.services.runtime.openai_responses_monitor import OpenAIResponsesTaskMonitor

setup_ops_logging(
    log_level=config.LOG_LEVEL,
    log_dir=config.LOG_DIR,
    log_file=config.LOG_FILE,
    max_bytes=config.LOG_MAX_BYTES,
    backup_count=config.LOG_BACKUP_COUNT,
)
logger = logging.getLogger("ops-dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_event(
        logger,
        "service_starting",
        env=config.ENV,
        port=config.PORT,
        db_path=config.DB_PATH,
        orchestration_backend=config.ORCHESTRATION_BACKEND,
        log_file=f"{config.LOG_DIR}/{config.LOG_FILE}",
    )
    init_db()
    log_event(logger, "database_initialized", db_path=config.DB_PATH)
    monitor = None
    bug_scheduler = None
    if config.ORCHESTRATION_BACKEND.lower() == "copilot_sdk" and config.COPILOT_SDK_MONITOR_ENABLED:
        monitor = CopilotSDKTaskMonitor(project_root=config.PROJECT_ROOT)
        monitor.start()
        app.state.copilot_runtime_monitor = monitor
    elif config.ORCHESTRATION_BACKEND.lower() == "codex_cli" and config.CODEX_CLI_MONITOR_ENABLED:
        monitor = CodexCLITaskMonitor(project_root=config.PROJECT_ROOT)
        monitor.start()
        app.state.codex_runtime_monitor = monitor
    elif config.ORCHESTRATION_BACKEND.lower() == "openai_responses" and config.OPENAI_RESPONSES_MONITOR_ENABLED:
        monitor = OpenAIResponsesTaskMonitor(project_root=config.PROJECT_ROOT)
        monitor.start()
        app.state.openai_runtime_monitor = monitor
    if config.BUG_LOG_SWEEP_SCHEDULER_ENABLED:
        bug_scheduler = BugLogSweepScheduler()
        bug_scheduler.start()
        app.state.bug_log_scheduler = bug_scheduler
    try:
        yield
    finally:
        if bug_scheduler is not None:
            bug_scheduler.stop()
        if monitor is not None:
            monitor.stop()
        log_event(logger, "service_stopped")


app = FastAPI(title="Synapse Agentic Ops Dashboard", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(agents.router)
app.include_router(tasks.router)
app.include_router(approvals.router)
app.include_router(skills.router)
app.include_router(copilot_auth.router)
app.include_router(requirements.router)
app.include_router(project_policies.router)
app.include_router(deployments.router)
app.include_router(project_onboarding.router)
app.include_router(optimization_signals.router)
app.include_router(company_review.router)
app.include_router(recurring_workflows.router)
app.include_router(bugs.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            logger,
            "http_request",
            level=logging.ERROR,
            exc_info=exc,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            query=str(request.url.query or ""),
            status=500,
            duration_ms=duration_ms,
            error_type=exc.__class__.__name__,
            error=str(exc),
        )
        raise
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    level = logging.WARNING if duration_ms >= 2000 else logging.INFO
    log_event(
        logger,
        "http_request",
        level=level,
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        query=str(request.url.query or ""),
        status=response.status_code,
        duration_ms=duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    return response


@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    ensure_agents_loaded(db)
    return DashboardStats(
        agent_count=db.query(AgentRow).count(),
        task_total=db.query(TaskRow).count(),
        task_pending=db.query(TaskRow).filter(TaskRow.status == "pending").count(),
        task_running=db.query(TaskRow).filter(TaskRow.status.in_(["running", "pending_approval"])).count(),
        task_completed=db.query(TaskRow).filter(TaskRow.status == "completed").count(),
        task_failed=db.query(TaskRow).filter(TaskRow.status.in_(["failed", "rejected"])).count(),
        approval_pending=db.query(ApprovalRow).filter(ApprovalRow.status == "pending").count(),
    )

@app.get("/health")
def health():
    return {"status": "ok"}
