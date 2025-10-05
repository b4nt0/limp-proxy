"""
Tests for admin pages (dashboard, config, users).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


def test_admin_dashboard(test_client: TestClient):
    """Test admin dashboard endpoint."""
    response = test_client.get("/admin/")
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")


def test_admin_config_unauthorized(test_client: TestClient):
    """Test admin config endpoint without authentication."""
    response = test_client.get("/admin/config/api")
    assert response.status_code == 401


def test_admin_config_authorized(test_client: TestClient):
    """Test admin config endpoint with authentication."""
    with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
        mock_verify.return_value = True
        
        response = test_client.get(
            "/admin/config/api",
            auth=("admin", "admin123")
        )
        assert response.status_code == 200
        assert "database" in response.json()
        assert "llm" in response.json()


def test_admin_users_unauthorized(test_client: TestClient):
    """Test admin users endpoint without authentication."""
    response = test_client.get("/admin/users/api")
    assert response.status_code == 401


def test_admin_users_authorized(test_client: TestClient):
    """Test admin users endpoint with authentication."""
    with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
        mock_verify.return_value = True
        
        response = test_client.get(
            "/admin/users/api",
            auth=("admin", "admin123")
        )
        assert response.status_code == 200
        assert "users" in response.json()


def test_admin_revoke_token_unauthorized(test_client: TestClient):
    """Test admin revoke token endpoint without authentication."""
    response = test_client.delete("/admin/users/1/tokens/1")
    assert response.status_code == 401


def test_admin_revoke_token_authorized(test_client: TestClient):
    """Test admin revoke token endpoint with authentication."""
    with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
        mock_verify.return_value = True
        
        # Mock the database session and query
        mock_token = Mock()
        mock_token.id = 1
        mock_token.user_id = 1
        
        mock_db = Mock()
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_token
        mock_db.query.return_value = mock_query
        mock_db.delete.return_value = None
        mock_db.commit.return_value = None
        
        with patch('limp.database.connection.sessionmaker') as mock_sessionmaker:
            mock_sessionmaker.return_value.__enter__.return_value = mock_db
            
            response = test_client.delete(
                "/admin/users/1/tokens/1",
                auth=("admin", "admin123")
            )
            
            assert response.status_code == 200
            assert response.json()["status"] == "success"
            assert response.json()["message"] == "Token revoked"
