"""
Tests for iterative tool calling workflow.
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from sqlalchemy.orm import Session

from limp.api.im import process_llm_workflow
from limp.models.user import User
from limp.services.oauth2 import OAuth2Service
from limp.services.llm import LLMService
from limp.services.tools import ToolsService
from limp.config import LLMConfig


class TestIterativeWorkflow:
    """Test suite for iterative tool calling workflow."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.user = User(id=1, external_id="test-user", platform="slack")
        self.db = Mock(spec=Session)
        self.oauth2_service = Mock(spec=OAuth2Service)
        self.tools_service = Mock(spec=ToolsService)
        self.bot_url = "http://localhost:8000"
        
        # Mock config with max_iterations = 3 for testing
        self.config = Mock()
        self.config.llm.max_iterations = 3
        self.config.external_systems = []
        self.config.bot.system_prompts = ["You are a helpful assistant."]
        
        # Mock external system config
        self.mock_system_config = {
            "name": "test-system",
            "oauth2": {
                "client_id": "test-client-id",
                "client_secret": "test-client-secret",
                "authorization_url": "https://example.com/oauth/authorize",
                "token_url": "https://example.com/oauth/token"
            },
            "openapi_spec": "https://example.com/api/openapi.json",
            "base_url": "https://example.com/api"
        }
        
        # Mock LLM service
        self.llm_service = Mock(spec=LLMService)
        
        # Mock tools service methods
        self.tools_service.get_cleaned_tools_for_openai.return_value = []
        self.tools_service.get_system_name_for_tool.return_value = "test-system"
        self.tools_service.execute_tool_call.return_value = {"success": True, "result": "test result"}
        
        # Mock OAuth2 service
        self.oauth2_service.get_valid_token.return_value = Mock(access_token="test-token")
        
        # Mock IM service
        self.mock_im_service = Mock()
        self.mock_im_service.acknowledge_message.return_value = True
        self.mock_im_service.complete_message.return_value = True
        self.mock_im_service.send_temporary_message.return_value = "temp_msg_123"
        self.mock_im_service.cleanup_temporary_messages.return_value = True
    
    @pytest.mark.asyncio
    @patch('limp.api.im.get_config')
    async def test_no_tool_calls_returns_immediately(self, mock_get_config):
        """Test that workflow returns immediately when no tool calls are made."""
        mock_get_config.return_value = self.config
        
        # Mock LLM response without tool calls
        self.llm_service.chat_completion.return_value = {
            "content": "Hello, how can I help you?",
            "tool_calls": None
        }
        self.llm_service.is_tool_call_response.return_value = False
        
        result = await process_llm_workflow(
            "Hello",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "Hello, how can I help you?"
        self.llm_service.chat_completion.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_single_tool_call_iteration(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test workflow with a single tool call iteration."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call response
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # First call: tool call, second call: final response
        self.llm_service.chat_completion.side_effect = [
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": "Based on the tool result, here's the answer.",
                "tool_calls": None
            }
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        result = await process_llm_workflow(
            "Please get some data",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "Based on the tool result, here's the answer."
        assert self.llm_service.chat_completion.call_count == 2
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_multiple_tool_call_iterations(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test workflow with multiple tool call iterations."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # First two calls: tool calls, third call: final response
        self.llm_service.chat_completion.side_effect = [
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": "Based on all the tool results, here's the comprehensive answer.",
                "tool_calls": None
            }
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        result = await process_llm_workflow(
            "Please analyze some data",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "Based on all the tool results, here's the comprehensive answer."
        assert self.llm_service.chat_completion.call_count == 3
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_max_iterations_exceeded(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test workflow when max iterations are exceeded."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # All calls return tool calls (exceeding max iterations)
        self.llm_service.chat_completion.side_effect = [
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": "I've reached the iteration limit, but here's what I found so far.",
                "tool_calls": None
            }
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, True, True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        result = await process_llm_workflow(
            "Please do extensive analysis",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "I've reached the iteration limit, but here's what I found so far."
        assert self.llm_service.chat_completion.call_count == 4  # 3 iterations + 1 final call
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_authorization_required_during_iteration(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test that authorization requirement stops the iteration and returns auth URL."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # First call: tool call
        self.llm_service.chat_completion.return_value = {
            "content": None,
            "tool_calls": [mock_tool_call]
        }
        
        self.llm_service.is_tool_call_response.return_value = True
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        # Mock no valid token (authorization required)
        self.oauth2_service.get_valid_token.return_value = None
        self.oauth2_service.generate_auth_url.return_value = "http://localhost:8000/auth"
        
        result = await process_llm_workflow(
            "Please get some data",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert "Please authorize access to test-system" in result["content"]
        assert "http://localhost:8000/auth" in result["content"]
        assert result["metadata"]["auth_url"] == "http://localhost:8000/auth"
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_tool_call_failure_handling(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test handling of tool call failures during iteration."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # First call: tool call, second call: final response
        self.llm_service.chat_completion.side_effect = [
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": "I encountered an error, but here's what I can tell you.",
                "tool_calls": None
            }
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        # Mock tool call failure
        self.tools_service.execute_tool_call.return_value = {
            "success": False,
            "error": "API endpoint not found",
            "status_code": 404
        }
        
        result = await process_llm_workflow(
            "Please get some data",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "I encountered an error, but here's what I can tell you."
        assert self.llm_service.chat_completion.call_count == 2
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_conversation_history_preserved(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test that conversation history is preserved through iterations."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        conversation_history = [
            {"role": "user", "content": "Previous question"},
            {"role": "assistant", "content": "Previous answer"}
        ]
        
        # First call: tool call, second call: final response
        self.llm_service.chat_completion.side_effect = [
            {
                "content": None,
                "tool_calls": [mock_tool_call]
            },
            {
                "content": "Based on the context and tool result, here's the answer.",
                "tool_calls": None
            }
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        result = await process_llm_workflow(
            "Current question",
            conversation_history,
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        # Verify that format_messages_with_context was called with the conversation history
        # Note: user_message is empty since it's already in conversation_history
        self.llm_service.format_messages_with_context.assert_called_once_with(
            "",
            conversation_history,
            ["You are a helpful assistant."]
        )
        
        # Verify that the conversation history contains the user message
        # The user message should be in the conversation history since it was stored in the database
        user_messages = [msg for msg in conversation_history if msg.get("role") == "user"]
        assert len(user_messages) >= 1  # Should have at least one user message
        
        assert result["content"] == "Based on the context and tool result, here's the answer."
    
    @pytest.mark.asyncio
    @patch('limp.api.im.get_config')
    async def test_error_handling_in_workflow(self, mock_get_config):
        """Test error handling in the workflow."""
        mock_get_config.return_value = self.config
        
        # Mock LLM service to raise an exception
        self.llm_service.chat_completion.side_effect = Exception("LLM service error")
        self.llm_service.get_error_message.return_value = "There was an issue with the AI service."
        
        result = await process_llm_workflow(
            "Hello",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "There was an issue with the AI service."
        assert result["metadata"]["error"] is True
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_custom_max_iterations_from_config(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test that custom max_iterations from config is respected."""
        # Set custom max_iterations
        self.config.llm.max_iterations = 5
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # All calls return tool calls (exceeding max iterations of 5)
        self.llm_service.chat_completion.side_effect = [
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": "Final response after 5 iterations.", "tool_calls": None}
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, True, True, True, True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        result = await process_llm_workflow(
            "Please do extensive analysis",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        assert result["content"] == "Final response after 5 iterations."
        assert self.llm_service.chat_completion.call_count == 6  # 5 iterations + 1 final call
    
    @pytest.mark.asyncio
    @patch('limp.services.context.ContextManager')
    @patch('limp.api.im.get_system_config')
    @patch('limp.api.im.get_config')
    async def test_final_prompt_sent_when_max_iterations_exceeded(self, mock_get_config, mock_get_system_config, mock_context_manager):
        """Test that final prompt is sent when max iterations are exceeded."""
        mock_get_config.return_value = self.config
        mock_get_system_config.return_value = self.mock_system_config
        
        # Mock ContextManager
        mock_context_instance = Mock()
        mock_context_instance.append_context_usage_to_message.return_value = "1. Talking to Test System. Processing request. 25% context"
        mock_context_manager.return_value = mock_context_instance
        
        # Mock tool call
        mock_tool_call = Mock()
        mock_tool_call.id = "call_123"
        mock_tool_call.type = "function"
        mock_tool_call.function.name = "test_function"
        mock_tool_call.function.arguments = '{"arg": "value"}'
        
        # All calls return tool calls (exceeding max iterations)
        self.llm_service.chat_completion.side_effect = [
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": None, "tool_calls": [mock_tool_call]},
            {"content": "I've reached the maximum number of tool calling iterations. Here's my best response.", "tool_calls": None}
        ]
        
        self.llm_service.is_tool_call_response.side_effect = [True, True, True, False]
        self.llm_service.extract_tool_calls.return_value = [{
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "test_function",
                "arguments": '{"arg": "value"}'
            }
        }]
        
        result = await process_llm_workflow(
            "Please do extensive analysis",
            [],
            self.user,
            self.oauth2_service,
            self.llm_service,
            self.tools_service,
            self.db,
            self.bot_url,
            self.mock_im_service,
            "test-channel",
            "1234567890.123456"
        )
        
        # Verify that the final call was made without tools
        final_call = self.llm_service.chat_completion.call_args_list[-1]
        # The final call should not have tools parameter or it should be None
        assert "tools" not in final_call[1] or final_call[1]["tools"] is None
        
        assert result["content"] == "I've reached the maximum number of tool calling iterations. Here's my best response."
        assert self.llm_service.chat_completion.call_count == 4  # 3 iterations + 1 final call
