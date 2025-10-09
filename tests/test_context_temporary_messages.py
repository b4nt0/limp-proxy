"""
Tests for context management temporary messages.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from limp.services.context import ContextManager
from limp.config import LLMConfig


class TestContextTemporaryMessages:
    """Test temporary message functionality for context management."""
    
    def test_context_usage_percentage(self):
        """Test context usage percentage calculation."""
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
            context_window_size=8000  # Set a specific size for testing
        )
        
        with patch('limp.services.context.openai.OpenAI'):
            context_manager = ContextManager(config)
            
            # Test with empty messages
            messages = []
            percentage = context_manager.get_context_usage_percentage(messages)
            assert percentage == 0.0
            
            # Test with some messages
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
            
            with patch.object(context_manager, 'count_tokens', return_value=100):
                percentage = context_manager.get_context_usage_percentage(messages)
                assert percentage == 1.25  # 100/8000 * 100
    
    def test_append_context_usage_to_message(self):
        """Test appending context usage to existing message."""
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
            context_window_size=8000
        )

        with patch('limp.services.context.openai.OpenAI'):
            context_manager = ContextManager(config)

            messages = [{"role": "user", "content": "Hello"}]

            with patch.object(context_manager, 'get_context_usage_percentage', return_value=45.6):
                base_message = "1. Talking to Portfoleon. Get a list of organizations."
                enhanced_message = context_manager.append_context_usage_to_message(base_message, messages)
                assert enhanced_message == "1. Talking to Portfoleon. Get a list of organizations. 45.6% context"
    
    def test_summarization_message(self):
        """Test summarization message creation."""
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4"
        )
        
        with patch('limp.services.context.openai.OpenAI'):
            context_manager = ContextManager(config)
            
            message = context_manager.create_summarization_message()
            assert message == "Summarizing conversation to manage context..."
    
    def test_get_conversation_history_without_explicit_context_messages(self, test_session: Session):
        """Test that explicit context usage messages are no longer sent."""
        from limp.api.im import get_conversation_history

        # Create a mock IM service
        mock_im_service = Mock()
        mock_im_service.send_temporary_message.return_value = "temp_msg_123"

        # Create user and conversation
        from limp.models.user import User
        from limp.models.conversation import Conversation

        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)

        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)

        # Test with mocked context manager
        with patch('limp.api.im.get_config') as mock_get_config, \
             patch('limp.api.im.ContextManager') as mock_context_manager:

            # Mock config
            mock_config = Mock()
            mock_config.llm = Mock()
            mock_get_config.return_value = mock_config

            # Mock context manager
            mock_instance = Mock()
            mock_instance.reconstruct_history_with_summary.return_value = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
            mock_instance.should_summarize.return_value = False
            mock_context_manager.return_value = mock_instance

            # Call get_conversation_history with IM service
            history = get_conversation_history(
                test_session,
                conversation.id,
                im_service=mock_im_service,
                channel="C123",
                original_message_ts="1234567890.123456"
            )

            # Verify that no explicit context usage message was sent
            mock_im_service.send_temporary_message.assert_not_called()
            
            # Verify history is returned
            assert len(history) == 2
            assert history[0]["role"] == "user"
            assert history[1]["role"] == "assistant"
    
    def test_get_conversation_history_with_summarization_notification(self, test_session: Session):
        """Test that summarization notification is sent when summarizing."""
        from limp.api.im import get_conversation_history
        
        # Create a mock IM service
        mock_im_service = Mock()
        mock_im_service.send_temporary_message.return_value = "temp_msg_123"
        
        # Create user and conversation
        from limp.models.user import User
        from limp.models.conversation import Conversation
        
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Test with mocked context manager that triggers summarization
        with patch('limp.api.im.get_config') as mock_get_config, \
             patch('limp.api.im.ContextManager') as mock_context_manager:
            
            # Mock config
            mock_config = Mock()
            mock_config.llm = Mock()
            mock_get_config.return_value = mock_config
            
            # Mock context manager that triggers summarization
            mock_instance = Mock()
            mock_instance.reconstruct_history_with_summary.return_value = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ]
            mock_instance.should_summarize.return_value = True  # Trigger summarization
            mock_instance.create_context_usage_message.return_value = "Context usage: 75.0%"
            mock_instance.create_summarization_message.return_value = "Summarizing conversation to manage context..."
            mock_instance.summarize_conversation.return_value = "Previous conversation summary"
            mock_instance.store_summary.return_value = None
            mock_context_manager.return_value = mock_instance
            
            # Call get_conversation_history with IM service
            history = get_conversation_history(
                test_session, 
                conversation.id, 
                im_service=mock_im_service,
                channel="C123",
                original_message_ts="1234567890.123456"
            )
            
            # Verify that only summarization message was sent (no explicit context usage)
            assert mock_im_service.send_temporary_message.call_count == 1
            
            # Check the call
            calls = mock_im_service.send_temporary_message.call_args_list
            assert calls[0][0] == ("C123", "Summarizing conversation to manage context...", "1234567890.123456")
            
            # Verify history is returned
            assert len(history) == 2
