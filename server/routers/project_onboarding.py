"""Project onboarding API."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from server.database import get_db
from server.schemas import ProjectOnboardingCreate, ProjectOnboardingOut
from server.services.projects.onboarding import create_project_onboarding, list_project_onboardings, project_onboarding_to_dict


router = APIRouter(prefix="/api/project-onboarding", tags=["project-onboarding"])


@router.get("", response_model=list[ProjectOnboardingOut])
def list_project_onboardings_endpoint(db: Session = Depends(get_db)):
    return [ProjectOnboardingOut(**project_onboarding_to_dict(row)) for row in list_project_onboardings(db)]


@router.post("", response_model=ProjectOnboardingOut, status_code=201)
def create_project_onboarding_endpoint(body: ProjectOnboardingCreate, db: Session = Depends(get_db)):
    if body.release_mode not in {"disabled", "manual", "auto"}:
        raise HTTPException(status_code=400, detail="release_mode must be disabled|manual|auto")
    if not body.project_key.strip() or not body.display_name.strip() or not body.root_path.strip():
        raise HTTPException(status_code=400, detail="project_key, display_name, and root_path are required")
    try:
        row = create_project_onboarding(
            db,
            project_key=body.project_key,
            display_name=body.display_name,
            root_path=body.root_path,
            docs_entrypoints=body.docs_entrypoints,
            validation_commands=body.validation_commands,
            agents_memory_namespace=body.agents_memory_namespace,
            auto_create_policy=body.auto_create_policy,
            allowed_write_globs=body.allowed_write_globs,
            forbidden_globs=body.forbidden_globs,
            release_mode=body.release_mode,
            requires_manual_approval=body.requires_manual_approval,
            notes=body.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ProjectOnboardingOut(**project_onboarding_to_dict(row))
