"""
Integration tests for end-to-end CRS generation flow with different patterns.
Tests the complete workflow from API request to CRS document creation.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import Mock, patch
from app.main import app
from app.db.session import Base, get_db
from app.models.user import User
from app.models.team import Team, TeamMember, TeamRole
from app.models.project import Project
from app.models.crs import CRSDocument, CRSPattern, CRSStatus
from app.core.security import create_access_token
from app.utils.hash import hash_password
import json


# Test database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test_patterns_integration.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(scope="function")
def test_db():
    """Create test database and tables."""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_client(test_db):
    """Create test client with database override."""
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def test_user(test_db):
    """Create test user."""
    user = User(
        email="test@example.com",
        full_name="Test User",
        password_hash=hash_password("testpass123"),
        is_active=True
    )
    test_db.add(user)
    test_db.commit()
    test_db.refresh(user)
    return user


@pytest.fixture
def test_team(test_db, test_user):
    """Create test team."""
    team = Team(
        name="Test Team",
        description="Test Team Description",
        created_by=test_user.id
    )
    test_db.add(team)
    test_db.commit()
    test_db.refresh(team)
    return team


@pytest.fixture
def test_team_member(test_db, test_user, test_team):
    """Create test team membership."""
    member = TeamMember(
        team_id=test_team.id,
        user_id=test_user.id,
        role=TeamRole.ba
    )
    test_db.add(member)
    test_db.commit()
    test_db.refresh(member)
    return member


@pytest.fixture
def test_project(test_db, test_user, test_team, test_team_member):
    """Create test project."""
    project = Project(
        name="Test Project",
        description="Test Description",
        team_id=test_team.id,
        created_by=test_user.id
    )
    test_db.add(project)
    test_db.commit()
    test_db.refresh(project)
    return project


@pytest.fixture
def auth_headers(test_user):
    """Generate authentication headers."""
    token = create_access_token(data={"sub": str(test_user.id)})
    return {"Authorization": f"Bearer {token}"}


class TestCRSPatternIntegration:
    """Integration tests for CRS pattern selection and generation."""
    
    @patch('app.services.crs_service.create_memory')
    def test_create_crs_with_babok_pattern(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test creating CRS with BABOK pattern."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "E-Commerce Platform",
                "project_description": "Online shopping platform",
                "functional_requirements": [{"id": "BR-001", "title": "Product Catalog"}]
            }),
            "summary_points": ["E-Commerce Platform"],
            "pattern": "babok"
        }
        
        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)
        
        assert response.status_code == 201
        
        # Verify in database
        crs = test_db.query(CRSDocument).filter_by(project_id=test_project.id).first()
        assert crs is not None
        assert crs.pattern == CRSPattern.babok
    
    @patch('app.services.crs_service.create_memory')
    def test_create_crs_with_ieee830_pattern(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test creating CRS with IEEE 830 pattern."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Inventory System",
                "project_description": "Real-time inventory tracking",
                "functional_requirements": [{"id": "SRS-001", "title": "Inventory Tracking"}]
            }),
            "summary_points": ["Inventory Management System"],
            "pattern": "ieee_830"
        }
        
        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)
        
        assert response.status_code == 201
        
        # Verify in database
        crs = test_db.query(CRSDocument).filter_by(project_id=test_project.id).first()
        assert crs is not None
        assert crs.pattern == CRSPattern.ieee_830
    
    @patch('app.services.crs_service.create_memory')
    def test_create_crs_with_iso29148_pattern(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test creating CRS with ISO/IEC/IEEE 29148 pattern."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Hospital Management",
                "project_description": "Patient care and record management",
                "functional_requirements": [{"id": "SYS-001", "title": "Patient Registration"}]
            }),
            "summary_points": ["Hospital Management System"],
            "pattern": "iso_iec_ieee_29148"
        }
        
        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)
        
        assert response.status_code == 201
        
        # Verify in database
        crs = test_db.query(CRSDocument).filter_by(project_id=test_project.id).first()
        assert crs is not None
        assert crs.pattern == CRSPattern.iso_iec_ieee_29148
    
    @patch('app.services.crs_service.create_memory')
    def test_create_crs_default_pattern_when_not_specified(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test that BABOK is used as default when pattern not specified."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Default Pattern Test",
                "project_description": "Testing default pattern",
                "functional_requirements": []
            }),
            "summary_points": ["Default Pattern Test"]
        }

        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data['pattern'] == 'babok'  # Default pattern
        
        # Verify in database
        crs = test_db.query(CRSDocument).filter_by(project_id=test_project.id).first()
        assert crs is not None
        assert crs.pattern == CRSPattern.babok
    
    @patch('app.services.crs_service.create_memory')
    def test_create_crs_with_invalid_pattern_defaults_to_babok(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test that invalid pattern defaults to BABOK."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Invalid Pattern Test",
                "project_description": "Testing invalid pattern handling",
                "functional_requirements": []
            }),
            "summary_points": ["Invalid Pattern Test"],
            "pattern": "invalid_pattern"
        }
        
        # This should fail validation at the API level due to enum constraint
        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)
        
        assert response.status_code == 422  # Validation error
    
    @patch('app.services.crs_service.create_memory')
    def test_pattern_persists_across_versions(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test that pattern is maintained across multiple CRS versions."""
        # Create first version with IEEE 830
        payload_v1 = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Version Test",
                "project_description": "Testing version pattern persistence",
                "functional_requirements": [{"id": "SRS-001", "title": "Feature 1"}]
            }),
            "summary_points": ["Version 1"],
            "pattern": "ieee_830"
        }
        
        response1 = test_client.post("/api/crs/", json=payload_v1, headers=auth_headers)
        assert response1.status_code == 201
        crs1_id = response1.json()['id']
        
        # Create second version with ISO 29148
        payload_v2 = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Version Test",
                "project_description": "Testing version pattern persistence",
                "functional_requirements": [{"id": "SYS-001", "title": "Feature 1"}]
            }),
            "summary_points": ["Version 2"],
            "pattern": "iso_iec_ieee_29148"
        }
        
        response2 = test_client.post("/api/crs/", json=payload_v2, headers=auth_headers)
        assert response2.status_code == 201
        
        # Verify both versions exist with their respective patterns
        crs1 = test_db.query(CRSDocument).filter_by(id=crs1_id).first()
        crs2 = test_db.query(CRSDocument).filter_by(project_id=test_project.id, version=2).first()
        
        assert crs1.pattern == CRSPattern.ieee_830
        assert crs2.pattern == CRSPattern.iso_iec_ieee_29148
        assert crs1.version == 1
        assert crs2.version == 2


class TestPartialCRSWithPatterns:
    """Integration tests for partial CRS generation with pattern selection."""
    
    @patch('app.services.crs_service.create_memory')
    def test_partial_crs_with_babok_pattern(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test creating partial CRS with BABOK pattern."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({
                "project_title": "Partial BABOK CRS",
                "project_description": "Testing partial generation with BABOK",
                "functional_requirements": []
            }),
            "summary_points": ["Partial CRS"],
            "pattern": "babok",
            "allow_partial": True,
            "completeness_percentage": 60
        }

        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)

        assert response.status_code == 201
        data = response.json()
        assert data['pattern'] == 'babok'
        assert data['status'] == 'draft'
        
        # Verify in database
        crs = test_db.query(CRSDocument).filter_by(project_id=test_project.id).first()
        assert crs.pattern == CRSPattern.babok
        assert crs.status == CRSStatus.draft
    
    @patch('app.services.crs_service.create_memory')
    def test_partial_crs_below_minimum_threshold(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test that partial CRS below 40% threshold is rejected."""
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({"project_title": "Low Completeness"}),
            "summary_points": ["Low Completeness"],
            "pattern": "ieee_830",
            "allow_partial": True,
            "completeness_percentage": 35  # Below 40% threshold
        }
        
        response = test_client.post("/api/crs/", json=payload, headers=auth_headers)
        
        assert response.status_code == 400
        assert "40%" in response.json()['detail']
    """Integration tests for retrieving CRS documents with pattern information."""
    
    @patch('app.services.crs_service.create_memory')
    def test_get_crs_returns_pattern(self, mock_memory, test_client, test_db, test_project, auth_headers):
        """Test that GET /api/crs/{id} returns pattern field."""
        # Create CRS
        payload = {
            "project_id": test_project.id,
            "content": json.dumps({"project_title": "Pattern Retrieval Test"}),
            "summary_points": ["Test"],
            "pattern": "ieee_830"
        }
        
        create_response = test_client.post("/api/crs/", json=payload, headers=auth_headers)
        crs_id = create_response.json()['id']
        
        # Retrieve CRS
        get_response = test_client.get(f"/api/crs/{crs_id}", headers=auth_headers)
        
        assert get_response.status_code == 200
        data = get_response.json()
        assert 'pattern' in data
        assert data['pattern'] == 'ieee_830'
    
    @patch('app.services.crs_service.create_memory')
    def test_list_crs_returns_patterns(self, mock_memory, test_client, test_db, test_user, test_project, auth_headers):
        """Test that listing CRS documents includes pattern information."""
        # Create multiple CRS with different patterns using same project
        patterns = ['babok', 'ieee_830', 'iso_iec_ieee_29148']
        
        for pattern in patterns:
            payload = {
                "project_id": test_project.id,
                "content": json.dumps({"project_title": f"Test {pattern}"}),
                "summary_points": [f"Test {pattern}"],
                "pattern": pattern
            }
            test_client.post("/api/crs/", json=payload, headers=auth_headers)
        
        # List CRS versions for the project
        list_response = test_client.get(f"/api/crs/versions?project_id={test_project.id}", headers=auth_headers)
        
        assert list_response.status_code == 200
        data = list_response.json()
        assert len(data) == 3
        
        # Verify patterns are included
        returned_patterns = [crs['pattern'] for crs in data]
        for pattern in patterns:
            assert pattern in returned_patterns
