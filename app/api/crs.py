import json
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.projects import get_project_or_404, verify_team_membership
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.crs import CRSDocument, CRSStatus
from app.models.user import User
from app.services.crs_service import get_latest_crs, persist_crs_document, get_crs_versions, update_crs_status


router = APIRouter()


class CRSCreate(BaseModel):
    project_id: int
    content: str
    summary_points: List[str] = Field(default_factory=list)


class CRSStatusUpdate(BaseModel):
    """Schema for updating CRS status (approval workflow)."""
    status: str = Field(..., description="New status: draft, under_review, approved, rejected")


class CRSOut(BaseModel):
    id: int
    project_id: int
    status: str
    version: int
    content: str
    summary_points: List[str]
    created_by: Optional[int] = None
    approved_by: Optional[int] = None
    created_at: datetime

    class Config:
        orm_mode = True


@router.post("/", response_model=CRSOut, status_code=status.HTTP_201_CREATED)
def create_crs(
    payload: CRSCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create and persist a CRS document for a project.
    """
    project = get_project_or_404(db, payload.project_id)
    verify_team_membership(db, project.team_id, current_user.id)

    crs = persist_crs_document(
        db,
        project_id=payload.project_id,
        created_by=current_user.id,
        content=payload.content,
        summary_points=payload.summary_points,
    )

    return CRSOut(
        id=crs.id,
        project_id=crs.project_id,
        status=crs.status.value,
        version=crs.version,
        content=crs.content,
        summary_points=payload.summary_points,
        created_by=crs.created_by,
        approved_by=crs.approved_by,
        created_at=crs.created_at,
    )


@router.post("/draft", response_model=CRSOut, status_code=status.HTTP_201_CREATED)
def create_crs_draft(
    payload: CRSCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create and persist a draft CRS document for a project.
    """
    project = get_project_or_404(db, payload.project_id)
    verify_team_membership(db, project.team_id, current_user.id)

    crs = persist_crs_document(
        db,
        project_id=payload.project_id,
        created_by=current_user.id,
        content=payload.content,
        summary_points=payload.summary_points,
        store_embedding=False,  # Drafts may not need embeddings initially
    )

    return CRSOut(
        id=crs.id,
        project_id=crs.project_id,
        status=crs.status.value,
        version=crs.version,
        content=crs.content,
        summary_points=json.loads(crs.summary_points),
        created_by=crs.created_by,
        approved_by=crs.approved_by,
        created_at=crs.created_at,
    )


@router.get("/latest", response_model=Optional[CRSOut])
def read_latest_crs(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch the most recent CRS for a project.
    """
    project = get_project_or_404(db, project_id)
    verify_team_membership(db, project.team_id, current_user.id)

    crs = get_latest_crs(db, project_id=project_id)
    if not crs:
        return None

    try:
        summary_points = json.loads(crs.summary_points) if crs.summary_points else []
    except Exception:
        summary_points = []

    return CRSOut(
        id=crs.id,
        project_id=crs.project_id,
        status=crs.status.value,
        version=crs.version,
        content=crs.content,
        summary_points=summary_points,
        created_by=crs.created_by,
        approved_by=crs.approved_by,
        created_at=crs.created_at,
    )


@router.get("/versions", response_model=List[CRSOut])
def read_crs_versions(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch all CRS versions for a project, ordered by version descending (newest first).
    """
    project = get_project_or_404(db, project_id)
    verify_team_membership(db, project.team_id, current_user.id)

    versions = get_crs_versions(db, project_id=project_id)
    result = []
    for crs in versions:
        try:
            summary_points = json.loads(crs.summary_points) if crs.summary_points else []
        except Exception:
            summary_points = []
        result.append(CRSOut(
            id=crs.id,
            project_id=crs.project_id,
            status=crs.status.value,
            version=crs.version,
            content=crs.content,
            summary_points=summary_points,
            created_by=crs.created_by,
            approved_by=crs.approved_by,
            created_at=crs.created_at,
        ))
    return result


@router.put("/{crs_id}/status", response_model=CRSOut)
def update_crs_status_endpoint(
    crs_id: int,
    payload: CRSStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update the status of a CRS document (approval workflow).
    
    Status transitions:
    - draft -> under_review (Client submits for review)
    - under_review -> approved/rejected (BA reviews)
    - rejected -> draft (Client revises)
    """
    # Validate status value
    try:
        new_status = CRSStatus(payload.status)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {[s.value for s in CRSStatus]}"
        )

    # Get CRS and verify access
    crs = db.query(CRSDocument).filter(CRSDocument.id == crs_id).first()
    if not crs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="CRS document not found"
        )

    project = get_project_or_404(db, crs.project_id)
    verify_team_membership(db, project.team_id, current_user.id)

    # Update status using service function
    updated_crs = update_crs_status(
        db,
        crs_id=crs_id,
        new_status=new_status,
        approved_by=current_user.id if new_status == CRSStatus.approved else None,
    )

    try:
        summary_points = json.loads(updated_crs.summary_points) if updated_crs.summary_points else []
    except Exception:
        summary_points = []

    return CRSOut(
        id=updated_crs.id,
        project_id=updated_crs.project_id,
        status=updated_crs.status.value,
        version=updated_crs.version,
        content=updated_crs.content,
        summary_points=summary_points,
        created_by=updated_crs.created_by,
        approved_by=updated_crs.approved_by,
        created_at=updated_crs.created_at,
    )


@router.get("/draft/{project_id}", response_model=CRSOut)
def fetch_crs_draft(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Fetch the latest draft CRS document for a project.
    """
    project = get_project_or_404(db, project_id)
    verify_team_membership(db, project.team_id, current_user.id)

    latest_draft = db.query(CRSDocument).filter(
        CRSDocument.project_id == project_id,
        CRSDocument.status == CRSStatus.draft
    ).order_by(CRSDocument.version.desc()).first()

    if not latest_draft:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No draft CRS document found for this project."
        )

    return CRSOut(
        id=latest_draft.id,
        project_id=latest_draft.project_id,
        status=latest_draft.status.value,
        version=latest_draft.version,
        content=latest_draft.content,
        summary_points=json.loads(latest_draft.summary_points),
        created_by=latest_draft.created_by,
        approved_by=latest_draft.approved_by,
        created_at=latest_draft.created_at,
    )
