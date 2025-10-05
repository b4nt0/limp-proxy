"""
Tests for Slack API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
from limp.models.conversation import Message


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


def test_slack_duplicate_message_detection(test_client: TestClient):
    """Test that duplicate Slack messages are detected and ignored."""
    from limp.models.slack_organization import SlackOrganization
    from limp.models.user import User
    from limp.models.conversation import Conversation
    from limp.database.connection import get_session
    
    # Add a test SlackOrganization to the database
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
        
        # Create a test user and conversation
        user = User(external_id="U789", platform="slack")
        db.add(user)
        db.commit()
        db.refresh(user)
        
        conversation = Conversation(user_id=user.id, context={"channel": "C123"})
        db.add(conversation)
        db.commit()
        db.refresh(conversation)
        
        # Create a message with external_id to simulate a duplicate
        message = Message(
            conversation_id=conversation.id,
            role="user",
            content="Hello",
            external_id="slack_T123456_U789_1234567890.123456"
        )
        db.add(message)
        db.commit()
        
    finally:
        db.close()
    
    # First message - should be processed normally
    message_data = {
        "type": "event_callback",
        "team_id": "T123456",
        "event": {
            "type": "message",
            "user": "U789",
            "channel": "C123",
            "text": "Hello",
            "ts": "1234567890.123456"
        }
    }
    
    with patch('limp.api.slack.IMServiceFactory.create_service') as mock_factory:
        mock_service = Mock()
        mock_service.verify_request.return_value = True
        mock_service.parse_message.return_value = {
            "type": "message",
            "user_id": "U789",
            "channel": "C123",
            "text": "Hello",
            "timestamp": "1234567890.123456",
            "team_id": "T123456"
        }
        mock_factory.return_value = mock_service
        
        # Mock the LLM service to avoid actual API calls
        with patch('limp.api.im.process_llm_workflow') as mock_llm:
            mock_llm.return_value = {"content": "Test response"}
            
            response = test_client.post("/api/slack/webhook", json=message_data)
            assert response.status_code == 200
            result = response.json()
            assert result["status"] == "ok"
            assert result["action"] == "duplicate_ignored"


def test_generate_slack_message_id():
    """Test Slack message ID generation."""
    from limp.api.im import generate_slack_message_id
    
    message_data = {
        "team_id": "T123456",
        "user_id": "U789",
        "timestamp": "1234567890.123456"
    }
    
    external_id = generate_slack_message_id(message_data)
    assert external_id == "slack_T123456_U789_1234567890.123456"
    
    # Test with missing fields
    incomplete_data = {
        "team_id": "T123456",
        "user_id": "U789"
        # Missing timestamp
    }
    
    external_id = generate_slack_message_id(incomplete_data)
    assert external_id == "slack_T123456_U789_unknown"
