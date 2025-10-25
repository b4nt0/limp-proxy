"""
Test LLM service JSON serialization to prevent OpenAI API errors.
"""

import pytest
from datetime import datetime
from unittest.mock import Mock, patch

from limp.services.llm import LLMService
from limp.config import LLMConfig


class TestLLMJSONSerialization:
    """Test that LLM service properly handles JSON serialization."""
    
    def test_chat_completion_with_datetime_fails(self):
        """Test that chat completion fails when datetime objects are present."""
        config = LLMConfig(
            api_key="test-key",
            model="gpt-4",
            base_url="https://api.openai.com/v1"
        )
        llm_service = LLMService(config)
        
        # Create messages with datetime objects (this should fail)
        messages = [
            {"role": "user", "content": "Hello", "created_at": datetime.now()},
            {"role": "assistant", "content": "Hi there", "created_at": datetime.now()}
        ]
        
        with patch.object(llm_service, 'client') as mock_client:
            # The validation should catch this before making the API call
            with pytest.raises(ValueError, match="Data is not JSON serializable"):
                llm_service.chat_completion(messages)
    
    def test_chat_completion_with_clean_messages_succeeds(self):
        """Test that chat completion works with clean messages."""
        config = LLMConfig(
            api_key="test-key",
            model="gpt-4",
            base_url="https://api.openai.com/v1"
        )
        llm_service = LLMService(config)
        
        # Create clean messages without datetime objects
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        
        with patch.object(llm_service, 'client') as mock_client:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message = Mock()
            mock_response.choices[0].message.content = "Test response"
            mock_response.choices[0].message.tool_calls = None
            mock_response.choices[0].finish_reason = "stop"
            mock_response.usage = Mock()
            mock_response.usage.prompt_tokens = 10
            mock_response.usage.completion_tokens = 5
            mock_response.usage.total_tokens = 15
            
            mock_client.chat.completions.create.return_value = mock_response
            
            # This should succeed
            result = llm_service.chat_completion(messages)
            assert result["content"] == "Test response"
    
    def test_stream_chat_completion_with_datetime_fails(self):
        """Test that stream chat completion fails when datetime objects are present."""
        config = LLMConfig(
            api_key="test-key",
            model="gpt-4",
            base_url="https://api.openai.com/v1"
        )
        llm_service = LLMService(config)
        
        # Create messages with datetime objects (this should fail)
        messages = [
            {"role": "user", "content": "Hello", "created_at": datetime.now()},
            {"role": "assistant", "content": "Hi there", "created_at": datetime.now()}
        ]
        
        with patch.object(llm_service, 'client') as mock_client:
            # The validation should catch this before making the API call
            with pytest.raises(ValueError, match="Data is not JSON serializable"):
                llm_service.stream_chat_completion(messages)
    
    def test_validate_json_serializable_method(self):
        """Test the JSON serialization validation method directly."""
        config = LLMConfig(
            api_key="test-key",
            model="gpt-4",
            base_url="https://api.openai.com/v1"
        )
        llm_service = LLMService(config)
        
        # Test with serializable data
        llm_service._validate_json_serializable({"key": "value"}, "test")
        
        # Test with non-serializable data
        with pytest.raises(ValueError, match="Data is not JSON serializable"):
            llm_service._validate_json_serializable({"key": datetime.now()}, "test")
    
    def test_conversation_history_without_datetime(self):
        """Test that conversation history from context manager doesn't include datetime."""
        from limp.services.context import ContextManager
        from limp.config import LLMConfig
        
        # Create a mock context manager
        llm_config = LLMConfig(
            api_key="test-key",
            model="gpt-4",
            base_url="https://api.openai.com/v1"
        )
        context_manager = ContextManager(llm_config)
        
        # Create mock messages with datetime
        mock_messages = [
            Mock(role="user", content="Hello", created_at=datetime.now()),
            Mock(role="assistant", content="Hi there", created_at=datetime.now())
        ]
        
        # Test the formatting method
        formatted = context_manager._format_messages_for_llm(mock_messages)
        
        # Verify that datetime fields are not included
        for message in formatted:
            assert "created_at" not in message
            assert "role" in message
            assert "content" in message
        
        # Verify the formatted messages are JSON serializable
        import json
        json.dumps(formatted)  # This should not raise an exception
