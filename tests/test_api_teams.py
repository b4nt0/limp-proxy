"""
Tests for Teams API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


def test_teams_webhook_message(test_client: TestClient):
    """Test Teams webhook message handling with async processing."""
    message_data = {
        "type": "message",
        "from": {"id": "U123456"},
        "conversation": {"id": "C123456"},
        "text": "Hello, bot!",
        "timestamp": "1234567890.123456"
    }
    
    with patch('limp.api.teams.IMServiceFactory.create_service') as mock_factory:
        mock_service = Mock()
        mock_service.verify_request.return_value = True
        mock_factory.return_value = mock_service
        
        # Test that the webhook responds immediately
        response = test_client.post("/api/teams/webhook", json=message_data)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        
        # The background processing should be queued but not block the response
        # We can't easily test the background task completion in this unit test
        # but we can verify the immediate response works


def test_teams_message_parsing():
    """Test that Teams message parsing works correctly for the full pipeline."""
    from limp.services.teams import TeamsService
    
    # Create a mock Teams service
    teams_service = TeamsService("test_app_id", "test_client_id", "test_client_secret")
    
    # Test message data
    message_data = {
        "type": "message",
        "from": {"id": "U123456"},
        "conversation": {"id": "C123456"},
        "text": "Hello, bot!",
        "timestamp": "1234567890.123456"
    }
    
    # Test that parse_message works correctly for the full pipeline
    parsed = teams_service.parse_message(message_data)
    assert parsed["type"] == "message"
    assert parsed["text"] == "Hello, bot!"
    assert parsed["user_id"] == "U123456"
    assert parsed["channel"] == "C123456"


@pytest.mark.asyncio
async def test_teams_echo_functionality():
    """Test that Teams echo functionality works through the original EchoBot approach."""
    from limp.services.teams import TeamsService
    from unittest.mock import Mock, AsyncMock
    
    # Create a mock Teams service
    teams_service = TeamsService("test_app_id", "test_client_id", "test_client_secret")
    
    # Mock the adapter's process_activity method
    teams_service._adapter.process_activity = AsyncMock(return_value=None)
    
    # Test activity data (Bot Framework format)
    activity_data = {
        "type": "message",
        "from": {"id": "U123456"},
        "conversation": {"id": "C123456"},
        "text": "Hello, bot!",
        "timestamp": "2023-10-24T18:59:44.061Z"
    }
    
    # Test the echo functionality through process_activity
    result = await teams_service.process_activity(activity_data, "auth_header", None)
    
    # Verify the result
    assert result == True
    
    # Verify that the adapter's process_activity was called
    teams_service._adapter.process_activity.assert_called_once()
