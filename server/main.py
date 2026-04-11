"""FastAPI main application for Agentic Ops Dashboard."""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server import config
from server.database import init_db, get_db, AgentRow, TaskRow, ApprovalRow
from server.schemas import DashboardStats
from server.routers import agents, tasks, approvals, skills, copilot_auth, requirements
from server.services.org_builder import build_org_tree
from server.services.copilot_sdk_monitor import CopilotSDKTaskMonitor
from server.services.openai_responses_monitor import OpenAIResponsesTaskMonitor

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ops-dashboard")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Ops Dashboard (env=%s, port=%s)", config.ENV, config.PORT)
    init_db()
    logger.info("Database initialized")
    monitor = None
    if config.ORCHESTRATION_BACKEND.lower() == "copilot_sdk" and config.COPILOT_SDK_MONITOR_ENABLED:
        monitor = CopilotSDKTaskMonitor(project_root=config.PROJECT_ROOT)
        monitor.start()
        app.state.copilot_runtime_monitor = monitor
    elif config.ORCHESTRATION_BACKEND.lower() == "openai_responses" and config.OPENAI_RESPONSES_MONITOR_ENABLED:
        monitor = OpenAIResponsesTaskMonitor(project_root=config.PROJECT_ROOT)
        monitor.start()
        app.state.openai_runtime_monitor = monitor
    try:
        yield
    finally:
        if monitor is not None:
            monitor.stop()
        logger.info("Shutting down")


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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.debug("%s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.debug("%s %s → %s", request.method, request.url.path, response.status_code)
    return response


@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    return DashboardStats(
        agent_count=db.query(AgentRow).count(),
        task_total=db.query(TaskRow).count(),
        task_pending=db.query(TaskRow).filter(TaskRow.status == "pending").count(),
        task_running=db.query(TaskRow).filter(TaskRow.status.in_(["running", "pending_approval"])).count(),
        task_completed=db.query(TaskRow).filter(TaskRow.status == "completed").count(),
        task_failed=db.query(TaskRow).filter(TaskRow.status.in_(["failed", "rejected"])).count(),
        approval_pending=db.query(ApprovalRow).filter(ApprovalRow.status == "pending").count(),
    )


@app.get("/api/org")
def get_org_tree():
    """Return the full multi-project org tree."""
    return build_org_tree()


@app.get("/health")
def health():
    return {"status": "ok"}
