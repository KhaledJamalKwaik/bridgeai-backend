"""Service for handling team invitation business logic."""

from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from app.models.invitation import Invitation
from app.models.team import TeamMember, TeamRole
from app.models.user import User
from app.repositories.invitation_repository import InvitationRepository
from app.repositories.team_repository import TeamRepository, TeamMemberRepository
from app.schemas.invitation import (
    InvitationPublicOut,
    InvitationAcceptResponse,
)
from app.utils.invitation import (
    build_invitation_link,
    create_invitation,
    send_invitation_email_to_console,
)


class InvitationService:
    """Service for invitation-related operations."""

    @staticmethod
    def get_invitation_by_token(
        db: Session, token: str
    ) -> Optional[Invitation]:
        """
        Get invitation by token.

        Args:
            db: Database session
            token: Invitation token

        Returns:
            Invitation or None
        """
        repo = InvitationRepository(db)
        return repo.get_by_token(token)

    @staticmethod
    def check_invitation(db: Session, token: str):
        """
        Check invitation validity and user registration status.
        Used by frontend to determine if redirect to registration is needed.
        
        Args:
            db: Database session
            token: Invitation token
            
        Returns:
            Dictionary with invitation details and registration status
        """
        from app.repositories import UserRepository
        
        repo = InvitationRepository(db)
        invitation = repo.get_by_token(token)
        
        if not invitation:
            return {
                "valid": False,
                "error": "Invitation not found"
            }
        
        # Check if invitation is valid (not expired, status is pending)
        if not invitation.is_valid():
            return {
                "valid": False,
                "error": "Invitation has expired or is no longer valid"
            }
        
        # Check if user is registered
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(invitation.email)
        
        # Get team details
        team_repo = TeamRepository(db)
        team = team_repo.get_by_id(invitation.team_id)
        
        return {
            "valid": True,
            "email": invitation.email,
            "team_name": team.name if team else "Unknown",
            "inviter_name": invitation.inviter.full_name if invitation.inviter else "Unknown",
            "role": invitation.role,
            "user_registered": user is not None,
            "requires_registration": user is None,
        }


    @staticmethod
    def get_invitation_details(
        db: Session, token: str
    ) -> InvitationPublicOut:
        """
        Get invitation details for public display.

        Args:
            db: Database session
            token: Invitation token

        Returns:
            InvitationPublicOut schema

        Raises:
            ValueError: If invitation not found or invalid
        """
        repo = InvitationRepository(db)
        invitation = repo.get_by_token(token)

        if not invitation:
            raise ValueError("Invitation not found")

        # Check if expired and update status
        if invitation.is_expired():
            repo.update_status(invitation.id, "expired")
            raise ValueError("This invitation has expired")

        # Check if not pending
        if invitation.status != "pending":
            raise ValueError(f"This invitation is {invitation.status}")

        # Build response with sender and team info
        return InvitationPublicOut(
            email=invitation.email,
            role=invitation.role,
            team_id=invitation.team_id,
            team_name=invitation.team.name if invitation.team else None,
            team_description=invitation.team.description if invitation.team else None,
            status=invitation.status,
            created_at=invitation.created_at,
            expires_at=invitation.expires_at,
            invited_by_name=invitation.inviter.full_name if invitation.inviter else None,
            invited_by_email=invitation.inviter.email if invitation.inviter else None,
        )

    @staticmethod
    def accept_invitation(
        db: Session, token: str, current_user: User
    ) -> InvitationAcceptResponse:
        """
        Accept a team invitation.

        Args:
            db: Database session
            token: Invitation token
            current_user: User accepting the invitation

        Returns:
            InvitationAcceptResponse

        Raises:
            ValueError: If invitation not found, invalid, or user email mismatch
        """
        repo = InvitationRepository(db)
        team_member_repo = TeamMemberRepository(db)
        
        invitation = repo.get_by_token(token)

        if not invitation:
            raise ValueError("Invitation not found")

        # Validate invitation
        if not invitation.is_valid():
            if invitation.is_expired():
                repo.update_status(invitation.id, "expired")
                raise ValueError("This invitation has expired")
            raise ValueError(f"This invitation is {invitation.status}")

        # Check if user's email matches invitation
        if current_user.email.lower() != invitation.email.lower():
            raise ValueError("This invitation was sent to a different email address")

        # Check current team size - enforce 2-member limit
        active_member_count = team_member_repo.get_active_member_count(invitation.team_id)
        
        # Check if user is already a member
        existing_member = team_member_repo.get_by_team_and_user(invitation.team_id, current_user.id)

        if existing_member:
            if existing_member.is_active:
                raise ValueError("You are already a member of this team")
            else:
                # Check team size before reactivating
                # if active_member_count >= 2:
                #     raise ValueError("Team is at maximum capacity (2 members: Client + BA)")
                
                # Reactivate the member with role based on user's role
                existing_member.is_active = True
                # Assign role based on user's role (client or ba)
                team_role = TeamRole.client if current_user.role.value == "client" else TeamRole.ba
                existing_member.role = team_role
                db.commit()
                repo.update_status(invitation.id, "accepted")

                return InvitationAcceptResponse(
                    message="Invitation accepted and membership reactivated",
                    team_id=invitation.team_id,
                    role=team_role.value,
                )

        # Check team size before creating new member
        # if active_member_count >= 2:
        #     raise ValueError("Team is at maximum capacity (2 members: Client + BA)")

        # Create new team membership with role based on user's role
        team_role = TeamRole.client if current_user.role.value == "client" else TeamRole.ba
        new_member = TeamMember(
            team_id=invitation.team_id,
            user_id=current_user.id,
            role=team_role,
            is_active=True,
        )
        db.add(new_member)
        db.commit()

        # Update invitation status
        repo.update_status(invitation.id, "accepted")

        return InvitationAcceptResponse(
            message="Invitation accepted successfully",
            team_id=invitation.team_id,
            role=team_role.value,
        )

    @staticmethod
    def reject_invitation(
        db: Session, token: str, current_user: User
    ) -> dict:
        """
        Reject a team invitation.

        Args:
            db: Database session
            token: Invitation token
            current_user: User rejecting the invitation

        Returns:
            Success message dict

        Raises:
            ValueError: If invitation not found, invalid, or user email mismatch
        """
        repo = InvitationRepository(db)
        invitation = repo.get_by_token(token)

        if not invitation:
            raise ValueError("Invitation not found")

        # If expired, mark expired and fail
        if invitation.is_expired():
            if invitation.status == "pending":
                repo.update_status(invitation.id, "expired")
            raise ValueError("This invitation has expired")

        if invitation.status != "pending":
            raise ValueError(f"This invitation is {invitation.status}")

        if current_user.email.lower() != invitation.email.lower():
            raise ValueError("This invitation was sent to a different email address")

        repo.update_status(invitation.id, "canceled")

        return {"message": "Invitation rejected"}

    @staticmethod
    def create_team_invitation(
        db: Session,
        team_id: int,
        email: str,
        role: str,
        invited_by_id: int
    ) -> Invitation:
        """
        Create a new team invitation.

        Args:
            db: Database session
            team_id: Team ID
            email: Invitee email
            role: Role to assign
            invited_by_id: ID of user creating invitation

        Returns:
            Created Invitation

        Raises:
            ValueError: If invitation already exists or invalid parameters
        """
        repo = InvitationRepository(db)
        
        # Check if already invited
        existing = repo.get_by_team_and_email(team_id, email, status="pending")
        if existing:
            raise ValueError("User already has a pending invitation")

        # Use utility function to create invitation
        invitation = create_invitation(
            db=db,
            team_id=team_id,
            email=email,
            role=role,
            invited_by_id=invited_by_id
        )

        return invitation

    @staticmethod
    def get_team_invitations(
        db: Session,
        team_id: int,
        status: Optional[str] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Invitation]:
        """
        Get invitations for a team.

        Args:
            db: Database session
            team_id: Team ID
            status: Optional status filter
            skip: Number of records to skip
            limit: Maximum number of records

        Returns:
            List of invitations
        """
        repo = InvitationRepository(db)
        return repo.get_team_invitations(team_id, status, skip, limit)

    @staticmethod
    def cancel_invitation(
        db: Session, invitation_id: int
    ) -> Optional[Invitation]:
        """
        Cancel an invitation.

        Args:
            db: Database session
            invitation_id: Invitation ID

        Returns:
            Updated invitation or None
        """
        repo = InvitationRepository(db)
        return repo.update_status(invitation_id, "canceled")
