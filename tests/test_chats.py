"""
Tests for chat/session endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.project import Project
from app.models.session_model import SessionModel, SessionStatus
from app.models.team import Team, TeamMember, TeamRole
from app.models.user import User, UserRole
from app.utils.hash import hash_password


@pytest.fixture
def test_user(db: Session):
    """Create a test user"""
    user = User(
        email="chatuser@test.com",
        full_name="Chat Test User",
        password_hash=hash_password("testpassword"),
        role=UserRole.client,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def test_team(db: Session, test_user):
    """Create a test team with the user as owner"""
    team = Team(
        name="Chat Test Team",
        description="A test team for chat testing",
        created_by=test_user.id,
    )
    db.add(team)
    db.commit()
    db.refresh(team)

    # Add user as team member
    member = TeamMember(team_id=team.id, user_id=test_user.id, role=TeamRole.ba)
    db.add(member)
    db.commit()
    return team


@pytest.fixture
def test_project(db: Session, test_team, test_user):
    """Create a test project"""
    project = Project(
        name="Chat Test Project",
        description="A test project for chat testing",
        team_id=test_team.id,
        created_by=test_user.id,
        status="pending",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@pytest.fixture
def auth_headers(test_user):
    """Generate auth headers with valid token"""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


def test_create_chat_session(client: TestClient, test_project, auth_headers):
    """Test creating a new chat session"""
    response = client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Requirements Discussion"},
        headers=auth_headers,
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Requirements Discussion"
    assert data["project_id"] == test_project.id
    assert data["status"] == "active"
    assert data["messages"] == []


def test_create_chat_without_name(client: TestClient, test_project, auth_headers):
    """Test creating chat without name should fail"""
    response = client.post(
        f"/api/projects/{test_project.id}/chats", json={}, headers=auth_headers
    )

    assert response.status_code == 422  # Validation error


def test_create_chat_without_auth(client: TestClient):
    """Test creating chat without authentication should fail"""
    response = client.post("/api/projects/1/chats", json={"name": "Test Chat"})

    assert response.status_code == 401


def test_create_chat_invalid_project(client: TestClient, auth_headers):
    """Test creating chat for non-existent project should fail"""
    response = client.post(
        "/api/projects/99999/chats", json={"name": "Test Chat"}, headers=auth_headers
    )

    assert response.status_code == 404


def test_get_all_chats(client: TestClient, test_project, auth_headers):
    """Test getting all chat sessions for a project"""
    # Create two chats
    client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Chat 1"},
        headers=auth_headers,
    )
    client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Chat 2"},
        headers=auth_headers,
    )

    # Get all chats
    response = client.get(
        f"/api/projects/{test_project.id}/chats", headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] in ["Chat 1", "Chat 2"]
    assert "message_count" in data[0]


def test_get_specific_chat(client: TestClient, test_project, auth_headers):
    """Test getting a specific chat session with messages"""
    # Create a chat
    create_response = client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Specific Chat"},
        headers=auth_headers,
    )
    chat_id = create_response.json()["id"]

    # Get the chat
    response = client.get(
        f"/api/projects/{test_project.id}/chats/{chat_id}", headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == chat_id
    assert data["name"] == "Specific Chat"
    assert isinstance(data["messages"], list)


def test_get_chat_wrong_project(client: TestClient, test_project, auth_headers):
    """Test getting chat from wrong project should fail"""
    # Create a chat
    create_response = client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Test Chat"},
        headers=auth_headers,
    )
    chat_id = create_response.json()["id"]

    # Try to get it with wrong project_id
    response = client.get(f"/api/projects/99999/chats/{chat_id}", headers=auth_headers)

    assert response.status_code == 404


def test_update_chat_status(client: TestClient, test_project, auth_headers):
    """Test updating chat session status"""
    # Create a chat
    create_response = client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Test Chat"},
        headers=auth_headers,
    )
    chat_id = create_response.json()["id"]

    # Update status to completed
    response = client.put(
        f"/api/projects/{test_project.id}/chats/{chat_id}",
        json={"status": "completed"},
        headers=auth_headers,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"


def test_delete_chat(client: TestClient, test_project, auth_headers):
    """Test deleting a chat session"""
    # Create a chat
    create_response = client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Chat to Delete"},
        headers=auth_headers,
    )
    chat_id = create_response.json()["id"]

    # Delete the chat
    response = client.delete(
        f"/api/projects/{test_project.id}/chats/{chat_id}", headers=auth_headers
    )

    assert response.status_code == 204

    # Verify it's deleted
    get_response = client.get(
        f"/api/projects/{test_project.id}/chats/{chat_id}", headers=auth_headers
    )
    assert get_response.status_code == 404


def test_delete_nonexistent_chat(client: TestClient, test_project, auth_headers):
    """Test deleting non-existent chat should fail"""
    response = client.delete(
        f"/api/projects/{test_project.id}/chats/99999", headers=auth_headers
    )

    assert response.status_code == 404


def test_chat_access_control(client: TestClient, db: Session, test_project):
    """Test that users cannot access chats from teams they're not in"""
    # Create another user not in the team
    other_user = User(
        email="otheruser@example.com",
        full_name="Other User",
        password_hash=hash_password("password"),
        role=UserRole.client,
    )
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    # Generate token for other user
    other_token = create_access_token(data={"sub": str(other_user.id)})
    other_headers = {"Authorization": f"Bearer {other_token}"}

    # Try to create chat in project
    response = client.post(
        f"/api/projects/{test_project.id}/chats",
        json={"name": "Unauthorized Chat"},
        headers=other_headers,
    )

    assert response.status_code == 403
