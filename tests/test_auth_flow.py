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
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.LLMService')
    @patch('limp.api.im.ToolsService')
    @pytest.mark.asyncio
    async def test_handle_user_message_no_primary_system(self, mock_tools_service, mock_llm_service, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test message handling when no primary system is configured."""
        # Mock config with no primary system
        mock_config = Mock()
        mock_config.get_primary_system.return_value = None
        mock_config.llm = Mock()
        mock_config.external_systems = []
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
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
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.OAuth2Service')
    @patch('limp.api.im.LLMService')
    @patch('limp.api.im.ToolsService')
    @pytest.mark.asyncio
    async def test_handle_user_message_valid_token(self, mock_tools_service, mock_llm_service, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test message handling when user has valid token."""
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
    @pytest.mark.asyncio
    async def test_handle_user_message_no_token(self, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test message handling when user has no token."""
        # Mock config with primary system
        mock_primary_system = Mock()
        mock_primary_system.name = "test-system"
        mock_config = Mock()
        mock_config.get_primary_system.return_value = mock_primary_system
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
        mock_oauth2_instance.generate_auth_url.assert_called_once_with(1, mock_primary_system)
        
        # Verify IM service calls
        self.mock_im_service.get_user_dm_channel.assert_called_once_with("U123456")
        self.mock_im_service.create_authorization_button.assert_called_once()
        self.mock_im_service.send_message.assert_called_once()
        
        # Verify no reply to original message
        self.mock_im_service.reply_to_message.assert_not_called()
    
    @patch('limp.api.im.get_config')
    @patch('limp.api.im.get_or_create_user')
    @patch('limp.api.im.OAuth2Service')
    @pytest.mark.asyncio
    async def test_handle_user_message_invalid_token(self, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test message handling when user has invalid token."""
        # Mock config with primary system
        mock_primary_system = Mock()
        mock_primary_system.name = "test-system"
        mock_config = Mock()
        mock_config.get_primary_system.return_value = mock_primary_system
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
        mock_oauth2_instance.generate_auth_url.assert_called_once_with(1, mock_primary_system)
        
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
    
    def test_slack_create_authorization_button(self):
        """Test Slack authorization button creation."""
        slack_service = SlackService(
            client_id="test_client_id",
            client_secret="test_client_secret",
            signing_secret="test_signing_secret"
        )
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = slack_service.create_authorization_button(auth_url, button_text, button_description)
        
        assert isinstance(result, list)
        assert len(result) == 2  # Section + Actions
        
        # Check section block
        section_block = result[0]
        assert section_block["type"] == "section"
        assert section_block["text"]["type"] == "mrkdwn"
        assert section_block["text"]["text"] == button_description
        
        # Check actions block
        actions_block = result[1]
        assert actions_block["type"] == "actions"
        assert len(actions_block["elements"]) == 1
        
        button = actions_block["elements"][0]
        assert button["type"] == "button"
        assert button["text"]["text"] == button_text
        assert button["url"] == auth_url
        assert button["action_id"] == "authorization_button"
        assert button["style"] == "primary"
    
    def test_teams_create_authorization_button(self):
        """Test Teams authorization button creation."""
        teams_service = TeamsService(
            app_id="test_app_id",
            client_id="test_client_id",
            client_secret="test_client_secret"
        )
        
        auth_url = "https://example.com/oauth/authorize"
        button_text = "Authorize System"
        button_description = "Click to authorize access"
        
        result = teams_service.create_authorization_button(auth_url, button_text, button_description)
        
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
        assert body["text"] == button_description
        
        # Check actions
        action = card["content"]["actions"][0]
        assert action["type"] == "Action.OpenUrl"
        assert action["title"] == button_text
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
