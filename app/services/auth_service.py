"""
Authentication Service Module.
Handles all business logic for user authentication, registration, and profile management.
Following architectural rules: stateless, no direct db.session access, uses repositories where applicable.
"""
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import random
import string

from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from google.oauth2 import id_token
from google.auth.transport import requests

from app.models.user import User, UserRole
from app.models.invitation import Invitation
from app.models.team import Team
from app.models.user_otp import UserOTP
from app.core.security import create_access_token
from app.utils.hash import hash_password, verify_password
from app.utils.email import send_password_reset_email
from app.services import notification_service
from app.repositories import (
    UserRepository,
    InvitationRepository,
    TeamRepository,
    OTPRepository,
)


class AuthService:
    """Service for managing authentication and user operations."""

    @staticmethod
    def google_login(db: Session, token: str, role: UserRole, google_client_id: str) -> Dict[str, Any]:
        """
        Authenticate user via Google OAuth.
        Only allows @gmail.com email addresses for Google Sign-In.
        """
        try:
            # Verify Google token
            id_info = id_token.verify_oauth2_token(
                token, requests.Request(), google_client_id
            )

            # Extract user data from Google token
            google_id = id_info["sub"]
            email = id_info.get("email")
            name = id_info.get("name", "")
            picture = id_info.get("picture")

            # RESTRICTION: Only allow @gmail.com email addresses
            if not email or not email.endswith("@gmail.com"):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only @gmail.com accounts are allowed for Google Sign-In. Please register with email and password instead."
                )

            # Check if user exists
            user_repo = UserRepository(db)
            user = user_repo.get_by_email(email)

            if not user:
                # Create new user from Google account
                user = user_repo.create(
                    User(
                        full_name=name,
                        email=email,
                        google_id=google_id,
                        avatar_url=picture,
                        role=role,
                        password_hash=None,  # Google users don't have a password
                    )
                )
            else:
                # Update existing user's Google ID and avatar if needed
                if not user.google_id:
                    user.google_id = google_id

                if picture and user.avatar_url != picture:
                    user.avatar_url = picture

                user_repo.update(user)

            # Create access token
            user_role = user.role if user.role is not None else UserRole.client
            access_token = create_access_token({"sub": str(user.id), "role": user_role})

            return {
                "access_token": access_token,
                "token_type": "bearer",
                "role": user_role.value,
            }

        except ValueError as e:
            raise HTTPException(
                status_code=401, detail=f"Invalid Google token: {str(e)}"
            )

    @staticmethod
    def register_user(
        db: Session, full_name: str, email: str, password: str, role: UserRole
    ) -> User:
        """
        Register a new user with email and password.
        Creates notifications for any pending team invitations.
        """
        # Check if email already registered
        user_repo = UserRepository(db)
        existing = user_repo.get_by_email(email)
        if existing:
            raise HTTPException(status_code=400, detail="Email already registered")

        # Create user
        user = user_repo.create(
            User(
                full_name=full_name,
                email=email,
                password_hash=hash_password(password),
                role=role,
            )
        )

        # Check for pending invitations and create notifications
        AuthService._create_invitation_notifications(db, user)

        return user

    @staticmethod
    def _create_invitation_notifications(db: Session, user: User):
        """Create notifications for any pending team invitations for this user."""
        invitation_repo = InvitationRepository(db)
        pending_invitations = invitation_repo.get_user_invitations(user.email, status="pending")

        team_repo = TeamRepository(db)
        for invitation in pending_invitations:
            # Get team details for the notification message
            team = team_repo.get_by_id(invitation.team_id)
            if team and invitation.inviter:
                notification_service.notify_team_invitation(
                    db=db,
                    team_id=invitation.team_id,
                    team_name=team.name,
                    inviter_name=invitation.inviter.full_name,
                    role=invitation.role,
                    invited_user_id=user.id,
                    commit=False,
                )

        db.commit()

    @staticmethod
    def authenticate_user(db: Session, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user with email and password.
        Returns access token and user role.
        """
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user or not verify_password(password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
            )

        # Ensure user has a role, default to client if None
        user_role = user.role if user.role is not None else UserRole.client

        access_token = create_access_token({"sub": str(user.id), "role": user_role})
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "role": user_role.value,
        }

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """Get user by ID."""
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )
        return user

    @staticmethod
    def initiate_password_reset(db: Session, email: str) -> Dict[str, str]:
        """
        Step 1 of password reset: Generate and send OTP.
        Returns success message.
        """
        # Check if user exists
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="This email is not registered with BridgeAI.",
            )

        # Generate 6-digit OTP
        otp_code = "".join(random.choices(string.digits, k=6))
        expires_at = datetime.utcnow() + timedelta(minutes=15)

        # Store in DB (delete old ones first)
        otp_repo = OTPRepository(db)
        otp_repo.delete_by_email(email)

        db_otp = UserOTP(email=email, otp_code=otp_code, expires_at=expires_at)
        otp_repo.create(db_otp)

        # Send email
        send_password_reset_email(email, otp_code)

        return {"message": "Verification code sent to your email."}

    @staticmethod
    def verify_otp(db: Session, email: str, otp_code: str) -> Dict[str, str]:
        """
        Step 2 of password reset: Verify the OTP code.
        Returns success message.
        """
        otp_repo = OTPRepository(db)
        db_otp = otp_repo.get_by_email_and_code(email, otp_code)

        if not db_otp:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid verification code.",
            )

        if db_otp.is_expired:
            otp_repo.delete(db_otp)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Verification code has expired.",
            )

        return {"message": "Verification successful."}

    @staticmethod
    def reset_password(
        db: Session, email: str, otp_code: str, new_password: str
    ) -> Dict[str, str]:
        """
        Step 3 of password reset: Reset the password after OTP verification.
        Returns success message.
        """
        # Verify OTP again (stateless verification for the final step)
        otp_repo = OTPRepository(db)
        db_otp = otp_repo.get_by_email_and_code(email, otp_code)

        if not db_otp or db_otp.is_expired:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid or expired verification session.",
            )

        # Get User
        user_repo = UserRepository(db)
        user = user_repo.get_by_email(email)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
            )

        # Update Password
        user.password_hash = hash_password(new_password)

        # Clean up OTP
        otp_repo.delete(db_otp)

        user_repo.update(user)

        return {"message": "Password reset successfully. You can now log in."}

    @staticmethod
    def update_profile(db: Session, user: User, full_name: str) -> User:
        """Update user's profile information."""
        user.full_name = full_name

        db.commit()
        db.refresh(user)

        return user

    @staticmethod
    def change_password(
        db: Session, user: User, current_password: str, new_password: str
    ) -> Dict[str, str]:
        """Change password for authenticated user."""
        # Check if user has a password (not a Google OAuth user)
        if not user.password_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot change password for Google OAuth users. Your account uses Google Sign-In.",
            )

        # Verify current password
        if not verify_password(current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Update password
        user.password_hash = hash_password(new_password)

        db.commit()

        return {"message": "Password changed successfully"}
