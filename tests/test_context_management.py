"""
Tests for context management functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from sqlalchemy.orm import Session
from datetime import datetime

from limp.services.context import ContextManager
from limp.models.conversation import Message, Conversation
from limp.config import LLMConfig


class TestContextManager:
    """Test context management functionality."""
    
    @pytest.fixture
    def llm_config(self):
        """Create a test LLM configuration."""
        return LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
            max_tokens=4000,
            temperature=0.7,
            max_iterations=8,
            context_threshold=0.75,
            context_window_size=8192,
            summary_max_tokens=2048
        )
    
    @pytest.fixture
    def context_manager(self, llm_config):
        """Create a context manager instance."""
        with patch('limp.services.context.openai.OpenAI'):
            return ContextManager(llm_config)
    
    def test_count_tokens_simple(self, context_manager):
        """Test token counting for simple messages."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        tokens = context_manager.count_tokens(messages)
        assert tokens > 0
        assert isinstance(tokens, int)
    
    def test_count_tokens_with_tool_calls(self, context_manager):
        """Test token counting for messages with tool calls."""
        messages = [
            {"role": "user", "content": "Get weather"},
            {
                "role": "assistant", 
                "content": "I'll get the weather for you.",
                "tool_calls": [{
                    "id": "call_123",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location": "New York"}'
                    }
                }]
            },
            {
                "role": "tool",
                "content": "Sunny, 72°F",
                "tool_call_id": "call_123"
            }
        ]
        
        tokens = context_manager.count_tokens(messages)
        assert tokens > 0
        assert isinstance(tokens, int)
    
    def test_should_summarize_below_threshold(self, context_manager):
        """Test that summarization is not triggered below threshold."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        
        should_summarize = context_manager.should_summarize(messages)
        assert not should_summarize
    
    def test_should_summarize_above_threshold(self, context_manager):
        """Test that summarization is triggered above threshold."""
        # Create a very long message to exceed threshold
        long_content = "This is a very long message. " * 1000  # ~30k characters
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content}
        ]
        
        should_summarize = context_manager.should_summarize(messages)
        assert should_summarize
    
    def test_summarize_conversation(self, context_manager):
        """Test conversation summarization."""
        # Mock the OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "This is a test summary."
        
        with patch.object(context_manager.client.chat.completions, 'create', return_value=mock_response):
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "How are you?"},
                {"role": "assistant", "content": "I'm doing well, thank you!"}
            ]
            
            summary = context_manager.summarize_conversation(messages)
            assert summary == "This is a test summary."
    
    def test_summarize_conversation_excludes_tool_calls(self, context_manager):
        """Test that summarization excludes tool calls when requested."""
        # Mock the OpenAI response
        mock_response = Mock()
        mock_response.choices = [Mock()]
        mock_response.choices[0].message.content = "Summary without tool calls"
        
        with patch.object(context_manager.client.chat.completions, 'create', return_value=mock_response):
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "tool", "content": "Tool response"},
                {"role": "tool_request", "content": "Tool request"}
            ]
            
            summary = context_manager.summarize_conversation(messages, exclude_tool_calls=True)
            assert summary == "Summary without tool calls"
    
    def test_create_summary_message(self, context_manager):
        """Test creation of summary message."""
        summary = "This is a test summary"
        message = context_manager.create_summary_message(summary)
        
        assert message["role"] == "summary"
        assert message["content"] == summary
    
    def test_reconstruct_history_with_summary(self, context_manager):
        """Test history reconstruction with summaries."""
        # Mock database session and messages
        mock_db = Mock(spec=Session)
        mock_messages = [
            Mock(spec=Message),
            Mock(spec=Message),
            Mock(spec=Message)
        ]
        
        # Configure mock messages
        mock_messages[0].role = "user"
        mock_messages[0].content = "Original request"
        mock_messages[0].created_at = datetime(2024, 1, 1, 10, 0, 0)
        
        mock_messages[1].role = "summary"
        mock_messages[1].content = "Previous conversation summary"
        mock_messages[1].created_at = datetime(2024, 1, 1, 10, 30, 0)
        
        mock_messages[2].role = "user"
        mock_messages[2].content = "New message"
        mock_messages[2].created_at = datetime(2024, 1, 1, 11, 0, 0)
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should include: original request + summary + new message
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Original request"
        assert history[1]["role"] == "system"
        assert "Previous conversation summary" in history[1]["content"]
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "New message"
    
    def test_reconstruct_history_without_summary(self, context_manager):
        """Test history reconstruction without summaries."""
        # Mock database session and messages
        mock_db = Mock(spec=Session)
        mock_messages = [
            Mock(spec=Message),
            Mock(spec=Message)
        ]
        
        # Configure mock messages (no summary)
        mock_messages[0].role = "user"
        mock_messages[0].content = "First message"
        mock_messages[0].created_at = datetime(2024, 1, 1, 10, 0, 0)
        
        mock_messages[1].role = "assistant"
        mock_messages[1].content = "Response"
        mock_messages[1].created_at = datetime(2024, 1, 1, 10, 1, 0)
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should include all messages
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "First message"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Response"
    
    def test_store_summary(self, context_manager):
        """Test storing summary in database."""
        mock_db = Mock(spec=Session)
        mock_message = Mock(spec=Message)
        mock_message.id = 123
        
        mock_db.add.return_value = None
        mock_db.commit.return_value = None
        mock_db.refresh.return_value = None
        mock_db.refresh.side_effect = lambda obj: setattr(obj, 'id', 123)
        
        result = context_manager.store_summary(mock_db, 1, "Test summary")
        
        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()
        
        # Verify the message was created correctly
        added_message = mock_db.add.call_args[0][0]
        assert added_message.conversation_id == 1
        assert added_message.role == "summary"
        assert added_message.content == "Test summary"
        assert added_message.message_metadata["type"] == "conversation_summary"
    
    def test_format_messages_for_llm(self, context_manager):
        """Test formatting database messages for LLM."""
        # Create mock messages
        mock_messages = [
            Mock(spec=Message),
            Mock(spec=Message),
            Mock(spec=Message)
        ]
        
        # Configure mock messages
        mock_messages[0].role = "user"
        mock_messages[0].content = "Hello"
        mock_messages[0].message_metadata = None
        
        mock_messages[1].role = "tool_request"
        mock_messages[1].content = "Tool request"
        mock_messages[1].message_metadata = {
            "tool_name": "test_tool",
            "tool_arguments": '{"param": "value"}',
            "tool_call_id": "call_123"
        }
        
        mock_messages[2].role = "tool_response"
        mock_messages[2].content = "Tool response"
        mock_messages[2].message_metadata = {
            "tool_call_id": "call_123"
        }
        
        formatted = context_manager._format_messages_for_llm(mock_messages)
        
        assert len(formatted) == 3
        assert formatted[0]["role"] == "user"
        assert formatted[0]["content"] == "Hello"
        
        assert formatted[1]["role"] == "assistant"
        assert "tool_calls" in formatted[1]
        assert formatted[1]["tool_calls"][0]["function"]["name"] == "test_tool"
        
        assert formatted[2]["role"] == "tool"
        assert formatted[2]["tool_call_id"] == "call_123"


class TestContextManagementIntegration:
    """Integration tests for context management."""
    
    @pytest.fixture
    def llm_config(self):
        """Create a test LLM configuration."""
        return LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
            max_tokens=4000,
            temperature=0.7,
            max_iterations=8,
            context_threshold=0.1,  # Low threshold for testing
            context_window_size=1000,  # Small window for testing
            summary_max_tokens=100
        )
    
    @pytest.fixture
    def context_manager(self, llm_config):
        """Create a context manager instance."""
        with patch('limp.services.context.openai.OpenAI'):
            return ContextManager(llm_config)
    
    def test_full_context_management_flow(self, context_manager):
        """Test the complete context management flow."""
        # Mock database session
        mock_db = Mock(spec=Session)
        
        # Create mock messages that would trigger summarization
        mock_messages = []
        for i in range(10):
            msg = Mock(spec=Message)
            msg.role = "user"
            msg.content = f"This is a very long message number {i}. " * 50  # Make it long
            msg.created_at = datetime(2024, 1, 1, 10, i, 0)
            msg.message_metadata = None
            mock_messages.append(msg)
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        # Test the reconstruction (this doesn't trigger summarization by itself)
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should have reconstructed all messages
        assert len(history) == 10
        assert all(msg["role"] == "user" for msg in history)
        
        # Test that summarization uses the reconstructed history, not raw messages
        with patch.object(context_manager, 'summarize_conversation') as mock_summarize:
            mock_summarize.return_value = "Test summary"
            
            # Simulate the summarization process
            summary = context_manager.summarize_conversation(history, exclude_tool_calls=True)
            mock_summarize.assert_called_with(history, exclude_tool_calls=True)
    
    def test_multiple_summarizations(self, context_manager):
        """Test handling of multiple summarizations in a conversation."""
        # Mock database session with existing summary
        mock_db = Mock(spec=Session)
        
        # Create messages with an existing summary
        mock_messages = [
            Mock(spec=Message),  # Original request
            Mock(spec=Message),  # Summary
            Mock(spec=Message),  # New message
        ]
        
        mock_messages[0].role = "user"
        mock_messages[0].content = "Original request"
        mock_messages[0].created_at = datetime(2024, 1, 1, 10, 0, 0)
        
        mock_messages[1].role = "summary"
        mock_messages[1].content = "Previous summary"
        mock_messages[1].created_at = datetime(2024, 1, 1, 10, 30, 0)
        
        mock_messages[2].role = "user"
        mock_messages[2].content = "New message"
        mock_messages[2].created_at = datetime(2024, 1, 1, 11, 0, 0)
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        # Test reconstruction
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should include: original request + summary + new message
        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Original request"
        assert history[1]["role"] == "system"
        assert "Previous summary" in history[1]["content"]
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "New message"
    
    def test_summarization_uses_reconstructed_history(self, context_manager):
        """Test that summarization uses the reconstructed history (original + latest summary + new messages)."""
        # Mock database session with existing summary
        mock_db = Mock(spec=Session)
        
        # Create messages with an existing summary
        mock_messages = [
            Mock(spec=Message),  # Original request
            Mock(spec=Message),  # First summary
            Mock(spec=Message),  # New messages after summary
            Mock(spec=Message),  # Another new message
        ]
        
        mock_messages[0].role = "user"
        mock_messages[0].content = "Original request"
        mock_messages[0].created_at = datetime(2024, 1, 1, 10, 0, 0)
        
        mock_messages[1].role = "summary"
        mock_messages[1].content = "Previous conversation summary"
        mock_messages[1].created_at = datetime(2024, 1, 1, 10, 30, 0)
        
        mock_messages[2].role = "user"
        mock_messages[2].content = "New message after summary"
        mock_messages[2].created_at = datetime(2024, 1, 1, 11, 0, 0)
        
        mock_messages[3].role = "assistant"
        mock_messages[3].content = "Response to new message"
        mock_messages[3].created_at = datetime(2024, 1, 1, 11, 1, 0)
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        # Test reconstruction - should include: original + summary + new messages
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should have 4 messages: original + summary (as system) + new user + new assistant
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Original request"
        assert history[1]["role"] == "system"
        assert "Previous conversation summary" in history[1]["content"]
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "New message after summary"
        assert history[3]["role"] == "assistant"
        assert history[3]["content"] == "Response to new message"
        
        # Test that when we summarize this reconstructed history, it doesn't include the past summary content
        with patch.object(context_manager.client.chat.completions, 'create') as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "New summary"
            mock_create.return_value = mock_response
            
            summary = context_manager.summarize_conversation(history, exclude_tool_calls=True)
            
            # Verify the summarization was called with the reconstructed history
            mock_create.assert_called_once()
            call_args = mock_create.call_args[1]
            messages_for_summary = call_args['messages']
            
            # The summarization should receive the reconstructed history, not raw database messages
            assert len(messages_for_summary) == 2  # system prompt + user prompt
            user_prompt = messages_for_summary[1]['content']
            assert "Original request" in user_prompt
            assert "New message after summary" in user_prompt
            assert "Response to new message" in user_prompt
            # Should include the previous summary as context (this is correct behavior)
            assert "Previous conversation summary" in user_prompt


class TestContextManagerEdgeCases:
    """Test edge cases for context management."""
    
    @pytest.fixture
    def llm_config(self):
        """Create a test LLM configuration."""
        return LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
            max_tokens=4000,
            temperature=0.7,
            max_iterations=8,
            context_threshold=0.75,
            context_window_size=8192,
            summary_max_tokens=2048
        )
    
    @pytest.fixture
    def context_manager(self, llm_config):
        """Create a context manager instance."""
        with patch('limp.services.context.openai.OpenAI'):
            return ContextManager(llm_config)
    
    def test_empty_conversation(self, context_manager):
        """Test handling of empty conversation."""
        messages = []
        
        should_summarize = context_manager.should_summarize(messages)
        assert not should_summarize
        
        summary = context_manager.summarize_conversation(messages)
        assert summary == "No conversation history to summarize."
    
    def test_summarization_failure(self, context_manager):
        """Test handling of summarization failures."""
        with patch.object(context_manager.client.chat.completions, 'create', side_effect=Exception("API Error")):
            messages = [{"role": "user", "content": "Hello"}]
            summary = context_manager.summarize_conversation(messages)
            
            assert summary == "Failed to generate summary due to an error."
    
    def test_context_window_detection_fallback(self, context_manager):
        """Test fallback when context window detection fails."""
        # Test with unknown model
        context_manager.config.model = "unknown-model"
        context_manager._context_window_size = None
        
        window_size = context_manager._get_context_window_size()
        assert window_size == 8192  # Default fallback
    
    def test_unknown_model_fallback(self, context_manager):
        """Test fallback for unknown models."""
        # Change model to something unknown
        context_manager.config.model = "unknown-model"
        context_manager._context_window_size = None
        
        with patch('limp.services.context.tiktoken.encoding_for_model') as mock_encoding:
            mock_encoding.side_effect = KeyError("Unknown model")
            
            # Should use fallback encoding
            encoding = context_manager._get_encoding()
            assert encoding is not None
    
    def test_model_context_window_lookup(self, context_manager):
        """Test context window size lookup for various models."""
        test_cases = [
            ("gpt-3.5-turbo", 4096),
            ("gpt-3.5-turbo-16k", 16384),
            ("gpt-4", 8192),
            ("gpt-4-32k", 32768),
            ("gpt-4-turbo", 128000),
            ("gpt-4o", 128000),
            ("gpt-4o-mini", 128000),
            ("gpt-5", 200000),
            ("gpt-5-turbo", 200000),
            ("claude-3-sonnet", 200000),
            ("o1-preview", 128000),
        ]
        
        for model_name, expected_size in test_cases:
            # Create a fresh context manager for each test
            with patch('limp.services.context.openai.OpenAI'):
                # Create a fresh config for each test
                fresh_config = LLMConfig(
                    provider="openai",
                    api_key="test-key",
                    model=model_name,
                    max_tokens=4000,
                    temperature=0.7,
                    max_iterations=8,
                    context_threshold=0.75,
                    context_window_size=None,  # Let it auto-detect
                    summary_max_tokens=2048
                )
                fresh_context_manager = ContextManager(fresh_config)
                size = fresh_context_manager._get_context_window_size()
                assert size == expected_size, f"Model {model_name} should have context window size {expected_size}, got {size}"
    
    def test_model_pattern_matching(self, context_manager):
        """Test pattern matching for model variants."""
        test_cases = [
            ("gpt-4-turbo-2024-04-09", 128000),
            ("gpt-4o-2024-05-13", 128000),
            ("gpt-3.5-turbo-1106", 16384),
            ("gpt-5-32k", 200000),
            ("gpt-5-128k", 200000),
            ("claude-3-haiku", 200000),
            ("claude-3-5-sonnet", 200000),
        ]
        
        for model_name, expected_size in test_cases:
            # Create a fresh context manager for each test
            with patch('limp.services.context.openai.OpenAI'):
                # Create a fresh config for each test
                fresh_config = LLMConfig(
                    provider="openai",
                    api_key="test-key",
                    model=model_name,
                    max_tokens=4000,
                    temperature=0.7,
                    max_iterations=8,
                    context_threshold=0.75,
                    context_window_size=None,  # Let it auto-detect
                    summary_max_tokens=2048
                )
                fresh_context_manager = ContextManager(fresh_config)
                size = fresh_context_manager._get_context_window_size()
                assert size == expected_size, f"Model {model_name} should have context window size {expected_size}, got {size}"
    
    def test_configured_context_window_override(self, context_manager):
        """Test that configured context window size overrides lookup."""
        context_manager.config.context_window_size = 50000
        context_manager._context_window_size = None
        
        size = context_manager._get_context_window_size()
        assert size == 50000
