"""
Tests for Teams API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch


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
