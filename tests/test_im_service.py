"""
Tests for IM service functionality.
"""

import pytest
from limp.services.im import SlackService, TeamsService, IMServiceFactory


class TestSlackService:
    """Test Slack service functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
        )
    
    def test_parse_message_challenge(self):
        """Test parsing URL verification challenge."""
        challenge_data = {
            "type": "url_verification",
            "challenge": "test_challenge_123"
        }
        
        result = self.slack_service.parse_message(challenge_data)
        
        assert result["type"] == "challenge"
        assert result["challenge"] == "test_challenge_123"
    
    def test_parse_message_regular_message(self):
        """Test parsing regular message."""
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
        
        result = self.slack_service.parse_message(message_data)
        
        assert result["type"] == "message"
        assert result["user_id"] == "U123456"
        assert result["channel"] == "C123456"
        assert result["text"] == "Hello, bot!"
        assert result["timestamp"] == "1234567890.123456"
    
    def test_parse_message_app_mention(self):
        """Test parsing app_mention message."""
        app_mention_data = {
            "type": "event_callback",
            "event": {
                "user": "U3B9SMXQT",
                "type": "app_mention",
                "ts": "1759477793.035939",
                "client_msg_id": "e7fda91d-7b8e-411f-aca8-0a608b7d684b",
                "text": "<@U09JV5N35MW> test11",
                "team": "T3AM9MZLH",
                "blocks": [
                    {
                        "type": "rich_text",
                        "block_id": "LgE8E",
                        "elements": [
                            {
                                "type": "rich_text_section",
                                "elements": [
                                    {"type": "user", "user_id": "U09JV5N35MW"},
                                    {"type": "text", "text": " test11"}
                                ]
                            }
                        ]
                    }
                ]
            },
            "channel": "C3C2K7GT1",
            "event_ts": "1759477793.035939"
        }
        
        result = self.slack_service.parse_message(app_mention_data)
        
        assert result["type"] == "message"
        assert result["user_id"] == "U3B9SMXQT"
        assert result["channel"] == "C3C2K7GT1"
        assert result["text"] == "<@U09JV5N35MW> test11"
        assert result["timestamp"] == "1759477793.035939"
    
    def test_parse_message_app_mention_with_channel_in_event(self):
        """Test parsing app_mention with channel in event object."""
        app_mention_data = {
            "type": "event_callback",
            "event": {
                "user": "U123456",
                "type": "app_mention",
                "channel": "C789012",
                "text": "<@U09JV5N35MW> hello",
                "ts": "1234567890.123456"
            }
        }
        
        result = self.slack_service.parse_message(app_mention_data)
        
        assert result["type"] == "message"
        assert result["user_id"] == "U123456"
        assert result["channel"] == "C789012"  # Should use channel from event
        assert result["text"] == "<@U09JV5N35MW> hello"
        assert result["timestamp"] == "1234567890.123456"
    
    def test_parse_message_bot_message_ignored(self):
        """Test that bot messages are ignored."""
        bot_message_data = {
            "type": "event_callback",
            "event": {
                "type": "message",
                "user": "U123456",
                "channel": "C123456",
                "text": "Bot message",
                "ts": "1234567890.123456",
                "bot_id": "B123456"  # This should cause the message to be ignored
            }
        }
        
        result = self.slack_service.parse_message(bot_message_data)
        
        assert result["type"] == "unknown"
    
    def test_parse_message_app_mention_bot_message_ignored(self):
        """Test that bot app_mention messages are ignored."""
        bot_app_mention_data = {
            "type": "event_callback",
            "event": {
                "type": "app_mention",
                "user": "U123456",
                "channel": "C123456",
                "text": "<@U09JV5N35MW> Bot mention",
                "ts": "1234567890.123456",
                "bot_id": "B123456"  # This should cause the message to be ignored
            }
        }
        
        result = self.slack_service.parse_message(bot_app_mention_data)
        
        assert result["type"] == "unknown"
    
    def test_parse_message_unknown_event_type(self):
        """Test parsing unknown event type."""
        unknown_data = {
            "type": "event_callback",
            "event": {
                "type": "unknown_event",
                "user": "U123456",
                "channel": "C123456",
                "text": "Some text",
                "ts": "1234567890.123456"
            }
        }
        
        result = self.slack_service.parse_message(unknown_data)
        
        assert result["type"] == "unknown"
    
    def test_parse_message_unknown_request_type(self):
        """Test parsing unknown request type."""
        unknown_data = {
            "type": "unknown_type",
            "data": "some data"
        }
        
        result = self.slack_service.parse_message(unknown_data)
        
        assert result["type"] == "unknown"
    
    def test_format_response_basic(self):
        """Test formatting basic response."""
        content = "Hello, world!"
        result = self.slack_service.format_response(content)
        
        assert result["text"] == "Hello, world!"
        assert result["response_type"] == "in_channel"
        assert "blocks" not in result
    
    def test_format_response_with_blocks(self):
        """Test formatting response with blocks."""
        content = "Hello, world!"
        metadata = {
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "Hello, world!"
                    }
                }
            ]
        }
        result = self.slack_service.format_response(content, metadata)
        
        assert result["text"] == "Hello, world!"
        assert result["response_type"] == "in_channel"
        assert "blocks" in result
        assert result["blocks"] == metadata["blocks"]
    
    def test_send_message(self):
        """Test sending message (placeholder implementation)."""
        result = self.slack_service.send_message("C123456", "Hello, world!")
        
        # Current implementation returns True as placeholder
        assert result is True


class TestTeamsService:
    """Test Teams service functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.teams_service = TeamsService(
            app_id="test_app_id",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
    
    def test_parse_message_regular_message(self):
        """Test parsing Teams message."""
        message_data = {
            "type": "message",
            "from": {"id": "U123456"},
            "conversation": {"id": "C123456"},
            "text": "Hello, bot!",
            "timestamp": "1234567890.123456"
        }
        
        result = self.teams_service.parse_message(message_data)
        
        assert result["type"] == "message"
        assert result["user_id"] == "U123456"
        assert result["channel"] == "C123456"
        assert result["text"] == "Hello, bot!"
        assert result["timestamp"] == "1234567890.123456"
    
    def test_parse_message_unknown_type(self):
        """Test parsing unknown Teams message type."""
        unknown_data = {
            "type": "unknown_type",
            "data": "some data"
        }
        
        result = self.teams_service.parse_message(unknown_data)
        
        assert result["type"] == "unknown"
    
    def test_format_response_basic(self):
        """Test formatting basic Teams response."""
        content = "Hello, world!"
        result = self.teams_service.format_response(content)
        
        assert result["type"] == "message"
        assert result["text"] == "Hello, world!"
        assert "attachments" not in result
    
    def test_format_response_with_attachments(self):
        """Test formatting Teams response with attachments."""
        content = "Hello, world!"
        metadata = {
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": {
                        "type": "AdaptiveCard",
                        "body": [
                            {
                                "type": "TextBlock",
                                "text": "Hello, world!"
                            }
                        ]
                    }
                }
            ]
        }
        result = self.teams_service.format_response(content, metadata)
        
        assert result["type"] == "message"
        assert result["text"] == "Hello, world!"
        assert "attachments" in result
        assert result["attachments"] == metadata["attachments"]
    
    def test_send_message(self):
        """Test sending Teams message (placeholder implementation)."""
        result = self.teams_service.send_message("C123456", "Hello, world!")
        
        # Current implementation returns True as placeholder
        assert result is True


class TestIMServiceFactory:
    """Test IM service factory."""
    
    def test_create_slack_service(self):
        """Test creating Slack service."""
        config = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "signing_secret": "test_signing_secret"
        }
        
        service = IMServiceFactory.create_service("slack", config)
        
        assert isinstance(service, SlackService)
        assert service.client_id == "test_client_id"
        assert service.client_secret == "test_client_secret"
        assert service.signing_secret == "test_signing_secret"
    
    def test_create_teams_service(self):
        """Test creating Teams service."""
        config = {
            "app_id": "test_app_id",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }
        
        service = IMServiceFactory.create_service("teams", config)
        
        assert isinstance(service, TeamsService)
        assert service.app_id == "test_app_id"
        assert service.client_id == "test_client_id"
        assert service.client_secret == "test_client_secret"
    
    def test_create_unsupported_platform(self):
        """Test creating service for unsupported platform."""
        config = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }
        
        with pytest.raises(ValueError, match="Unsupported platform: discord"):
            IMServiceFactory.create_service("discord", config)
    
    def test_create_slack_service_case_insensitive(self):
        """Test creating Slack service with case insensitive platform name."""
        config = {
            "client_id": "test_client_id",
            "client_secret": "test_client_secret",
            "signing_secret": "test_signing_secret"
        }
        
        service = IMServiceFactory.create_service("SLACK", config)
        
        assert isinstance(service, SlackService)
    
    def test_create_teams_service_case_insensitive(self):
        """Test creating Teams service with case insensitive platform name."""
        config = {
            "app_id": "test_app_id",
            "client_id": "test_client_id",
            "client_secret": "test_client_secret"
        }
        
        service = IMServiceFactory.create_service("TEAMS", config)
        
        assert isinstance(service, TeamsService)
