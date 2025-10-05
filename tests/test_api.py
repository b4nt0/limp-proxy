"""
Tests for API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from limp.api.main import create_app
from limp.config import Config, DatabaseConfig, LLMConfig


def test_root_page_with_slack_configured(test_client: TestClient):
    """Test root page when Slack is configured."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Install to Slack" in response.content.decode("utf-8")
    assert "slack.com/oauth/v2/authorize" in response.content.decode("utf-8")


def test_root_page_without_slack_configured(test_client: TestClient):
    """Test root page when Slack is not configured."""
    # Create a test app without Slack configuration
    from limp.config import AdminConfig, IMPlatformConfig, ExternalSystemConfig, OAuth2Config
    
    test_config_no_slack = Config(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        llm=LLMConfig(
            api_key="test-api-key",
            model="gpt-4",
            max_tokens=1000,
            temperature=0.7
        ),
        admin=AdminConfig(enabled=True, username="admin", password="admin123"),
        im_platforms=[],  # No Slack configured
        external_systems=[
            ExternalSystemConfig(
                name="test-system",
                oauth2=OAuth2Config(
                    client_id="test-client-id",
                    client_secret="test-client-secret",
                    authorization_url="https://example.com/oauth/authorize",
                    token_url="https://example.com/oauth/token",
                    redirect_uri="http://localhost:8000/callback"
                ),
                openapi_spec="https://example.com/api/openapi.json",
                base_url="https://example.com/api"
            )
        ],
    )
    
    test_app_no_slack = create_app(test_config_no_slack)
    test_client_no_slack = TestClient(test_app_no_slack)
    
    response = test_client_no_slack.get("/")
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Slack Not Configured" in response.content.decode("utf-8")
    assert "Configuration Error" in response.content.decode("utf-8")


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


def test_slack_webhook_challenge(test_client: TestClient):
    """Test Slack webhook challenge."""
    from limp.models.slack_organization import SlackOrganization
    from limp.database.connection import get_session
    
    # Add a test SlackOrganization to the database that the test client uses
    db = next(get_session())
    try:
        test_org = SlackOrganization(
            organization_id="T123456",
            access_token="xoxb-test-bot-token",
            token_type="bot",
            scope="chat:write,channels:read",
            bot_user_id="U123456",
            app_id="A123456",
            team_id="T123456",
            team_name="Test Team"
        )
        db.add(test_org)
        db.commit()
    finally:
        db.close()
    
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
    from limp.models.slack_organization import SlackOrganization
    from limp.database.connection import get_session
    
    # Add a test SlackOrganization to the database that the test client uses
    db = next(get_session())
    try:
        test_org = SlackOrganization(
            organization_id="T123456",
            access_token="xoxb-test-bot-token",
            token_type="bot",
            scope="chat:write,channels:read",
            bot_user_id="U123456",
            app_id="A123456",
            team_id="T123456",
            team_name="Test Team"
        )
        db.add(test_org)
        db.commit()
    finally:
        db.close()
    
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


def test_slack_webhook_ignored_message(test_client: TestClient):
    """Test Slack webhook ignores messages from own bot."""
    from limp.models.slack_organization import SlackOrganization
    from limp.database.connection import get_session
    
    # Add a test SlackOrganization to the database that the test client uses
    db = next(get_session())
    try:
        test_org = SlackOrganization(
            organization_id="T123456",
            access_token="xoxb-test-bot-token",
            token_type="bot",
            scope="chat:write,channels:read",
            bot_user_id="U123456",
            app_id="A123456",
            team_id="T123456",
            team_name="Test Team"
        )
        db.add(test_org)
        db.commit()
    finally:
        db.close()
    
    # Message from own bot (same event.app_id as configured)
    bot_message_data = {
        "type": "event_callback",
        "api_app_id": "A09JTJR1R40",
        "event": {
            "type": "message",
            "user": "U09JV5N35MW",
            "channel": "D09JV5N5B8Q",
            "text": "There was an issue communicating with the AI service. Please try again.",
            "ts": "1759512330.731609",
            "bot_id": "B09JV5N2K96",
            "app_id": "A09JTJR1R40"  # Matches configured app_id
        }
    }
    
    with patch('limp.api.slack.IMServiceFactory.create_service') as mock_factory:
        mock_service = Mock()
        mock_service.verify_request.return_value = True
        mock_service.parse_message.return_value = {"type": "ignored"}
        mock_factory.return_value = mock_service
        
        response = test_client.post("/api/slack/webhook", json=bot_message_data)
        assert response.status_code == 200
        assert response.json()["status"] == "ignored"


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
        
        response = test_client.get("/api/slack/install?code=test_code_123", follow_redirects=False)
        
        assert response.status_code == 302  # Redirect response
        assert response.headers["location"] == "/install-success?system=slack&organization=Test%20Team"
        
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
        
        response = test_client.get("/api/slack/install?code=test_code_123&state=test_state_456", follow_redirects=False)
        
        assert response.status_code == 302  # Redirect response
        assert response.headers["location"] == "/install-success?system=slack&organization=Test%20Team"


def test_slack_install_empty_team_data(test_client: TestClient):
    """Test Slack installation with empty team data."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange, \
         patch('limp.api.slack.store_slack_installation') as mock_store, \
         patch('limp.api.slack.send_installation_confirmation') as mock_confirm:
        
        # Mock token exchange with empty team data
        mock_exchange.return_value = {
            "ok": True,
            "access_token": "xoxb-test-token",
            "app_id": "A123456",  # Use app_id as fallback
            # No team, enterprise, or authed_user keys - they will be None
        }
        
        # Mock successful storage
        mock_organization = Mock()
        mock_organization.organization_id = "A123456"  # Should use app_id
        mock_organization.team_name = None
        mock_store.return_value = mock_organization
        
        # Mock confirmation sending (should be skipped due to empty authed_user)
        mock_confirm.return_value = None
        
        response = test_client.get("/api/slack/install?code=test_code_123", follow_redirects=False)
        
        assert response.status_code == 302  # Redirect response
        assert response.headers["location"] == "/install-success?system=slack&organization=A123456"
        
        # Verify that store_slack_installation was called with the token data
        mock_store.assert_called_once()
        # Verify that send_installation_confirmation was called (but should skip due to empty authed_user)
        mock_confirm.assert_called_once()


def test_slack_install_empty_authed_user(test_client: TestClient):
    """Test Slack installation with empty authed_user data."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange, \
         patch('limp.api.slack.store_slack_installation') as mock_store, \
         patch('limp.api.slack.send_installation_confirmation') as mock_confirm:
        
        # Mock token exchange with empty authed_user
        mock_exchange.return_value = {
            "ok": True,
            "access_token": "xoxb-test-token",
            "team": {"id": "T123456", "name": "Test Team"},
            "authed_user": None  # Explicitly None
        }
        
        # Mock successful storage
        mock_organization = Mock()
        mock_organization.organization_id = "T123456"
        mock_organization.team_name = "Test Team"
        mock_store.return_value = mock_organization
        
        # Mock confirmation sending (should be skipped)
        mock_confirm.return_value = None
        
        response = test_client.get("/api/slack/install?code=test_code_123", follow_redirects=False)
        
        assert response.status_code == 302  # Redirect response
        assert response.headers["location"] == "/install-success?system=slack&organization=Test%20Team"
        
        # Verify that send_installation_confirmation was called but should skip
        mock_confirm.assert_called_once()


def test_slack_install_no_organization_id(test_client: TestClient):
    """Test Slack installation with no organization identifier."""
    with patch('limp.api.slack.exchange_code_for_token') as mock_exchange, \
         patch('limp.api.slack.store_slack_installation') as mock_store:
        
        # Mock token exchange with no team_id or app_id
        mock_exchange.return_value = {
            "ok": True,
            "access_token": "xoxb-test-token",
            # No team, enterprise, authed_user, or app_id keys - all will be None
        }
        
        # Mock storage failure due to no organization ID
        mock_store.side_effect = ValueError("No organization identifier found in token data (neither team_id nor app_id)")
        
        response = test_client.get("/api/slack/install?code=test_code_123")
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


def test_install_success_page_slack(test_client: TestClient):
    """Test installation success page for Slack."""
    response = test_client.get("/install-success?system=slack&organization=Test%20Team")
    
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Installation Successful!" in response.content.decode("utf-8")
    assert "Test Team" in response.content.decode("utf-8")
    assert "Slack" in response.content.decode("utf-8")


def test_install_success_page_teams(test_client: TestClient):
    """Test installation success page for Teams."""
    response = test_client.get("/install-success?system=teams&organization=Test%20Organization")
    
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Installation Successful!" in response.content.decode("utf-8")
    assert "Test Organization" in response.content.decode("utf-8")
    assert "Teams" in response.content.decode("utf-8")


def test_install_success_page_no_organization(test_client: TestClient):
    """Test installation success page without organization name."""
    response = test_client.get("/install-success?system=slack")
    
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Installation Successful!" in response.content.decode("utf-8")
    assert "N/A" in response.content.decode("utf-8")  # Should show N/A for missing organization


def test_install_success_page_missing_system(test_client: TestClient):
    """Test installation success page with missing system parameter."""
    response = test_client.get("/install-success")
    
    assert response.status_code == 422  # FastAPI validation error for missing required parameter


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