from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

# Get limiter from core
from app.core.rate_limit import limiter
from app.core.security import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.invitation import (
    InvitationAcceptResponse,
    InvitationPublicOut,
    InvitationResponse,
)
from app.services.invitation_service import InvitationService
from app.services import notification_service

router = APIRouter()


@router.get("/check/{token}")
@limiter.limit("10/minute")
def check_invitation(request: Request, token: str, db: Session = Depends(get_db)):
    """
    Check invitation validity and user registration status.
    Used by frontend to determine if user needs to register before accepting.
    Returns invitation details and whether user is registered.
    """
    result = InvitationService.check_invitation(db, token)
    return result


@router.get("/{token}", response_model=InvitationPublicOut)
@limiter.limit("10/minute")
def get_invitation(request: Request, token: str, db: Session = Depends(get_db)):
    """
    Get invitation details by token.
    This endpoint is public (no auth required) to show invite details.
    """
    try:
        return InvitationService.get_invitation_details(db, token)
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, 
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{token}/accept", response_model=InvitationAcceptResponse)
@limiter.limit("5/minute")
def accept_invitation(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Accept a team invitation.
    User must be authenticated and their email must match the invitation.
    """
    try:
        result = InvitationService.accept_invitation(db, token, current_user)
        
        # Notify team owner/admin about accepted invitation
        invitation = InvitationService.get_invitation_by_token(db, token)
        if invitation:
            notification_service.notify_invitation_accepted(
                db=db,
                team_id=invitation.team_id,
                acceptor_name=current_user.full_name,
                acceptor_email=current_user.email,
                role=invitation.role,
                commit=True,
            )
        
        return result
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "different email" in str(e):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.post("/{token}/reject")
@limiter.limit("5/minute")
def reject_invitation(
    request: Request,
    token: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject (decline) a team invitation.

    Marks the invitation as canceled. Requires authentication and the current
    user's email must match the invitation email.
    """
    try:
        result = InvitationService.reject_invitation(db, token, current_user)
        
        # Best-effort: mark any matching team invitation notifications as read
        invitation = InvitationService.get_invitation_by_token(db, token)
        if invitation:
            notification_service.mark_team_invitation_as_read(
                db=db,
                user_id=current_user.id,
                team_id=invitation.team_id
            )
        
        return result
    except ValueError as e:
        if "not found" in str(e):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(e)
            )
        elif "different email" in str(e):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
