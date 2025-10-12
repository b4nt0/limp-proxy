"""
Tests for authentication flow implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta

from limp.api.im import handle_user_message
from limp.services.oauth2 import OAuth2Service
from limp.services.im import SlackService, TeamsService
from limp.models.user import User
from limp.models.auth import AuthToken
from limp.config import ExternalSystemConfig, OAuth2Config


class TestAuthenticationFlow:
    """Test the complete authentication flow implementation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_im_service = Mock(spec=SlackService)
        self.mock_db_session = Mock()
        self.mock_user = Mock()
        self.mock_user.id = 1
        self.mock_user.external_id = "U123456"
        self.mock_user.platform = "slack"
        
        # Mock message data
        self.message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "text": "Hello, bot!",
            "timestamp": "1234567890.123456"
        }
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.LLMService')
    @patch('limp.api.im.ToolsService')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_no_primary_system(self, mock_generate_id, mock_is_duplicate, mock_tools_service, mock_llm_service, mock_oauth2_service, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test message handling when no primary system is configured."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with no primary system
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.external_systems = []
        mock_config.bot.system_prompts = []  # Mock bot config with empty system prompts
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock services
        mock_llm_instance = Mock()
        mock_llm_instance.chat_completion.return_value = {"content": "Test response"}
        mock_llm_instance.is_tool_call_response.return_value = False
        mock_llm_service.return_value = mock_llm_instance
        
        mock_tools_instance = Mock()
        mock_tools_instance.get_available_tools.return_value = []
        mock_tools_service.return_value = mock_tools_instance
        
        # Mock IM service
        self.mock_im_service.reply_to_message.return_value = True
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify that normal processing continues (no authorization check)
        assert result["status"] == "ok"
        assert "action" not in result
        mock_get_user.assert_called_once()
        self.mock_im_service.reply_to_message.assert_called_once()
        
        # Verify that format_messages_with_context was called with system prompts
        mock_llm_instance.format_messages_with_context.assert_called_once()
        call_args = mock_llm_instance.format_messages_with_context.call_args
        assert call_args[0][0] == ""  # user_message is empty since it's already in conversation history
        assert call_args[0][1] == []  # conversation_history (empty in this test case)
        assert call_args[0][2] == []  # system_prompts (empty because no primary system)
        
        # Verify that the user message was stored in the database
        mock_store_user_message.assert_called_once_with(
            self.mock_db_session,
            1,  # conversation_id
            "Hello, bot!",  # content
            "1234567890.123456",  # timestamp
            "test_external_id"  # external_id
        )
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.LLMService')
    @patch('limp.api.im.ToolsService')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_with_system_prompts(self, mock_generate_id, mock_is_duplicate, mock_tools_service, mock_llm_service, mock_oauth2_service, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test message handling with system prompts configured."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with system prompts
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.external_systems = []
        mock_config.bot.system_prompts = [
            "You are a helpful AI assistant.",
            "Always be polite and professional.",
            "If you need to access external systems, ask the user to authorize access first."
        ]
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock services
        mock_llm_instance = Mock()
        mock_llm_instance.chat_completion.return_value = {"content": "Test response"}
        mock_llm_instance.is_tool_call_response.return_value = False
        mock_llm_service.return_value = mock_llm_instance
        
        mock_tools_instance = Mock()
        mock_tools_instance.get_available_tools.return_value = []
        mock_tools_service.return_value = mock_tools_instance
        
        # Mock IM service
        self.mock_im_service.reply_to_message.return_value = True
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify that normal processing continues
        assert result["status"] == "ok"
        assert "action" not in result
        mock_get_user.assert_called_once()
        self.mock_im_service.reply_to_message.assert_called_once()
        
        # Verify that format_messages_with_context was called with system prompts
        mock_llm_instance.format_messages_with_context.assert_called_once()
        call_args = mock_llm_instance.format_messages_with_context.call_args
        assert call_args[0][0] == ""  # user_message is empty since it's already in conversation history
        assert call_args[0][1] == []  # conversation_history (empty in this test case)
        assert call_args[0][2] == [  # system_prompts
            "You are a helpful AI assistant.",
            "Always be polite and professional.",
            "If you need to access external systems, ask the user to authorize access first."
        ]
        
        # Verify that the user message was stored in the database
        mock_store_user_message.assert_called_once_with(
            self.mock_db_session,
            1,  # conversation_id
            "Hello, bot!",  # content
            "1234567890.123456",  # timestamp
            "test_external_id"  # external_id
        )
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.LLMService')
    @patch('limp.api.im.ToolsService')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_valid_token(self, mock_generate_id, mock_is_duplicate, mock_tools_service, mock_llm_service, mock_oauth2_service, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test message handling when user has valid token."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with primary system
        mock_primary_system = Mock()
        mock_primary_system.name = "test-system"
        mock_config = Mock()
        mock_config.get_primary_system.return_value = mock_primary_system
        mock_config.llm = Mock()
        mock_config.external_systems = []
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock OAuth2 service with valid token
        mock_oauth2_instance = Mock()
        mock_token = Mock()
        mock_oauth2_instance.get_valid_token.return_value = mock_token
        mock_oauth2_instance.validate_token.return_value = True
        mock_oauth2_service.return_value = mock_oauth2_instance
        
        # Mock services
        mock_llm_instance = Mock()
        mock_llm_instance.chat_completion.return_value = {"content": "Test response"}
        mock_llm_instance.is_tool_call_response.return_value = False
        mock_llm_service.return_value = mock_llm_instance
        
        mock_tools_instance = Mock()
        mock_tools_instance.get_available_tools.return_value = []
        mock_tools_service.return_value = mock_tools_instance
        
        # Mock IM service
        self.mock_im_service.reply_to_message.return_value = True
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify that normal processing continues
        assert result["status"] == "ok"
        assert "action" not in result
        mock_oauth2_instance.get_valid_token.assert_called_once_with(1, "test-system")
        mock_oauth2_instance.validate_token.assert_called_once_with(mock_token, mock_primary_system)
        self.mock_im_service.reply_to_message.assert_called_once()
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_no_token(self, mock_generate_id, mock_is_duplicate, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test message handling when user has no token."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with primary system
        mock_primary_system = Mock()
        mock_primary_system.name = "test-system"
        mock_config = Mock()
        mock_config.get_primary_system.return_value = mock_primary_system
        mock_config.bot.url = ""  # Empty bot URL to trigger fallback
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock OAuth2 service with no token
        mock_oauth2_instance = Mock()
        mock_oauth2_instance.get_valid_token.return_value = None
        mock_oauth2_service.return_value = mock_oauth2_instance
        
        # Mock IM service methods
        self.mock_im_service.get_user_dm_channel.return_value = "D123456"
        self.mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        self.mock_im_service.send_message.return_value = True
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify authorization flow
        assert result["status"] == "ok"
        assert result["action"] == "authorization_required"
        
        # Verify OAuth2 service calls
        mock_oauth2_instance.get_valid_token.assert_called_once_with(1, "test-system")
        mock_oauth2_instance.generate_auth_url.assert_called_once_with(1, mock_primary_system, "http://localhost:8000")
        
        # Verify IM service calls
        self.mock_im_service.get_user_dm_channel.assert_called_once_with("U123456")
        self.mock_im_service.create_authorization_button.assert_called_once()
        self.mock_im_service.send_message.assert_called_once()
        
        # Verify no reply to original message
        self.mock_im_service.reply_to_message.assert_not_called()
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_invalid_token(self, mock_generate_id, mock_is_duplicate, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test message handling when user has invalid token."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with primary system
        mock_primary_system = Mock()
        mock_primary_system.name = "test-system"
        mock_config = Mock()
        mock_config.get_primary_system.return_value = mock_primary_system
        mock_config.bot.url = ""  # Empty bot URL to trigger fallback
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock OAuth2 service with invalid token
        mock_oauth2_instance = Mock()
        mock_token = Mock()
        mock_oauth2_instance.get_valid_token.return_value = mock_token
        mock_oauth2_instance.validate_token.return_value = False
        mock_oauth2_service.return_value = mock_oauth2_instance
        
        # Mock IM service methods
        self.mock_im_service.get_user_dm_channel.return_value = "D123456"
        self.mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        self.mock_im_service.send_message.return_value = True
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify authorization flow
        assert result["status"] == "ok"
        assert result["action"] == "authorization_required"
        
        # Verify OAuth2 service calls
        mock_oauth2_instance.get_valid_token.assert_called_once_with(1, "test-system")
        mock_oauth2_instance.validate_token.assert_called_once_with(mock_token, mock_primary_system)
        mock_oauth2_instance.generate_auth_url.assert_called_once_with(1, mock_primary_system, "http://localhost:8000")
        
        # Verify IM service calls
        self.mock_im_service.get_user_dm_channel.assert_called_once_with("U123456")
        self.mock_im_service.create_authorization_button.assert_called_once()
        self.mock_im_service.send_message.assert_called_once()
        
        # Verify no reply to original message
        self.mock_im_service.reply_to_message.assert_not_called()


class TestOAuth2TokenValidation:
    """Test OAuth2 token validation functionality."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_db_session = Mock()
        self.oauth2_service = OAuth2Service(self.mock_db_session)
    
    def test_validate_token_with_test_endpoint(self):
        """Test token validation using configured test endpoint."""
        # Mock system config with test endpoint
        mock_system_config = Mock()
        mock_system_config.oauth2.test_endpoint = "https://example.com/oauth/introspect"
        mock_system_config.base_url = "https://example.com/api"
        
        # Mock token
        mock_token = Mock()
        mock_token.access_token = "test_token"
        mock_token.token_type = "Bearer"
        mock_token.expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Mock introspection response
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"active": True}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = self.oauth2_service.validate_token(mock_token, mock_system_config)
            
            assert result is True
            mock_post.assert_called_once_with(
                "https://example.com/oauth/introspect",
                data={
                    "token": "test_token",
                    "token_type_hint": "access_token"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )
    
    def test_validate_token_with_heuristic_endpoint(self):
        """Test token validation using heuristic endpoint."""
        # Mock system config without test endpoint
        mock_system_config = Mock()
        mock_system_config.oauth2.test_endpoint = None
        mock_system_config.oauth2.authorization_url = "https://example.com/oauth/authorize"
        mock_system_config.base_url = "https://example.com/api"
        
        # Mock token
        mock_token = Mock()
        mock_token.access_token = "test_token"
        mock_token.token_type = "Bearer"
        mock_token.expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Mock introspection response
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"active": True}
            mock_response.raise_for_status.return_value = None
            mock_post.return_value = mock_response
            
            result = self.oauth2_service.validate_token(mock_token, mock_system_config)
            
            assert result is True
            # Should use heuristic endpoint
            mock_post.assert_called_once_with(
                "https://example.com/oauth/introspect",
                data={
                    "token": "test_token",
                    "token_type_hint": "access_token"
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=10
            )
    
    def test_validate_token_expired(self):
        """Test token validation with expired token."""
        # Mock system config
        mock_system_config = Mock()
        mock_system_config.oauth2.test_endpoint = "https://example.com/oauth/introspect"
        mock_system_config.base_url = "https://example.com/api"
        
        # Mock expired token
        mock_token = Mock()
        mock_token.expires_at = datetime.utcnow() - timedelta(hours=1)  # Expired
        
        result = self.oauth2_service.validate_token(mock_token, mock_system_config)
        
        assert result is False
    
    def test_validate_token_introspection_fallback(self):
        """Test token validation with introspection failure and test request fallback."""
        # Mock system config
        mock_system_config = Mock()
        mock_system_config.oauth2.test_endpoint = "https://example.com/oauth/introspect"
        mock_system_config.base_url = "https://example.com/api"
        
        # Mock token
        mock_token = Mock()
        mock_token.access_token = "test_token"
        mock_token.token_type = "Bearer"
        mock_token.expires_at = datetime.utcnow() + timedelta(hours=1)
        
        # Mock introspection failure and test request success
        with patch('requests.post') as mock_post, patch('requests.get') as mock_get:
            # Introspection fails
            mock_post.side_effect = Exception("Introspection failed")
            
            # Test request succeeds
            mock_response = Mock()
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            result = self.oauth2_service.validate_token(mock_token, mock_system_config)
            
            assert result is True
            mock_get.assert_called_once_with(
                "https://example.com/api",
                headers={
                    "Authorization": "Bearer test_token",
                    "Content-Type": "application/json"
                },
                timeout=10
            )


class TestIMServiceAuthorizationButtons:
    """Test IM service authorization button functionality."""
    
    def test_slack_create_authorization_button_with_production_url(self):
        """Test Slack authorization button creation with production URL (should use button)."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
        )
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = slack_service.create_authorization_button(auth_url, button_text, button_description, None)
        
        assert isinstance(result, list)
        assert len(result) == 2  # Section + Actions
        
        # Check section block
        section_block = result[0]
        assert section_block["type"] == "section"
        assert section_block["text"]["type"] == "mrkdwn"
        expected_text = f"{button_description}\n\n🔒 Click the button below to authorize:"
        assert section_block["text"]["text"] == expected_text
        
        # Check actions block
        actions_block = result[1]
        assert actions_block["type"] == "actions"
        assert len(actions_block["elements"]) == 1
        
        button = actions_block["elements"][0]
        assert button["type"] == "button"
        assert button["text"]["text"] == f"🔐 {button_text}"
        assert button["url"] == auth_url  # URL field for direct browser opening
        assert button["style"] == "primary"
    
    def test_slack_create_authorization_button_with_localhost_url(self):
        """Test Slack authorization button creation with localhost URL (should use hyperlink)."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
        )
        
        auth_url = "http://localhost:8000/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = slack_service.create_authorization_button(auth_url, button_text, button_description, None)
        
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
        assert context_block["elements"][0]["text"] == ":computer: Click the link above to open authorization in your browser"
    
    @patch('limp.config.get_config')
    @patch('limp.api.im.get_bot_url')
    def test_teams_create_authorization_button(self, mock_get_bot_url, mock_get_config):
        """Test Teams authorization button creation."""
        # Mock config with bot URL (for interactive button)
        mock_config = Mock()
        mock_config.bot.url = "https://example.com"
        mock_get_config.return_value = mock_config
        
        # Mock get_bot_url to return a production URL
        mock_get_bot_url.return_value = "https://example.com"
        
        teams_service = TeamsService(
            app_id="test_app_id",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = teams_service.create_authorization_button(auth_url, button_text, button_description, None)
        
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
        expected_text = f"{button_description}\n\n➡️ **{button_text}**"
        assert body["text"] == expected_text
        
        # Check context text
        context_body = card["content"]["body"][1]
        assert context_body["type"] == "TextBlock"
        assert context_body["text"] == "💻 Click the link above to open authorization in your browser"
        
        # Check actions
        action = card["content"]["actions"][0]
        assert action["type"] == "Action.OpenUrl"
        assert action["title"] == f"🔐 {button_text}"
        assert action["url"] == auth_url
    
    @patch('requests.post')
    def test_slack_get_user_dm_channel_success(self, mock_post):
        """Test successful Slack DM channel retrieval."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            bot_token="test_bot_token"
        )
        
        # Mock successful API response
        mock_response = Mock()
        mock_response.json.return_value = {
            "ok": True,
            "channel": {"id": "D123456"}
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
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
    def test_slack_get_user_dm_channel_failure(self, mock_post):
        """Test Slack DM channel retrieval failure."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret",
            bot_token="test_bot_token"
        )
        
        # Mock API failure
        mock_post.side_effect = Exception("API Error")
        
        result = slack_service.get_user_dm_channel("U123456")
        
        # Should fallback to user_id
        assert result == "U123456"
    
    def test_slack_get_user_dm_channel_no_token(self):
        """Test Slack DM channel retrieval without bot token."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
            # No bot_token
        )
        
        result = slack_service.get_user_dm_channel("U123456")
        
        # Should fallback to user_id
        assert result == "U123456"
    
    def test_teams_get_user_dm_channel(self):
        """Test Teams DM channel retrieval."""
        teams_service = TeamsService(
            app_id="test_app_id",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        result = teams_service.get_user_dm_channel("U123456")
        
        # Teams uses user_id as DM channel
        assert result == "U123456"


class TestConfigurationUpdates:
    """Test configuration model updates for authentication flow."""
    
    def test_oauth2_config_with_test_endpoint(self):
        """Test OAuth2Config with test_endpoint parameter."""
        from limp.config import OAuth2Config
        
        config = OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            authorization_url="https://example.com/oauth/authorize",
            token_url="https://example.com/oauth/token",
            redirect_uri="http://localhost:8000/callback",
            test_endpoint="https://example.com/oauth/introspect"
        )
        
        assert config.test_endpoint == "https://example.com/oauth/introspect"
    
    def test_oauth2_config_without_test_endpoint(self):
        """Test OAuth2Config without test_endpoint parameter."""
        from limp.config import OAuth2Config
        
        config = OAuth2Config(
            client_id="test_client_id",
            client_secret="test_client_secret",
            authorization_url="https://example.com/oauth/authorize",
            token_url="https://example.com/oauth/token",
            redirect_uri="http://localhost:8000/callback"
        )
        
        assert config.test_endpoint is None
    
    def test_external_system_config_primary(self):
        """Test ExternalSystemConfig with primary flag."""
        from limp.config import ExternalSystemConfig, OAuth2Config
        
        config = ExternalSystemConfig(
            name="test-system",
            oauth2=OAuth2Config(
                client_id="test_client_id",
                client_secret="test_client_secret",
                authorization_url="https://example.com/oauth/authorize",
                token_url="https://example.com/oauth/token",
                redirect_uri="http://localhost:8000/callback"
            ),
            openapi_spec="https://example.com/api/openapi.json",
            base_url="https://example.com/api",
            primary=True
        )
        
        assert config.primary is True


class TestFinishReasonHandling:
    """Test finish_reason handling in handle_user_message."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_im_service = Mock(spec=SlackService)
        self.mock_db_session = Mock()
        self.mock_user = Mock()
        self.mock_user.id = 1
        self.mock_user.external_id = "U123456"
        self.mock_user.platform = "slack"
        
        # Mock message data
        self.message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "text": "Hello, bot!",
            "timestamp": "1234567890.123456"
        }
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.process_llm_workflow')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_successful_finish_reason_stop(self, mock_generate_id, mock_is_duplicate, mock_process_llm_workflow, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test that finish_reason 'stop' is marked as successful."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with no primary system
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.llm.base_url = "https://api.openai.com/v1"
        mock_config.llm.api_key = "test-key"
        mock_config.llm.model = "gpt-4"
        mock_config.llm.max_tokens = 1000
        mock_config.llm.temperature = 0.7
        mock_config.llm.max_iterations = 3
        mock_config.external_systems = []
        mock_config.bot = Mock()
        mock_config.bot.system_prompts = []
        mock_config.bot.url = "http://localhost:8000"
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock LLM workflow with successful finish_reason
        mock_process_llm_workflow.return_value = {
            "content": "Test response",
            "finish_reason": "stop"
        }
        
        # Mock IM service
        self.mock_im_service.acknowledge_message.return_value = None
        self.mock_im_service.reply_to_message.return_value = True
        self.mock_im_service.complete_message.return_value = None
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify success
        assert result["status"] == "ok"
        self.mock_im_service.complete_message.assert_called_once_with(
            "C123456",
            "1234567890.123456",
            success=True
        )
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.process_llm_workflow')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_failed_finish_reason_length(self, mock_generate_id, mock_is_duplicate, mock_process_llm_workflow, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test that finish_reason 'length' is marked as failed."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with no primary system
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.llm.base_url = "https://api.openai.com/v1"
        mock_config.llm.api_key = "test-key"
        mock_config.llm.model = "gpt-4"
        mock_config.llm.max_tokens = 1000
        mock_config.llm.temperature = 0.7
        mock_config.llm.max_iterations = 3
        mock_config.external_systems = []
        mock_config.bot = Mock()
        mock_config.bot.system_prompts = []
        mock_config.bot.url = "http://localhost:8000"
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock LLM workflow with truncated finish_reason
        mock_process_llm_workflow.return_value = {
            "content": "Test response [truncated]",
            "finish_reason": "length"
        }
        
        # Mock IM service
        self.mock_im_service.acknowledge_message.return_value = None
        self.mock_im_service.reply_to_message.return_value = True
        self.mock_im_service.complete_message.return_value = None
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify failure
        assert result["status"] == "ok"
        self.mock_im_service.complete_message.assert_called_once_with(
            "C123456",
            "1234567890.123456",
            success=False
        )
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.process_llm_workflow')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_failed_finish_reason_tool_calls(self, mock_generate_id, mock_is_duplicate, mock_process_llm_workflow, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test that finish_reason 'tool_calls' is marked as failed for final messages."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with no primary system
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.llm.base_url = "https://api.openai.com/v1"
        mock_config.llm.api_key = "test-key"
        mock_config.llm.model = "gpt-4"
        mock_config.llm.max_tokens = 1000
        mock_config.llm.temperature = 0.7
        mock_config.llm.max_iterations = 3
        mock_config.external_systems = []
        mock_config.bot = Mock()
        mock_config.bot.system_prompts = []
        mock_config.bot.url = "http://localhost:8000"
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock LLM workflow with tool_calls finish_reason (should be failed for final message)
        mock_process_llm_workflow.return_value = {
            "content": "Test response",
            "finish_reason": "tool_calls"
        }
        
        # Mock IM service
        self.mock_im_service.acknowledge_message.return_value = None
        self.mock_im_service.reply_to_message.return_value = True
        self.mock_im_service.complete_message.return_value = None
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify failure
        assert result["status"] == "ok"
        self.mock_im_service.complete_message.assert_called_once_with(
            "C123456",
            "1234567890.123456",
            success=False
        )
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.get_or_create_conversation')
    @patch('limp.api.im.store_user_message')
    @patch('limp.api.im.get_conversation_history')
    @patch('limp.api.im.store_assistant_message')
    @patch('limp.api.im.process_llm_workflow')
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_handle_user_message_backward_compatibility_none_finish_reason(self, mock_generate_id, mock_is_duplicate, mock_process_llm_workflow, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test that None finish_reason is marked as successful for backward compatibility."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with no primary system
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.llm.base_url = "https://api.openai.com/v1"
        mock_config.llm.api_key = "test-key"
        mock_config.llm.model = "gpt-4"
        mock_config.llm.max_tokens = 1000
        mock_config.llm.temperature = 0.7
        mock_config.llm.max_iterations = 3
        mock_config.external_systems = []
        mock_config.bot = Mock()
        mock_config.bot.system_prompts = []
        mock_config.bot.url = "http://localhost:8000"
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock conversation management
        mock_conversation = Mock()
        mock_conversation.id = 1
        mock_get_or_create_conversation.return_value = mock_conversation
        mock_get_conversation_history.return_value = []
        mock_store_user_message.return_value = Mock()
        mock_store_assistant_message.return_value = Mock()
        
        # Mock LLM workflow with None finish_reason (backward compatibility)
        mock_process_llm_workflow.return_value = {
            "content": "Test response",
            "finish_reason": None
        }
        
        # Mock IM service
        self.mock_im_service.acknowledge_message.return_value = None
        self.mock_im_service.reply_to_message.return_value = True
        self.mock_im_service.complete_message.return_value = None
        
        # Call the function
        result = await handle_user_message(
            self.message_data,
            self.mock_im_service,
            self.mock_db_session,
            "slack"
        )
        
        # Verify success (backward compatibility)
        assert result["status"] == "ok"
        self.mock_im_service.complete_message.assert_called_once_with(
            "C123456",
            "1234567890.123456",
            success=True
        )
