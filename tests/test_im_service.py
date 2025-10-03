"""
Tests for IM service functionality.
"""

import pytest
from unittest.mock import Mock, patch
from limp.services.im import SlackService, TeamsService, IMServiceFactory


class TestSlackService:
    """Test Slack service functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            app_id="A09JTJR1R40"
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
    
    @patch('requests.post')
    def test_send_message_success(self, mock_post):
        """Test sending message successfully."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            bot_token="test_bot_token"
        )
        
        result = slack_service.send_message("C123456", "Hello, world!")
        
        assert result is True
        mock_post.assert_called_once()
    
    @patch('requests.post')
    def test_send_message_with_blocks(self, mock_post):
        """Test sending message with blocks."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {"ok": True}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            bot_token="test_bot_token"
        )
        
        metadata = {
            "blocks": [{"type": "section", "text": {"type": "mrkdwn", "text": "Hello!"}}]
        }
        
        result = slack_service.send_message("C123456", "Hello, world!", metadata)
        
        assert result is True
        call_args = mock_post.call_args
        assert "blocks" in call_args[1]["json"]
    
    @patch('requests.post')
    def test_send_message_no_token(self, mock_post):
        """Test sending message without bot token."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
            # No bot_token
        )
        
        result = slack_service.send_message("C123456", "Hello, world!")
        
        assert result is False
        mock_post.assert_not_called()
    
    @patch('limp.config.get_config')
    @patch('limp.api.im.get_bot_url')
    def test_create_authorization_button_with_bot_url(self, mock_get_bot_url, mock_get_config):
        """Test creating authorization button with bot URL configured."""
        # Mock config with bot URL
        mock_config = Mock()
        mock_config.bot.url = "https://example.com"
        mock_get_config.return_value = mock_config
        
        # Mock get_bot_url to return a production URL
        mock_get_bot_url.return_value = "https://example.com"
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = self.slack_service.create_authorization_button(auth_url, button_text, button_description, None)
        
        assert isinstance(result, list)
        assert len(result) == 2  # Section + Actions
        
        # Check section block
        section_block = result[0]
        assert section_block["type"] == "section"
        assert section_block["text"]["type"] == "mrkdwn"
        expected_text = f"{button_description}\n\n:lock: Click the button below to authorize:"
        assert section_block["text"]["text"] == expected_text
        
        # Check actions block
        actions_block = result[1]
        assert actions_block["type"] == "actions"
        assert len(actions_block["elements"]) == 1
        
        button = actions_block["elements"][0]
        assert button["type"] == "button"
        assert button["text"]["text"] == f"🔐 {button_text}"  # Button text now includes emoji
        assert button["value"] == auth_url  # URL stored in value, not url
        assert button["action_id"] == "authorization_button"
        assert button["style"] == "primary"
    
    @patch('limp.config.get_config')
    @patch('limp.api.im.get_bot_url')
    def test_create_authorization_button_without_bot_url(self, mock_get_bot_url, mock_get_config):
        """Test creating authorization button without bot URL (fallback to hyperlink)."""
        # Mock config without bot URL
        mock_config = Mock()
        mock_config.bot.url = None
        mock_get_config.return_value = mock_config
        
        # Mock get_bot_url to return localhost (development mode)
        mock_get_bot_url.return_value = "http://localhost:8000"
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = self.slack_service.create_authorization_button(auth_url, button_text, button_description, None)
        
        assert isinstance(result, list)
        assert len(result) == 2  # Section + Context blocks
        
        # Check section block with hyperlink
        section_block = result[0]
        assert section_block["type"] == "section"
        assert section_block["text"]["type"] == "mrkdwn"
        expected_text = f"{button_description}\n\n:arrow_right: <{auth_url}|*{button_text}*>"
        assert section_block["text"]["text"] == expected_text
        
        # Check context block
        context_block = result[1]
        assert context_block["type"] == "context"
        assert context_block["elements"][0]["type"] == "mrkdwn"
        assert context_block["elements"][0]["text"] == ":warning: *Development Mode* - Click the link above to authorize"
    
    
    @patch('requests.post')
    def test_get_user_dm_channel_success(self, mock_post):
        """Test successful DM channel retrieval."""
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "channel": {"id": "D123456"}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            bot_token="test_bot_token"
        )
        
        result = slack_service.get_user_dm_channel("U123456")
        
        assert result == "D123456"
        mock_post.assert_called_once_with(
            "https://slack.com/api/conversations.open",
            headers={
                "Authorization": "Bearer test_bot_token",
                "Content-Type": "application/json"
            },
            json={"users": "U123456"},
            timeout=10
        )
    
    @patch('requests.post')
    def test_get_user_dm_channel_failure(self, mock_post):
        """Test DM channel retrieval failure."""
        # Mock API failure
        mock_post.side_effect = Exception("API Error")
        
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            bot_token="test_bot_token"
        )
        
        result = slack_service.get_user_dm_channel("U123456")
        
        # Should fallback to user_id
        assert result == "U123456"
    
    def test_get_user_dm_channel_no_token(self):
        """Test DM channel retrieval without bot token."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
            # No bot_token
        )
        
        result = slack_service.get_user_dm_channel("U123456")
        
        # Should fallback to user_id
        assert result == "U123456"

    def test_parse_message_ignore_own_bot(self):
        """Test that messages from own bot are ignored to prevent infinite loops."""
        # This simulates the exact message structure from the user's example
        bot_message_data = {
            'token': 'GV6o3ZOfViTisC2PolCOzAHt',
            'team_id': 'T3AM9MZLH',
            'context_team_id': 'T3AM9MZLH',
            'context_enterprise_id': None,
            'api_app_id': 'A09JTJR1R40',
            'event': {
                'user': 'U09JV5N35MW',
                'type': 'message',
                'ts': '1759512330.731609',
                'bot_id': 'B09JV5N2K96',
                'app_id': 'A09JTJR1R40',  # This matches our app_id
                'text': 'There was an issue communicating with the AI service. Please try again.',
                'team': 'T3AM9MZLH',
                'bot_profile': {
                    'id': 'B09JV5N2K96',
                    'deleted': False,
                    'name': 'LIMP assistant',
                    'updated': 1759267388,
                    'app_id': 'A09JTJR1R40',
                    'user_id': 'U09JV5N35MW',
                    'icons': {
                        'image_36': 'https://a.slack-edge.com/80588/img/plugins/app/bot_36.png',
                        'image_48': 'https://a.slack-edge.com/80588/img/plugins/app/bot_48.png',
                        'image_72': 'https://a.slack-edge.com/80588/img/plugins/app/service_72.png'
                    },
                    'team_id': 'T3AM9MZLH'
                },
                'thread_ts': '1759512327.907089',
                'parent_user_id': 'U3B9SMXQT',
                'blocks': [{
                    'type': 'rich_text',
                    'block_id': 'jdPtg',
                    'elements': [{
                        'type': 'rich_text_section',
                        'elements': [{
                            'type': 'text',
                            'text': 'There was an issue communicating with the AI service. Please try again.'
                        }]
                    }]
                }],
                'channel': 'D09JV5N5B8Q',
                'event_ts': '1759512330.731609',
                'channel_type': 'im'
            },
            'type': 'event_callback',
            'event_id': 'Ev09JKU58UDU',
            'event_time': 1759512330,
            'authorizations': [{
                'enterprise_id': None,
                'team_id': 'T3AM9MZLH',
                'user_id': 'U09JV5N35MW',
                'is_bot': True,
                'is_enterprise_install': False
            }],
            'is_ext_shared_channel': False,
            'event_context': '4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUM0FNOU1aTEgiLCJhaWQiOiJBMDlKVEpSMVI0MCIsImNpZCI6IkQwOUpWNU41QjhRIn0'
        }
        
        result = self.slack_service.parse_message(bot_message_data)
        
        # Should be ignored because event.app_id matches our app_id
        assert result["type"] == "ignored"

    def test_parse_message_allow_other_bot(self):
        """Test that messages from other bots are not ignored."""
        other_bot_message_data = {
            "type": "event_callback",
            "api_app_id": "A_DIFFERENT_APP_ID",
            "event": {
                "type": "message",
                "user": "U123456",
                "channel": "C123456",
                "text": "Hello from another bot!",
                "ts": "1234567890.123456",
                "app_id": "A_DIFFERENT_APP_ID"  # Different app_id
            }
        }
        
        result = self.slack_service.parse_message(other_bot_message_data)
        
        # Should be processed normally
        assert result["type"] == "message"
        assert result["user_id"] == "U123456"
        assert result["channel"] == "C123456"
        assert result["text"] == "Hello from another bot!"

    def test_parse_message_no_app_id_not_ignored(self):
        """Test that messages without event.app_id are not ignored."""
        message_without_app_id = {
            "type": "event_callback",
            "api_app_id": "A09JTJR1R40",
            "event": {
                "type": "message",
                "user": "U123456",
                "channel": "C123456",
                "text": "Hello from user without app_id!",
                "ts": "1234567890.123456"
                # No app_id field in event
            }
        }
        
        result = self.slack_service.parse_message(message_without_app_id)
        
        # Should be processed normally even though api_app_id matches our app_id
        # because event.app_id is missing
        assert result["type"] == "message"
        assert result["user_id"] == "U123456"
        assert result["channel"] == "C123456"
        assert result["text"] == "Hello from user without app_id!"


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
    
    @patch('limp.config.get_config')
    @patch('limp.api.im.get_bot_url')
    def test_create_authorization_button(self, mock_get_bot_url, mock_get_config):
        """Test creating authorization button for Teams."""
        # Mock config with bot URL (for interactive button)
        mock_config = Mock()
        mock_config.bot.url = "https://example.com"
        mock_get_config.return_value = mock_config
        
        # Mock get_bot_url to return a production URL
        mock_get_bot_url.return_value = "https://example.com"
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = self.teams_service.create_authorization_button(auth_url, button_text, button_description, None)
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        # Check adaptive card
        card = result[0]
        assert card["contentType"] == "application/vnd.microsoft.card.adaptive"
        assert card["content"]["type"] == "AdaptiveCard"
        assert card["content"]["version"] == "1.3"
        
        # Check body
        body = card["content"]["body"][0]
        assert body["type"] == "TextBlock"
        expected_text = f"{button_description}\n\n🔒 Click the button below to authorize:"
        assert body["text"] == expected_text
        
        # Check actions
        action = card["content"]["actions"][0]
        assert action["type"] == "Action.OpenUrl"
        assert action["title"] == f"🔐 {button_text}"
        assert action["url"] == auth_url
    
    def test_get_user_dm_channel(self):
        """Test Teams DM channel retrieval."""
        result = self.teams_service.get_user_dm_channel("U123456")
        
        # Teams uses user_id as DM channel
        assert result == "U123456"
    


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
