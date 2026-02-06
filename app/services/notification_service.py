"""
Notification service for all application events.
Centralizes notification creation for consistency and maintainability.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.crs import CRSDocument
from app.models.notification import Notification, NotificationType
from app.models.project import Project
from app.models.user import User
from app.utils.email import send_email
from app.repositories.user_repository import UserRepository


def create_notification(
    db: Session,
    user_id: int,
    notification_type: str,
    reference_id: int,
    title: str,
    message: str,
    meta_data: Optional[dict] = None,
    commit: bool = True,
) -> Notification:
    """
    Create an in-app notification.
    
    Args:
        db: Database session
        user_id: ID of user to notify
        notification_type: Type of notification (string or NotificationType enum)
        reference_id: ID of the related entity (project, team, etc.)
        title: Notification title
        message: Notification message
        meta_data: Additional metadata
        commit: Whether to commit immediately (default True)
        
    Returns:
        Created Notification object
    """
    notification = Notification(
        user_id=user_id,
        type=notification_type,
        reference_id=reference_id,
        title=title,
        message=message,
        meta_data=meta_data or {},
    )
    db.add(notification)
    if commit:
        db.commit()
        db.refresh(notification)
    return notification


# ==================== Project Notifications ====================


def notify_project_approval_requested(
    db: Session,
    project_id: int,
    project_name: str,
    requester_name: str,
    ba_user_ids: List[int],
    commit: bool = True,
) -> List[Notification]:
    """Notify BAs when a client requests project approval."""
    notifications = []
    for ba_user_id in ba_user_ids:
        notif = create_notification(
            db=db,
            user_id=ba_user_id,
            notification_type=NotificationType.PROJECT_APPROVAL,
            reference_id=project_id,
            title="New Project Request",
            message=f"{requester_name} has requested approval for project '{project_name}'.",
            commit=False,
        )
        notifications.append(notif)
    
    if commit:
        db.commit()
        for notif in notifications:
            db.refresh(notif)
    
    return notifications


def notify_project_approved(
    db: Session,
    project_id: int,
    project_name: str,
    approver_name: str,
    creator_user_id: int,
    commit: bool = True,
) -> Notification:
    """Notify project creator when project is approved."""
    return create_notification(
        db=db,
        user_id=creator_user_id,
        notification_type=NotificationType.PROJECT_APPROVAL,
        reference_id=project_id,
        title="Project Approved",
        message=f"Your project '{project_name}' has been approved by {approver_name}.",
        commit=commit,
    )


def notify_project_rejected(
    db: Session,
    project_id: int,
    project_name: str,
    rejector_name: str,
    rejection_reason: str,
    creator_user_id: int,
    commit: bool = True,
) -> Notification:
    """Notify project creator when project is rejected."""
    return create_notification(
        db=db,
        user_id=creator_user_id,
        notification_type=NotificationType.PROJECT_APPROVAL,
        reference_id=project_id,
        title="Project Rejected",
        message=f"Your project '{project_name}' was rejected by {rejector_name}. Reason: {rejection_reason}",
        commit=commit,
    )


# ==================== Team Notifications ====================


def notify_team_invitation(
    db: Session,
    team_id: int,
    team_name: str,
    inviter_name: str,
    role: str,
    invited_user_id: int,
    commit: bool = True,
) -> Notification:
    """Notify user when invited to a team."""
    return create_notification(
        db=db,
        user_id=invited_user_id,
        notification_type=NotificationType.TEAM_INVITATION,
        reference_id=team_id,
        title="Team Invitation",
        message=f"{inviter_name} has invited you to join the team '{team_name}' as {role}.",
        commit=commit,
    )


def notify_invitation_accepted(
    db: Session,
    team_id: int,
    acceptor_name: str,
    acceptor_email: str,
    role: str,
    commit: bool = True,
) -> Notification:
    """Notify team owner when someone accepts invitation."""
    from app.models.team import Team
    
    # Get team creator (owner)
    team = db.query(Team).filter(Team.id == team_id).first()
    if not team or not team.created_by:
        return None
    
    return create_notification(
        db=db,
        user_id=team.created_by,
        notification_type=NotificationType.TEAM_INVITATION,
        reference_id=team_id,
        title="New Team Member",
        message=f"{acceptor_name} ({acceptor_email}) has joined the team as {role}.",
        commit=commit,
    )


def mark_team_invitation_as_read(
    db: Session,
    user_id: int,
    team_id: int
) -> None:
    """Mark team invitation notifications as read."""
    db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == NotificationType.TEAM_INVITATION,
        Notification.reference_id == team_id,
        Notification.is_read == False,
    ).update({"is_read": True})
    db.commit()


def send_crs_notification_email(
    to_email: str,
    subject: str,
    event_type: str,
    crs_id: int,
    project_name: str,
    details: str,
):
    """Send CRS notification email."""
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <table width="600" style="background-color: #ffffff; margin: 0 auto; border-radius: 8px; overflow: hidden;">
            <tr>
                <td style="background-color: #341bab; padding: 30px; text-align: center;">
                    <h1 style="color: #ffffff; margin: 0;">BridgeAI</h1>
                </td>
            </tr>
            <tr>
                <td style="padding: 40px 30px;">
                    <h2 style="color: #333333; margin: 0 0 20px 0;">{event_type}</h2>
                    <p style="color: #666666; font-size: 16px; line-height: 1.6;">
                        <strong>Project:</strong> {project_name}<br>
                        <strong>CRS ID:</strong> #{crs_id}
                    </p>
                    <p style="color: #666666; font-size: 16px; line-height: 1.6; margin: 20px 0;">
                        {details}
                    </p>
                    <table width="100%" style="margin-top: 30px;">
                        <tr>
                            <td align="center">
                                <a href="{details}" 
                                   style="display: inline-block; padding: 15px 40px; background-color: #341bab; color: #ffffff; text-decoration: none; border-radius: 5px; font-weight: bold;">
                                    View CRS Document
                                </a>
                            </td>
                        </tr>
                    </table>
                </td>
            </tr>
            <tr>
                <td style="background-color: #f8f8f8; padding: 20px; text-align: center; border-top: 1px solid #eeeeee;">
                    <p style="color: #999999; font-size: 12px; margin: 0;">© 2025 BridgeAI. All rights reserved.</p>
                </td>
            </tr>
        </table>
    </body>
    </html>
    """

    text_content = (
        f"{event_type}\n\nProject: {project_name}\nCRS ID: #{crs_id}\n\n{details}"
    )

    send_email(to_email, subject, html_content, text_content)


def notify_crs_created(
    db: Session,
    crs: CRSDocument,
    project: Project,
    notify_users: List[int],
    send_email_notification: bool = True,
):
    """Notify users when a CRS is created."""
    user_repo = UserRepository(db)
    for user_id in notify_users:
        user = user_repo.get_by_id(user_id)
        if not user:
            continue

        create_notification(
            db=db,
            user_id=user_id,
            notification_type="crs_created",
            reference_id=crs.id,
            title="New CRS Document Created",
            message=f"A new CRS document has been created for project '{project.name}'",
            meta_data={
                "project_id": project.id,
                "project_name": project.name,
                "crs_id": crs.id,
                "team_id": project.team_id,
            },
        )

        if send_email_notification:
            send_crs_notification_email(
                to_email=user.email,
                subject=f"New CRS Document - {project.name}",
                event_type="New CRS Document Created",
                crs_id=crs.id,
                project_name=project.name,
                details=f"A new CRS document (version {crs.version}) has been created for your project.",
            )


def notify_crs_updated(
    db: Session,
    crs: CRSDocument,
    project: Project,
    notify_users: List[int],
    send_email_notification: bool = True,
):
    """Notify users when a CRS is updated."""
    user_repo = UserRepository(db)
    for user_id in notify_users:
        user = user_repo.get_by_id(user_id)
        if not user:
            continue

        create_notification(
            db=db,
            user_id=user_id,
            notification_type="crs_updated",
            reference_id=crs.id,
            title="CRS Document Updated",
            message=f"CRS document for project '{project.name}' has been updated",
            meta_data={
                "project_id": project.id,
                "project_name": project.name,
                "crs_id": crs.id,
                "team_id": project.team_id,
            },
        )

        if send_email_notification:
            send_crs_notification_email(
                to_email=user.email,
                subject=f"CRS Updated - {project.name}",
                event_type="CRS Document Updated",
                crs_id=crs.id,
                project_name=project.name,
                details=f"The CRS document (version {crs.version}) has been updated.",
            )


def notify_crs_status_changed(
    db: Session,
    crs: CRSDocument,
    project: Project,
    old_status: str,
    new_status: str,
    notify_users: List[int],
    send_email_notification: bool = True,
):
    """Notify users when CRS status changes."""
    user_repo = UserRepository(db)
    for user_id in notify_users:
        user = user_repo.get_by_id(user_id)
        if not user:
            continue

        create_notification(
            db=db,
            user_id=user_id,
            notification_type="crs_status_changed",
            reference_id=crs.id,
            title="CRS Status Changed",
            message=f"CRS status changed from '{old_status}' to '{new_status}' for project '{project.name}'",
            meta_data={
                "project_id": project.id,
                "project_name": project.name,
                "crs_id": crs.id,
                "status": new_status,
                "team_id": project.team_id,
            },
        )

        if send_email_notification:
            send_crs_notification_email(
                to_email=user.email,
                subject=f"CRS Status Changed - {project.name}",
                event_type="CRS Status Changed",
                crs_id=crs.id,
                project_name=project.name,
                details=f"Status changed from '{old_status}' to '{new_status}'.",
            )


def notify_crs_comment_added(
    db: Session,
    crs: CRSDocument,
    project: Project,
    comment_author: User,
    notify_users: List[int],
    send_email_notification: bool = True,
):
    """Notify users when a comment is added to CRS."""
    user_repo = UserRepository(db)
    for user_id in notify_users:
        if user_id == comment_author.id:
            continue

        user = user_repo.get_by_id(user_id)
        if not user:
            continue

        create_notification(
            db=db,
            user_id=user_id,
            notification_type="crs_comment_added",
            reference_id=crs.id,
            title="New Comment on CRS",
            message=f"{comment_author.full_name} added a comment on CRS for project '{project.name}'",
            meta_data={
                "project_id": project.id,
                "project_name": project.name,
                "crs_id": crs.id,
                "team_id": project.team_id,
            },
        )

        if send_email_notification:
            send_crs_notification_email(
                to_email=user.email,
                subject=f"New Comment - {project.name}",
                event_type="New Comment Added",
                crs_id=crs.id,
                project_name=project.name,
                details=f"{comment_author.full_name} added a comment to the CRS document.",
            )


def notify_crs_approved(
    db: Session,
    crs: CRSDocument,
    project: Project,
    approver: User,
    notify_users: List[int],
    send_email_notification: bool = True,
):
    """Notify users when CRS is approved."""
    user_repo = UserRepository(db)
    for user_id in notify_users:
        user = user_repo.get_by_id(user_id)
        if not user:
            continue

        create_notification(
            db=db,
            user_id=user_id,
            notification_type="crs_approved",
            reference_id=crs.id,
            title="CRS Document Approved",
            message=f"CRS for project '{project.name}' has been approved by {approver.full_name}",
            meta_data={
                "project_id": project.id,
                "project_name": project.name,
                "crs_id": crs.id,
                "status": "approved",
                "team_id": project.team_id,
            },
        )

        if send_email_notification:
            send_crs_notification_email(
                to_email=user.email,
                subject=f"CRS Approved - {project.name}",
                event_type="CRS Document Approved",
                crs_id=crs.id,
                project_name=project.name,
                details=f"Your CRS document has been approved by {approver.full_name}.",
            )


def notify_crs_rejected(
    db: Session,
    crs: CRSDocument,
    project: Project,
    rejector: User,
    notify_users: List[int],
    send_email_notification: bool = True,
):
    """Notify users when CRS is rejected."""
    user_repo = UserRepository(db)
    for user_id in notify_users:
        user = user_repo.get_by_id(user_id)
        if not user:
            continue

        create_notification(
            db=db,
            user_id=user_id,
            notification_type="crs_rejected",
            reference_id=crs.id,
            title="CRS Document Rejected",
            message=f"CRS for project '{project.name}' has been rejected by {rejector.full_name}",
            meta_data={
                "project_id": project.id,
                "project_name": project.name,
                "crs_id": crs.id,
                "status": "rejected",
                "team_id": project.team_id,
            },
        )

        if send_email_notification:
            send_crs_notification_email(
                to_email=user.email,
                subject=f"CRS Rejected - {project.name}",
                event_type="CRS Document Rejected",
                crs_id=crs.id,
                project_name=project.name,
                details=f"Your CRS document has been rejected by {rejector.full_name}. Please review the feedback.",
            )


def notify_crs_review_assignment(
    db: Session,
    crs: CRSDocument,
    project: Project,
    reviewer_id: int,
    send_email_notification: bool = True,
):
    """Notify user when assigned to review a CRS."""
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(reviewer_id)
    if not user:
        return

    create_notification(
        db=db,
        user_id=reviewer_id,
        notification_type="crs_review_assigned",
        reference_id=crs.id,
        title="CRS Review Assignment",
        message=f"You have been assigned to review CRS for project '{project.name}'",
        meta_data={
            "project_id": project.id,
            "project_name": project.name,
            "crs_id": crs.id,
            "team_id": project.team_id,
        },
    )

    if send_email_notification:
        send_crs_notification_email(
            to_email=user.email,
            subject=f"CRS Review Assignment - {project.name}",
            event_type="CRS Review Assignment",
            crs_id=crs.id,
            project_name=project.name,
            details="You have been assigned to review this CRS document. Please review and provide your feedback.",
        )
