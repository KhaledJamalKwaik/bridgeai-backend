from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey
from app.db.session import Base
import enum


class ProjectStatus(enum.Enum):
    draft = "draft"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"


class Project(Base):
    __tablename__ = "projects"


    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(256), nullable=False)
    description = Column(Text)
    status = Column(Enum(ProjectStatus), default=ProjectStatus.draft)
    
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by = Column(Integer, ForeignKey("users.id"))
    approved_at = Column(DateTime)
    rejected_by = Column(Integer, ForeignKey("users.id"))
    rejected_at = Column(DateTime)

    team_id = Column(Integer, ForeignKey("teams.id"))

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )    
    
    creator = relationship("User", foreign_keys=[created_by])
    approver = relationship("User", foreign_keys=[approved_by])
    rejected_user = relationship("User", foreign_keys=[rejected_by])
    team = relationship("Team", back_populates="projects")