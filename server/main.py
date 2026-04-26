"""FastAPI main application for Agentic Ops Dashboard."""
import time
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from server import config
from server.database import (
    AgentRow,
    HumanGateRequestRow,
    RequirementRow,
    WorkflowRunRow,
    get_db,
    init_db,
)
from server.logging_utils import bind_context, clear_context, get_logger, log_event, setup_ops_logging
from server.schemas import DashboardStats
from server.routers import agents, skills, copilot_auth, requirements, project_policies, project_onboarding, optimization_signals, company_review, recurring_workflows, bugs, releases, errors, projects, workflows, planning, deployments, social
from server.services.agents.loader import ensure_agents_loaded
from server.services.bugs.log_scheduler import BugLogSweepScheduler
from server.services.planning.scheduler import GoalPlannerSweepScheduler
from server.services.releases.deployment_status_scheduler import ReleaseDeploymentStatusSweepScheduler
from server.services.releases.pr_status_scheduler import ReleasePrStatusSweepScheduler
from server.services.runtime.notification_dispatcher import NotificationDispatcher
from server.services.workflows.ci_scheduler import CiStatusSweepScheduler

setup_ops_logging(
    log_level=config.LOG_LEVEL,
    log_dir=config.LOG_DIR,
    log_file=config.LOG_FILE,
    backup_days=config.LOG_BACKUP_DAYS,
    service_name="ops-dashboard",
    env=config.ENV,
)
logger = get_logger("ops-dashboard")


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
    bug_scheduler = None
    goal_planner_scheduler = None
    ci_status_scheduler = None
    release_pr_status_scheduler = None
    release_deployment_status_scheduler = None  # pragma: no cover - lifespan wiring
    notification_dispatcher = None
    if config.BUG_LOG_SWEEP_SCHEDULER_ENABLED:
        bug_scheduler = BugLogSweepScheduler()
        bug_scheduler.start()
        app.state.bug_log_scheduler = bug_scheduler
    if config.GOAL_PLANNER_SWEEP_SCHEDULER_ENABLED:
        goal_planner_scheduler = GoalPlannerSweepScheduler()
        goal_planner_scheduler.start()
        app.state.goal_planner_scheduler = goal_planner_scheduler
    if config.CI_STATUS_SWEEP_SCHEDULER_ENABLED:
        ci_status_scheduler = CiStatusSweepScheduler()
        ci_status_scheduler.start()
        app.state.ci_status_scheduler = ci_status_scheduler
    if config.RELEASE_PR_STATUS_SWEEP_SCHEDULER_ENABLED:
        release_pr_status_scheduler = ReleasePrStatusSweepScheduler()
        release_pr_status_scheduler.start()
        app.state.release_pr_status_scheduler = release_pr_status_scheduler
    if config.RELEASE_DEPLOYMENT_STATUS_SWEEP_SCHEDULER_ENABLED:  # pragma: no cover - lifespan wiring
        release_deployment_status_scheduler = ReleaseDeploymentStatusSweepScheduler()
        release_deployment_status_scheduler.start()
        app.state.release_deployment_status_scheduler = release_deployment_status_scheduler
    if config.NOTIFICATION_DISPATCHER_ENABLED:
        notification_dispatcher = NotificationDispatcher()
        notification_dispatcher.start()
        app.state.notification_dispatcher = notification_dispatcher
    try:
        yield
    finally:
        if notification_dispatcher is not None:
            notification_dispatcher.stop()
        if release_pr_status_scheduler is not None:
            release_pr_status_scheduler.stop()
        if release_deployment_status_scheduler is not None:  # pragma: no cover - lifespan wiring
            release_deployment_status_scheduler.stop()
        if ci_status_scheduler is not None:
            ci_status_scheduler.stop()
        if goal_planner_scheduler is not None:
            goal_planner_scheduler.stop()
        if bug_scheduler is not None:
            bug_scheduler.stop()
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
app.include_router(skills.router)
app.include_router(copilot_auth.router)
app.include_router(requirements.router)
app.include_router(releases.router)
app.include_router(deployments.router)
app.include_router(errors.router)
app.include_router(projects.router)
app.include_router(project_policies.router)
app.include_router(project_onboarding.router)
app.include_router(optimization_signals.router)
app.include_router(company_review.router)
app.include_router(recurring_workflows.router)
app.include_router(bugs.router)
app.include_router(workflows.router)
app.include_router(planning.router)
app.include_router(social.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    bind_context(request_id=request_id)
    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        log_event(
            logger,
            "http_request_failed",
            level=40,
            exc_info=exc,
            method=request.method,
            path=request.url.path,
            query_string=str(request.url.query or ""),
            status=500,
            duration_ms=duration_ms,
            error_type=exc.__class__.__name__,
            error_message=str(exc),
        )
        raise
    finally:
        response = locals().get("response")
        if response is not None:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            level = 30 if duration_ms >= 2000 else 20
            log_event(
                logger,
                "http_request_completed",
                level=level,
                method=request.method,
                path=request.url.path,
                query_string=str(request.url.query or ""),
                status=response.status_code,
                duration_ms=duration_ms,
            )
            response.headers["X-Request-ID"] = request_id
        clear_context()
    return response


@app.get("/api/dashboard/stats", response_model=DashboardStats)
def dashboard_stats(db: Session = Depends(get_db)):
    ensure_agents_loaded(db)
    return DashboardStats(
        agent_count=db.query(AgentRow).count(),
        requirement_total=db.query(RequirementRow).count(),
        requirement_active=db.query(RequirementRow).filter(RequirementRow.status.notin_(["completed", "succeeded", "done", "cancelled", "deleted"])).count(),
        workflow_total=db.query(WorkflowRunRow).count(),
        workflow_running=db.query(WorkflowRunRow).filter(WorkflowRunRow.status.in_(["running", "paused"])).count(),
        workflow_succeeded=db.query(WorkflowRunRow).filter(WorkflowRunRow.status == "succeeded").count(),
        workflow_failed=db.query(WorkflowRunRow).filter(WorkflowRunRow.status == "failed").count(),
        human_gate_pending=db.query(HumanGateRequestRow).filter(HumanGateRequestRow.status == "pending").count(),
    )

@app.get("/health")
def health():
    return {"status": "ok"}
