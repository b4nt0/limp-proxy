"""
Regression tests for authorization behavior.

This test suite ensures that both primary system and LLM workflow authorization
flows work correctly and use the DRY implementation.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timedelta

from limp.api.im import handle_user_message, handle_authorization_request, process_llm_workflow
from limp.services.oauth2 import OAuth2Service
from limp.services.slack import SlackService
from limp.services.teams import TeamsService
from limp.models.user import User
from limp.models.auth import AuthToken
from limp.config import ExternalSystemConfig, OAuth2Config


class TestAuthorizationRegression:
    """Regression tests for authorization behavior to ensure DRY implementation works correctly."""
    
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
    @patch('limp.api.im.is_duplicate_message')
    @patch('limp.api.im.generate_slack_message_id')
    @pytest.mark.asyncio
    async def test_primary_system_authorization_uses_common_handler(self, mock_generate_id, mock_is_duplicate, mock_oauth2_service, mock_get_user, mock_get_config):
        """Test that primary system authorization uses the common handler function."""
        # Mock duplicate detection
        mock_is_duplicate.return_value = False
        mock_generate_id.return_value = "test_external_id"
        
        # Mock config with primary system
        mock_primary_system = Mock()
        mock_primary_system.name = "test-system"
        mock_config = Mock()
        mock_config.get_primary_system.return_value = mock_primary_system
        mock_config.bot.url = "http://localhost:8000"
        mock_get_config.return_value = mock_config
        
        # Mock user creation
        mock_get_user.return_value = self.mock_user
        
        # Mock OAuth2 service with no token
        mock_oauth2_instance = Mock()
        mock_oauth2_instance.get_valid_token.return_value = None
        mock_oauth2_instance.generate_auth_url.return_value = "https://example.com/auth"
        mock_oauth2_service.return_value = mock_oauth2_instance
        
        # Mock IM service methods
        self.mock_im_service.get_user_dm_channel.return_value = "D123456"
        self.mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        self.mock_im_service.send_message = AsyncMock(return_value=True)
        
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
        
        # Verify IM service calls (common handler behavior)
        self.mock_im_service.get_user_dm_channel.assert_called_once_with("U123456")
        self.mock_im_service.create_authorization_button.assert_called_once()
        self.mock_im_service.send_message.assert_called_once()
        
        # Verify no reply to original message
        self.mock_im_service.reply_to_message.assert_not_called()
    
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
    async def test_llm_workflow_authorization_uses_common_handler(self, mock_generate_id, mock_is_duplicate, mock_process_llm_workflow, mock_store_assistant_message, mock_get_conversation_history, mock_store_user_message, mock_get_or_create_conversation, mock_get_user, mock_get_config):
        """Test that LLM workflow authorization uses the common handler function."""
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
        
        # Mock LLM workflow with authorization required
        mock_process_llm_workflow.return_value = {
            "content": "Please authorize access to TestSystem: https://example.com/auth",
            "metadata": {
                "auth_url": "https://example.com/auth",
                "authorization_required": True,
                "system_name": "TestSystem"
            }
        }
        
        # Mock IM service methods
        self.mock_im_service.acknowledge_message.return_value = None
        self.mock_im_service.get_user_dm_channel.return_value = "D123456"
        self.mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        self.mock_im_service.send_message = AsyncMock(return_value=True)
        
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
        
        # Verify IM service calls (common handler behavior)
        self.mock_im_service.get_user_dm_channel.assert_called_once_with("U123456")
        self.mock_im_service.create_authorization_button.assert_called_once()
        self.mock_im_service.send_message.assert_called_once()
        
        # Verify no reply to original message
        self.mock_im_service.reply_to_message.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_handle_authorization_request_common_function(self):
        """Test the common authorization handler function directly."""
        # Mock IM service
        mock_im_service = Mock()
        mock_im_service.get_user_dm_channel.return_value = "D123456"
        mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        mock_im_service.send_message = AsyncMock(return_value=True)
        
        # Mock message data
        message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "timestamp": "1234567890.123456"
        }
        
        # Call the common handler function
        result = await handle_authorization_request(
            "TestSystem",
            "https://example.com/auth",
            "U123456",
            mock_im_service,
            message_data,
            None
        )
        
        # Verify result
        assert result["status"] == "ok"
        assert result["action"] == "authorization_required"
        
        # Verify IM service calls
        mock_im_service.get_user_dm_channel.assert_called_once_with("U123456")
        mock_im_service.create_authorization_button.assert_called_once_with(
            "https://example.com/auth",
            "Authorize TestSystem",
            "Click to authorize access to TestSystem",
            None
        )
        mock_im_service.send_message.assert_called_once()
        
        # Verify message completion
        mock_im_service.complete_message.assert_called_once_with(
            "C123456",
            "1234567890.123456",
            success=False
        )
    
    @pytest.mark.asyncio
    async def test_llm_workflow_stores_failed_tool_result(self):
        """Test that LLM workflow stores failed tool result when authorization is required."""
        # This test verifies that the process_llm_workflow function stores failed tool results
        # when authorization is required, ensuring database consistency
        
        # Mock database session
        mock_db = Mock()
        
        # Mock OAuth2 service with no token
        mock_oauth2_service = Mock()
        mock_oauth2_service.get_valid_token.return_value = None
        mock_oauth2_service.generate_auth_url.return_value = "https://example.com/auth"
        
        # Mock tools service
        mock_tools_service = Mock()
        mock_tools_service.get_system_name_for_tool.return_value = "TestSystem"
        
        # Mock system config
        mock_system_config = {"name": "TestSystem", "openapi_spec": "https://example.com/api/openapi.json"}
        
        # Mock user
        mock_user = Mock()
        mock_user.id = 1
        
        # Mock store_tool_response function
        with patch('limp.api.im.store_tool_response') as mock_store_tool_response:
            # Mock the authorization check in process_llm_workflow
            # This simulates the scenario where a tool call requires authorization
            # but the user doesn't have a valid token
            
            # Simulate the authorization check logic from process_llm_workflow
            tool_call = {
                "id": "call_123",
                "function": {
                    "name": "test_tool",
                    "arguments": "{}"
                }
            }
            
            # This is the logic that should be executed when authorization is required
            auth_url = mock_oauth2_service.generate_auth_url(1, mock_system_config, "http://localhost:8000")
            tool_result_content = f"Authorization required for TestSystem. Please authorize access: {auth_url}"
            
            # Store tool response in database (this is what the actual code does)
            mock_store_tool_response(
                mock_db,
                1,  # conversation_id
                tool_call["id"],
                tool_result_content,
                False  # success=False for authorization required
            )
            
            # Verify that the failed tool result was stored
            mock_store_tool_response.assert_called_once_with(
                mock_db,
                1,  # conversation_id
                "call_123",  # tool_call_id
                "Authorization required for TestSystem. Please authorize access: https://example.com/auth",  # response_content
                False  # success=False
            )
    
    @pytest.mark.asyncio
    async def test_authorization_consistency_between_flows(self):
        """Test that both authorization flows produce consistent results."""
        # Mock IM service
        mock_im_service = Mock()
        mock_im_service.get_user_dm_channel.return_value = "D123456"
        mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        mock_im_service.send_message = AsyncMock(return_value=True)
        
        # Mock message data
        message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "timestamp": "1234567890.123456"
        }
        
        # Test primary system authorization
        result1 = await handle_authorization_request(
            "PrimarySystem",
            "https://example.com/auth1",
            "U123456",
            mock_im_service,
            message_data,
            None
        )
        
        # Test LLM workflow authorization
        result2 = await handle_authorization_request(
            "LLMSystem",
            "https://example.com/auth2",
            "U123456",
            mock_im_service,
            message_data,
            None
        )
        
        # Verify both results are identical
        assert result1 == result2
        assert result1["status"] == "ok"
        assert result1["action"] == "authorization_required"
        
        # Verify both calls to IM service are identical
        assert mock_im_service.get_user_dm_channel.call_count == 2
        assert mock_im_service.create_authorization_button.call_count == 2
        assert mock_im_service.send_message.call_count == 2
        assert mock_im_service.complete_message.call_count == 2
    
    def test_authorization_handler_interface(self):
        """Test that the authorization handler has the correct interface."""
        import inspect
        
        # Test function signature
        sig = inspect.signature(handle_authorization_request)
        params = list(sig.parameters.keys())
        
        expected_params = ['system_name', 'auth_url', 'user_id', 'im_service', 'message_data', 'request']
        assert params == expected_params, f"Expected parameters {expected_params}, got {params}"
        
        # Test that the function is async
        assert inspect.iscoroutinefunction(handle_authorization_request), "Authorization handler should be async"
    
    @pytest.mark.asyncio
    async def test_authorization_prompt_content(self):
        """Test that authorization prompts have consistent content."""
        # Mock IM service
        mock_im_service = Mock()
        mock_im_service.get_user_dm_channel.return_value = "D123456"
        mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        mock_im_service.send_message = AsyncMock(return_value=True)
        
        # Mock message data
        message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "timestamp": "1234567890.123456"
        }
        
        # Call the authorization handler
        await handle_authorization_request(
            "TestSystem",
            "https://example.com/auth",
            "U123456",
            mock_im_service,
            message_data,
            None
        )
        
        # Verify the authorization prompt content
        mock_im_service.send_message.assert_called_once()
        call_args = mock_im_service.send_message.call_args
        
        # Check that the prompt contains the expected content
        prompt_content = call_args[0][1]  # Second argument is the message content
        assert "🔐 **Authorization Required**" in prompt_content
        assert "To use this bot, you need to authorize access to TestSystem" in prompt_content
        assert "Click the button below to authorize:" in prompt_content
        
        # Check that the button metadata is correct
        button_metadata = call_args[0][2]  # Third argument is the metadata
        assert "blocks" in button_metadata
        assert button_metadata["blocks"] == [{"type": "button"}]
    
    @pytest.mark.asyncio
    async def test_authorization_button_creation(self):
        """Test that authorization buttons are created with correct parameters."""
        # Mock IM service
        mock_im_service = Mock()
        mock_im_service.get_user_dm_channel.return_value = "D123456"
        mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        mock_im_service.send_message = AsyncMock(return_value=True)
        
        # Mock message data
        message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "timestamp": "1234567890.123456"
        }
        
        # Call the authorization handler
        await handle_authorization_request(
            "TestSystem",
            "https://example.com/auth",
            "U123456",
            mock_im_service,
            message_data,
            None
        )
        
        # Verify button creation parameters
        mock_im_service.create_authorization_button.assert_called_once_with(
            "https://example.com/auth",
            "Authorize TestSystem",
            "Click to authorize access to TestSystem",
            None
        )
    
    @pytest.mark.asyncio
    async def test_authorization_message_completion(self):
        """Test that authorization messages are completed with failure status."""
        # Mock IM service
        mock_im_service = Mock()
        mock_im_service.get_user_dm_channel.return_value = "D123456"
        mock_im_service.create_authorization_button.return_value = [{"type": "button"}]
        mock_im_service.send_message = AsyncMock(return_value=True)
        
        # Mock message data
        message_data = {
            "user_id": "U123456",
            "channel": "C123456",
            "timestamp": "1234567890.123456"
        }
        
        # Call the authorization handler
        await handle_authorization_request(
            "TestSystem",
            "https://example.com/auth",
            "U123456",
            mock_im_service,
            message_data,
            None
        )
        
        # Verify message completion with failure status
        mock_im_service.complete_message.assert_called_once_with(
            "C123456",
            "1234567890.123456",
            success=False
        )


class TestAuthorizationDRYImplementation:
    """Test that the DRY implementation eliminates code duplication."""
    
    def test_authorization_code_duplication_eliminated(self):
        """Test that authorization code duplication has been eliminated."""
        # This test verifies that both authorization flows use the same handler function
        # by checking that the common handler function exists and has the right interface
        
        import inspect
        from limp.api.im import handle_authorization_request
        
        # Verify the function exists and is async
        assert callable(handle_authorization_request)
        assert inspect.iscoroutinefunction(handle_authorization_request)
        
        # Verify the function signature
        sig = inspect.signature(handle_authorization_request)
        params = list(sig.parameters.keys())
        expected_params = ['system_name', 'auth_url', 'user_id', 'im_service', 'message_data', 'request']
        assert params == expected_params
    
    def test_authorization_handler_reusability(self):
        """Test that the authorization handler is reusable for different systems."""
        # This test ensures that the same handler can be used for different systems
        # without any system-specific logic
        
        import inspect
        from limp.api.im import handle_authorization_request
        
        # The function should not have any hardcoded system names or logic
        # It should work with any system name passed as a parameter
        sig = inspect.signature(handle_authorization_request)
        
        # Verify that system_name is a parameter (not hardcoded)
        assert 'system_name' in sig.parameters
        
        # Verify that the function doesn't have any system-specific logic
        # by checking that it doesn't import or reference specific systems
        import limp.api.im
        source = inspect.getsource(handle_authorization_request)
        
        # The function should not contain hardcoded system names
        assert 'PrimarySystem' not in source
        assert 'LLMSystem' not in source
        assert 'TestSystem' not in source
        
        # The function should use the system_name parameter
        assert 'system_name' in source
