"""
Permission Service - Centralized Authorization Logic

This service encapsulates all permission and authorization checks
to eliminate code duplication and enforce consistent access control
across the application.

SOLID Principles:
- Single Responsibility: Only handles authorization/permission logic
- Open/Closed: Easy to extend with new permission checks
- Dependency Inversion: Routes depend on this abstraction, not repositories
"""

from typing import Optional, List
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.models.user import User, UserRole
from app.models.team import Team, TeamMember, TeamRole
from app.models.project import Project
from app.models.crs import CRSDocument, CRSStatus
from app.models.notification import Notification
from app.repositories.user_repository import UserRepository
from app.repositories.team_repository import TeamRepository, TeamMemberRepository
from app.repositories.project_repository import ProjectRepository
from app.repositories.crs_repository import CRSRepository
from app.repositories.notification_repository import NotificationRepository


class PermissionService:
    """
    Centralized service for all permission and authorization checks.

    This service provides a consistent interface for verifying user permissions
    across teams, projects, CRS documents, and other resources.
    """

    # ========================================
    # TEAM PERMISSION METHODS
    # ========================================

    @staticmethod
    def verify_team_membership(
        db: Session,
        team_id: int,
        user_id: int,
        required_roles: Optional[List[TeamRole]] = None,
    ) -> TeamMember:
        """
        Verify user is an active member of a team.

        Args:
            db: Database session
            team_id: Team ID to check membership for
            user_id: User ID to verify
            required_roles: Optional list of required roles (owner, admin, member)

        Returns:
            TeamMember object if authorized

        Raises:
            HTTPException 403: If user is not a member or lacks required role
        """
        team_member_repo = TeamMemberRepository(db)
        team_member = team_member_repo.get_by_team_and_user(team_id, user_id)

        if not team_member or not team_member.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You must be a member of this team",
            )

        if required_roles and team_member.role not in required_roles:
            role_names = ", ".join([r.value for r in required_roles])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires one of these roles: {role_names}",
            )

        return team_member

    @staticmethod
    def verify_team_admin(
        db: Session,
        team_id: int,
        user_id: int,
    ) -> TeamMember:
        """
        Verify user is a Business Analyst in the team OR the Team Creator.
        Team creators should always have admin rights.
        """
        # First check if user is the team creator/owner
        team_repo = TeamRepository(db)
        team = team_repo.get_by_id(team_id)
        if team and team.created_by == user_id:
            # If user is the creator, they are authorized. 
            # We still return the team member object for consistency
            team_member_repo = TeamMemberRepository(db)
            team_member = team_member_repo.get_by_team_and_user(team_id, user_id)
            if team_member:
                return team_member

        team_member_repo = TeamMemberRepository(db)
        team_member = team_member_repo.get_by_team_and_user(team_id, user_id)

        if (
            not team_member
            or not team_member.is_active
            or team_member.role != TeamRole.ba
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Only Business Analysts or Team Owners can perform this action.",
            )

        return team_member

    @staticmethod
    def verify_team_owner(
        db: Session,
        team_id: int,
        user_id: int,
    ) -> TeamMember:
        """
        Verify user is a Business Analyst in the team.
        In the new model, BAs have equivalent permissions to what owners had.

        Args:
            db: Database session
            team_id: Team ID to check
            user_id: User ID to verify

        Returns:
            TeamMember object if authorized

        Raises:
            HTTPException 403: If user is not a BA in the team
        """
        team_member_repo = TeamMemberRepository(db)
        team_member = team_member_repo.get_by_team_and_user(team_id, user_id)

        if (
            not team_member
            or not team_member.is_active
            or team_member.role != TeamRole.ba
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. Only Business Analysts can perform this action.",
            )

        return team_member

    # ========================================
    # USER ROLE PERMISSION METHODS
    # ========================================

    @staticmethod
    def verify_ba_role(user: User) -> None:
        """
        Verify user has the Business Analyst role.

        Args:
            user: Current user object

        Raises:
            HTTPException 403: If user is not a Business Analyst
        """
        if user.role != UserRole.ba:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Business Analysts can perform this action",
            )

    @staticmethod
    def verify_ba_access(db: Session, team_id: int, user_id: int) -> TeamMember:
        """
        Verify user is a Business Analyst with access to a team.

        Args:
            db: Database session
            team_id: Team ID to check access for
            user_id: User ID to verify

        Returns:
            TeamMember object if authorized

        Raises:
            HTTPException 403: If user is not a BA or not a member of the team
        """
        # Get user to verify BA role
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User not found",
            )

        # Verify BA role
        PermissionService.verify_ba_role(user)

        # Verify team membership
        return PermissionService.verify_team_membership(db, team_id, user_id)

    # ========================================
    # PROJECT PERMISSION METHODS
    # ========================================

    @staticmethod
    def verify_project_access(
        db: Session,
        project_id: int,
        user_id: int,
    ) -> Project:
        """
        Verify user has access to a project via team membership.

        Args:
            db: Database session
            project_id: Project ID to check
            user_id: User ID to verify

        Returns:
            Project object if authorized

        Raises:
            HTTPException 404: If project not found
            HTTPException 403: If user not a member of project's team
        """
        project = PermissionService.get_project_or_404(db, project_id)

        # Verify team membership
        PermissionService.verify_team_membership(
            db=db,
            team_id=project.team_id,
            user_id=user_id,
        )

        return project

    @staticmethod
    def verify_project_ownership(
        db: Session,
        project_id: int,
        user: User,
        allow_ba: bool = True,
    ) -> Project:
        """
        Verify user is the project creator or (optionally) a Business Analyst.

        Args:
            db: Database session
            project_id: Project ID to check
            user: Current user object
            allow_ba: Whether to allow BA access (default: True)

        Returns:
            Project object if authorized

        Raises:
            HTTPException 404: If project not found
            HTTPException 403: If user is neither creator nor BA
        """
        project = PermissionService.get_project_or_404(db, project_id)

        is_creator = user.id == project.created_by
        is_ba = user.role == UserRole.ba

        if not is_creator and not (allow_ba and is_ba):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the project creator or Business Analysts can perform this action",
            )

        return project

    # ========================================
    # CRS PERMISSION METHODS
    # ========================================

    @staticmethod
    def verify_crs_access(
        db: Session,
        crs_id: int,
        user_id: int,
    ) -> CRSDocument:
        """
        Verify user has access to a CRS document via project team membership.

        Args:
            db: Database session
            crs_id: CRS document ID to check
            user_id: User ID to verify

        Returns:
            CRSDocument object if authorized

        Raises:
            HTTPException 404: If CRS not found
            HTTPException 403: If user not a member of the project's team
        """
        crs_repo = CRSRepository(db)
        crs = crs_repo.get_by_id(crs_id)
        if not crs:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="CRS document not found",
            )

        # Verify access via project
        PermissionService.verify_project_access(
            db=db,
            project_id=crs.project_id,
            user_id=user_id,
        )

        return crs

    @staticmethod
    def verify_crs_approval_authority(
        db: Session,
        project_id: int,
        user: User,
    ) -> None:
        """
        Verify user can approve/reject CRS documents (BA or team admin).

        Args:
            db: Database session
            project_id: Project ID the CRS belongs to
            user: Current user object

        Raises:
            HTTPException 403: If user is neither BA nor team admin
        """
        # Check if user is BA
        if user.role == UserRole.ba:
            return

        # Check if user is team BA (Business Analyst)
        project = PermissionService.get_project_or_404(db, project_id)
        team_member_repo = TeamMemberRepository(db)
        team_member = team_member_repo.get_by_team_and_user(project.team_id, user.id)

        is_ba = team_member and team_member.role == TeamRole.ba

        if not is_ba:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only Business Analysts or team admins can approve/reject CRS documents",
            )

    @staticmethod
    def verify_crs_editable(crs: CRSDocument) -> None:
        """
        Verify CRS document can be edited (not approved).

        Args:
            crs: CRS document to check

        Raises:
            HTTPException 400: If CRS is approved and cannot be edited
        """
        if crs.status == CRSStatus.approved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot edit an approved CRS. Please change status to 'under review' or 'draft' first.",
            )

    # ========================================
    # NOTIFICATION PERMISSION METHODS
    # ========================================

    @staticmethod
    def verify_notification_ownership(
        db: Session,
        notification_id: int,
        user_id: int,
    ) -> Notification:
        """
        Verify user owns a notification.

        Args:
            db: Database session
            notification_id: Notification ID to check
            user_id: User ID to verify

        Returns:
            Notification object if authorized

        Raises:
            HTTPException 404: If notification not found or not owned by user
        """
        notification_repo = NotificationRepository(db)
        notification = notification_repo.get_by_id(notification_id)

        if not notification or notification.user_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Notification not found",
            )

        return notification

    # ========================================
    # HELPER METHODS (GET OR 404)
    # ========================================

    @staticmethod
    def get_team_or_404(db: Session, team_id: int) -> Team:
        """
        Get team by ID or raise 404.

        Args:
            db: Database session
            team_id: Team ID to retrieve

        Returns:
            Team object

        Raises:
            HTTPException 404: If team not found
        """
        team_repo = TeamRepository(db)
        team = team_repo.get_by_id(team_id)
        if not team:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Team not found",
            )
        return team

    @staticmethod
    def get_project_or_404(db: Session, project_id: int) -> Project:
        """
        Get project by ID or raise 404.

        Args:
            db: Database session
            project_id: Project ID to retrieve

        Returns:
            Project object

        Raises:
            HTTPException 404: If project not found
        """
        project_repo = ProjectRepository(db)
        project = project_repo.get_by_id(project_id)
        if not project:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Project not found",
            )
        return project

    # ========================================
    # UTILITY METHODS
    # ========================================

    @staticmethod
    def get_user_team_ids(db: Session, user_id: int) -> List[int]:
        """
        Get all team IDs user is an active member of.

        Args:
            db: Database session
            user_id: User ID to get teams for

        Returns:
            List of team IDs
        """
        team_member_repo = TeamMemberRepository(db)
        # Get all team members for this user
        team_members = (
            db.query(TeamMember)
            .filter(
                TeamMember.user_id == user_id,
                TeamMember.is_active == True,
            )
            .all()
        )
        return [tm.team_id for tm in team_members]

    @staticmethod
    def check_duplicate_project_name(
        db: Session,
        name: str,
        team_id: int,
        exclude_id: Optional[int] = None,
    ) -> None:
        """
        Check if project name already exists in team.

        Args:
            db: Database session
            name: Project name to check
            team_id: Team ID to check within
            exclude_id: Optional project ID to exclude from check (for updates)

        Raises:
            HTTPException 400: If duplicate name exists
        """
        project_repo = ProjectRepository(db)
        existing = project_repo.get_by_name_and_team(name, team_id, exclude_id)

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="A project with this name already exists in this team",
            )
