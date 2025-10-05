"""
Tests for general-purpose API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


def test_ping_endpoint(test_client: TestClient):
    """Test ping endpoint."""
    response = test_client.get("/api/ping")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health_check(test_client: TestClient):
    """Test health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_oauth2_authorize(test_client: TestClient):
    """Test OAuth2 authorization start."""
    with patch('limp.api.oauth2.get_system_config') as mock_get_config, \
         patch('limp.api.oauth2.OAuth2Service') as mock_oauth2:
        
        # Mock system config
        mock_config = Mock()
        mock_config.name = "test_system"
        mock_get_config.return_value = mock_config
        
        # Mock OAuth2 service
        mock_service = Mock()
        mock_service.generate_auth_url.return_value = "https://example.com/oauth/authorize?state=test"
        mock_oauth2.return_value = mock_service
        
        response = test_client.get("/api/oauth2/authorize/test_system?user_id=1")
        assert response.status_code == 200
        assert "authorization_url" in response.json()
        assert response.json()["system_name"] == "test_system"


def test_oauth2_callback_success(test_client: TestClient):
    """Test OAuth2 callback success."""
    with patch('limp.api.oauth2.OAuth2Service') as mock_oauth2:
        # Mock OAuth2 service
        mock_service = Mock()
        mock_token = Mock()
        mock_token.user_id = 1
        mock_token.system_name = "test_system"
        mock_service.handle_callback.return_value = mock_token
        mock_oauth2.return_value = mock_service
        
        response = test_client.get("/api/oauth2/callback/test_system?code=test_code&state=test_state")
        assert response.status_code == 200
        assert response.json()["status"] == "success"
        assert response.json()["system_name"] == "test_system"


def test_oauth2_callback_failure(test_client: TestClient):
    """Test OAuth2 callback failure."""
    with patch('limp.api.oauth2.OAuth2Service') as mock_oauth2:
        # Mock OAuth2 service
        mock_service = Mock()
        mock_service.handle_callback.return_value = None
        mock_oauth2.return_value = mock_service
        
        response = test_client.get("/api/oauth2/callback/test_system?code=test_code&state=test_state")
        assert response.status_code == 400
        assert "Authorization failed" in response.json()["detail"]


def test_oauth2_status_authorized(test_client: TestClient):
    """Test OAuth2 status check for authorized user."""
    with patch('limp.api.oauth2.OAuth2Service') as mock_oauth2:
        # Mock OAuth2 service
        mock_service = Mock()
        mock_token = Mock()
        mock_token.expires_at = None
        mock_service.get_valid_token.return_value = mock_token
        mock_oauth2.return_value = mock_service
        
        response = test_client.get("/api/oauth2/status/1/test_system")
        assert response.status_code == 200
        assert response.json()["authorized"] is True


def test_oauth2_status_not_authorized(test_client: TestClient):
    """Test OAuth2 status check for not authorized user."""
    with patch('limp.api.oauth2.OAuth2Service') as mock_oauth2:
        # Mock OAuth2 service
        mock_service = Mock()
        mock_service.get_valid_token.return_value = None
        mock_oauth2.return_value = mock_service
        
        response = test_client.get("/api/oauth2/status/1/test_system")
        assert response.status_code == 200
        assert response.json()["authorized"] is False