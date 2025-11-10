from datetime import datetime
from pydantic import BaseModel
from enum import Enum


class ProjectStatus(str, Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class ProjectBase(BaseModel):
    name: str
    description: str | None = None
    status: ProjectStatus | None = ProjectStatus.draft


class ProjectCreate(ProjectBase):
    team_id: int | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectResponse(ProjectBase):
    id: int
    created_by: int
    approved_by: int | None = None
    approved_at: datetime | None = None
    rejected_by: int | None = None
    rejected_at: datetime | None = None
    team_id: int | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True