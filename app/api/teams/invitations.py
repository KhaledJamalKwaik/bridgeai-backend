"""
Team Invitations Module.
Handles invitation operations within a team context.
"""
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.invitation import InvitationOut
from app.services.team_service import TeamService

router = APIRouter()


@router.post("/{team_id}/invitations", response_model=dict)
def invite_member(
    team_id: int,
    email: str,
    role: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Invite a user to the team."""
    return TeamService.invite_member(db, team_id, email, role, current_user)


@router.get("/{team_id}/invitations", response_model=List[InvitationOut])
def list_invitations(
    team_id: int,
    include_expired: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List pending invitations for the team."""
    return TeamService.list_invitations(db, team_id, current_user, include_expired)


@router.post("/{team_id}/invitations/{invitation_id}/cancel")
def cancel_invitation(
    team_id: int,
    invitation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending invitation."""
    result = TeamService.cancel_invitation(db, team_id, invitation_id, current_user)
    db.commit()
    return result
