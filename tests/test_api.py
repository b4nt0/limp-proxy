"""
Tests for API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from limp.api.main import create_app
from limp.config import Config, DatabaseConfig, LLMConfig


def test_root_endpoint(test_client: TestClient):
    """Test root endpoint."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_health_check(test_client: TestClient):
    """Test health check endpoint."""
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


def test_slack_webhook_challenge(test_client: TestClient):
    """Test Slack webhook challenge."""
    challenge_data = {
        "type": "url_verification",
        "challenge": "test_challenge_123"
    }
    
    with patch('limp.api.slack.IMServiceFactory.create_service') as mock_factory:
        mock_service = Mock()
        mock_service.verify_request.return_value = True
        mock_service.parse_message.return_value = {
            "type": "challenge",
            "challenge": "test_challenge_123"
        }
        mock_factory.return_value = mock_service
        
        response = test_client.post("/api/slack/webhook", json=challenge_data)
        assert response.status_code == 200
        assert response.json()["challenge"] == "test_challenge_123"


def test_slack_webhook_message(test_client: TestClient):
    """Test Slack webhook message handling."""
    message_data = {
        "type": "event_callback",
        "event": {
            "type": "message",
            "user": "U123456",
            "channel": "C123456",
            "text": "Hello, bot!",
            "ts": "1234567890.123456"
        }
    }
    
    with patch('limp.api.slack.IMServiceFactory.create_service') as mock_factory, \
         patch('limp.api.slack.handle_user_message') as mock_handle:
        
        mock_service = Mock()
        mock_service.verify_request.return_value = True
        mock_service.parse_message.return_value = {
            "type": "message",
            "user_id": "U123456",
            "channel": "C123456",
            "text": "Hello, bot!",
            "timestamp": "1234567890.123456"
        }
        mock_factory.return_value = mock_service
        
        mock_handle.return_value = {"status": "ok"}
        
        response = test_client.post("/api/slack/webhook", json=message_data)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_teams_webhook_message(test_client: TestClient):
    """Test Teams webhook message handling."""
    message_data = {
        "type": "message",
        "from": {"id": "U123456"},
        "conversation": {"id": "C123456"},
        "text": "Hello, bot!",
        "timestamp": "1234567890.123456"
    }
    
    with patch('limp.api.teams.IMServiceFactory.create_service') as mock_factory, \
         patch('limp.api.teams.handle_user_message') as mock_handle:
        
        mock_service = Mock()
        mock_service.verify_request.return_value = True
        mock_service.parse_message.return_value = {
            "type": "message",
            "user_id": "U123456",
            "channel": "C123456",
            "text": "Hello, bot!",
            "timestamp": "1234567890.123456"
        }
        mock_factory.return_value = mock_service
        
        mock_handle.return_value = {"status": "ok"}
        
        response = test_client.post("/api/teams/webhook", json=message_data)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_slack_install_success(test_client: TestClient):
    """Test successful Slack installation."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange, \
         patch('limp.api.slack.store_slack_installation') as mock_store, \
         patch('limp.api.slack.send_installation_confirmation') as mock_confirm:
        
        # Mock successful token exchange
        mock_exchange.return_value = {
            "ok": True,
            "access_token": "xoxb-test-token",
            "token_type": "bot",
            "scope": "chat:write,channels:read",
            "bot_user_id": "U123456",
            "app_id": "A123456",
            "team": {
                "id": "T123456",
                "name": "Test Team"
            },
            "enterprise": {
                "id": "E123456",
                "name": "Test Enterprise"
            },
            "authed_user": {
                "id": "U789012",
                "access_token": "xoxp-user-token",
                "token_type": "user",
                "scope": "chat:write"
            }
        }
        
        # Mock successful storage
        mock_organization = Mock()
        mock_organization.organization_id = "T123456"
        mock_organization.team_name = "Test Team"
        mock_store.return_value = mock_organization
        
        # Mock confirmation sending
        mock_confirm.return_value = None
        
        response = test_client.get("/api/slack/install?code=test_code_123")
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "success"
        assert response_data["message"] == "Slack app installed successfully!"
        assert response_data["organization_id"] == "T123456"
        assert response_data["team_name"] == "Test Team"
        
        # Verify mocks were called
        mock_exchange.assert_called_once()
        mock_store.assert_called_once()
        mock_confirm.assert_called_once()


def test_slack_install_token_exchange_failure(test_client: TestClient):
    """Test Slack installation with token exchange failure."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange:
        # Mock failed token exchange
        mock_exchange.return_value = {
            "ok": False,
            "error": "invalid_code"
        }
        
        response = test_client.get("/api/slack/install?code=invalid_code")
        
        assert response.status_code == 400
        assert "Failed to exchange code for token" in response.json()["detail"]


def test_slack_install_storage_failure(test_client: TestClient):
    """Test Slack installation with storage failure."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange, \
         patch('limp.api.slack.store_slack_installation') as mock_store:
        
        # Mock successful token exchange
        mock_exchange.return_value = {
            "ok": True,
            "access_token": "xoxb-test-token",
            "team": {"id": "T123456", "name": "Test Team"}
        }
        
        # Mock storage failure
        mock_store.side_effect = Exception("Database error")
        
        response = test_client.get("/api/slack/install?code=test_code_123")
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


def test_slack_install_missing_code(test_client: TestClient):
    """Test Slack installation with missing authorization code."""
    response = test_client.get("/api/slack/install")
    
    assert response.status_code == 422  # FastAPI validation error


def test_slack_install_with_state(test_client: TestClient):
    """Test Slack installation with state parameter."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange, \
         patch('limp.api.slack.store_slack_installation') as mock_store, \
         patch('limp.api.slack.send_installation_confirmation') as mock_confirm:
        
        # Mock successful token exchange
        mock_exchange.return_value = {
            "ok": True,
            "access_token": "xoxb-test-token",
            "team": {"id": "T123456", "name": "Test Team"}
        }
        
        # Mock successful storage
        mock_organization = Mock()
        mock_organization.organization_id = "T123456"
        mock_organization.team_name = "Test Team"
        mock_store.return_value = mock_organization
        
        # Mock confirmation sending
        mock_confirm.return_value = None
        
        response = test_client.get("/api/slack/install?code=test_code_123&state=test_state_456")
        
        assert response.status_code == 200
        response_data = response.json()
        assert response_data["status"] == "success"


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