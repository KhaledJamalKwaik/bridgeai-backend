"""
Teams API Module.
Aggregates all teams endpoint routers for backward compatibility.
"""
from fastapi import APIRouter

from .crud import router as crud_router
from .members import router as members_router
from .dashboard import router as dashboard_router

from .invitations import router as invitations_router

# Create main router that includes all sub-routers
router = APIRouter()

# Include all teams sub-routers
# IMPORTANT: Include routers with specific routes (like /members, /projects)
# BEFORE routers with path parameters (like /{team_id}) to avoid route conflicts
router.include_router(crud_router, tags=["Teams"])
router.include_router(members_router, tags=["Team Members"])
router.include_router(invitations_router, tags=["Team Invitations"])
router.include_router(dashboard_router, tags=["Team Dashboard"])

__all__ = ["router"]
