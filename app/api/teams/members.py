"""
Team Members Module.
Handles team member management operations.
Refactored to use TeamService following service layer architecture.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.team import (
    TeamMemberCreate,
    TeamMemberDetailOut,
    TeamMemberUpdate,
)
from app.services.team_service import TeamService

router = APIRouter()


@router.post("/{team_id}/members", response_model=TeamMemberDetailOut)
def add_team_member(
    team_id: int,
    payload: TeamMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a member to the team. Only owners and admins can add members."""
    member = TeamService.add_member(db, team_id, payload.user_id, payload.role, current_user)
    db.commit()
    db.refresh(member)
    return member


@router.get("/{team_id}/members", response_model=List[TeamMemberDetailOut])
def list_team_members(
    team_id: int,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List team members. Only team members can view the member list."""
    return TeamService.list_members(db, team_id, current_user, include_inactive)


@router.put("/{team_id}/members/{member_id}", response_model=TeamMemberDetailOut)
def update_team_member(
    team_id: int,
    member_id: int,
    payload: TeamMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update team member role or status. Only owners and admins can update members."""
    update_data = payload.dict(exclude_unset=True)
    member = TeamService.update_member(
        db,
        team_id,
        member_id,
        current_user,
        role=update_data.get("role"),
        is_active=update_data.get("is_active"),
    )
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{team_id}/members/{member_id}")
def remove_team_member(
    team_id: int,
    member_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove a member from the team. Only owners and admins can remove members."""
    result = TeamService.remove_member(db, team_id, member_id, current_user)
    db.commit()
    return result
