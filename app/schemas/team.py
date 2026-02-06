import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, root_validator, validator


class TeamRole(str, Enum):
    client = "client"
    ba = "ba"


class TeamStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    archived = "archived"


# User info for team member details
class UserInfo(BaseModel):
    id: int
    full_name: str
    email: str
    role: str

    class Config:
        from_attributes = True


# Team schemas
class TeamCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)

    @validator("name")
    def validate_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Team name cannot be empty")
        # Removed strict regex to allow Arabic and other characters
        # if not re.match(r"^[a-zA-Z0-9\s\-_]+$", v):
        #     raise ValueError(
        #         "Team name can only contain letters, numbers, spaces, hyphens, and underscores"
        #     )
        return v

    @validator("description")
    def validate_description(cls, v):
        if v is not None:
            v = v.strip()
            dangerous_patterns = [r"<script", r"javascript:", r"onerror=", r"onclick="]
            for pattern in dangerous_patterns:
                if re.search(pattern, v, re.IGNORECASE):
                    raise ValueError("Description contains invalid content")
        return v


class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    status: Optional[TeamStatus] = None

    @validator("name")
    def validate_name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Team name cannot be empty")
            # Removed strict regex to allow Arabic and other characters
            # if not re.match(r"^[a-zA-Z0-9\s\-_]+$", v):
            #     raise ValueError(
            #         "Team name can only contain letters, numbers, spaces, hyphens, and underscores"
            #     )
        return v

    @validator("description")
    def validate_description(cls, v):
        if v is not None:
            v = v.strip()
            dangerous_patterns = [r"<script", r"javascript:", r"onerror=", r"onclick="]
            for pattern in dangerous_patterns:
                if re.search(pattern, v, re.IGNORECASE):
                    raise ValueError("Description contains invalid content")
        return v

    @root_validator(pre=True)
    def validate_no_immutable_fields(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        """Validate that no immutable fields are being updated"""
        if isinstance(values, dict):
            # List of fields that should never be updated
            immutable_fields = ["id", "created_by", "created_at", "updated_at"]

            # Check if any immutable fields are present in the request
            invalid_fields = [field for field in immutable_fields if field in values]
            if invalid_fields:
                raise ValueError(
                    f"Cannot update immutable fields: {', '.join(invalid_fields)}. "
                    f"Only these fields can be updated: name, description, status"
                )

        return values


# Simple project schema to avoid circular imports
class ProjectSimpleOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class TeamMemberOut(BaseModel):
    id: int
    user_id: int
    role: TeamRole
    is_active: bool
    joined_at: datetime

    class Config:
        from_attributes = True


class TeamOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: TeamStatus
    created_by: int
    created_at: datetime
    updated_at: datetime
    members: Optional[List[TeamMemberOut]] = []
    projects: Optional[List[ProjectSimpleOut]] = []

    class Config:
        from_attributes = True


class TeamListOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    status: TeamStatus
    created_by: int
    created_at: datetime
    member_count: Optional[int] = 0

    class Config:
        from_attributes = True


# Team member schemas
class TeamMemberCreate(BaseModel):
    user_id: int
    role: Optional[TeamRole] = TeamRole.client


class TeamMemberUpdate(BaseModel):
    role: Optional[TeamRole] = None
    is_active: Optional[bool] = None


class TeamMemberDetailOut(BaseModel):
    id: int
    team_id: int
    user_id: int
    role: TeamRole
    is_active: bool
    joined_at: datetime
    updated_at: datetime
    user: Optional[UserInfo] = None

    class Config:
        from_attributes = True


# Dashboard statistics schemas
class StatusBreakdown(BaseModel):
    """Generic status breakdown with counts"""
    total: int = 0
    by_status: Dict[str, int] = {}


class ProjectStats(BaseModel):
    """Project statistics for dashboard"""
    total: int = 0
    by_status: Dict[str, int] = {}


class ChatStats(BaseModel):
    """Chat statistics for dashboard"""
    total: int = 0
    by_status: Dict[str, int] = {}


class CRSStats(BaseModel):
    """CRS statistics for dashboard"""
    total: int = 0
    by_status: Dict[str, int] = {}


class TeamDashboardStatsOut(BaseModel):
    """Team dashboard aggregated statistics"""
    projects: ProjectStats
    chats: ChatStats
    crs: CRSStats
    recent_projects: List[ProjectSimpleOut] = []

    class Config:
        from_attributes = True
