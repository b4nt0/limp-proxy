"""
Tests for context management with initial messages (system, setup, etc.).
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from limp.services.context import ContextManager
from limp.config import LLMConfig
from limp.models.conversation import Message, Conversation
from limp.models.user import User


class TestContextInitialMessages:
    """Test that initial messages are preserved consistently."""
    
    def test_reconstruct_history_preserves_initial_system_messages(self, test_session: Session):
        """Test that initial system messages are preserved when reconstructing with summary."""
        # Create user and conversation
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Create messages with initial system message
        messages = [
            Message(
                conversation_id=conversation.id,
                role="system",
                content="You are a helpful assistant. Always be polite and professional.",
                message_metadata={"type": "system_prompt"}
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Hello, how are you?",
                message_metadata={}
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="I'm doing well, thank you! How can I help you today?",
                message_metadata={}
            ),
            Message(
                conversation_id=conversation.id,
                role="summary",
                content="User greeted the assistant and asked how they were doing.",
                message_metadata={"type": "conversation_summary"}
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="What's the weather like?",
                message_metadata={}
            )
        ]
        
        for message in messages:
            test_session.add(message)
        test_session.commit()
        
        # Test reconstruction with summary
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4"
        )
        
        with patch('limp.services.context.openai.OpenAI'):
            context_manager = ContextManager(config)
            
            # Mock the database query
            with patch.object(test_session, 'query') as mock_query:
                mock_query.return_value.filter.return_value.order_by.return_value.all.return_value = messages
                
                reconstructed = context_manager.reconstruct_history_with_summary(test_session, conversation.id)
        
        # Verify that the initial system message is preserved
        assert len(reconstructed) == 5  # system + user + assistant + summary + user
        
        # Check that the system message is preserved
        assert reconstructed[0]["role"] == "system"
        assert reconstructed[0]["content"] == "You are a helpful assistant. Always be polite and professional."
        
        # Check that the original user message is preserved
        assert reconstructed[1]["role"] == "user"
        assert reconstructed[1]["content"] == "Hello, how are you?"
        
        # Check that the assistant message is preserved
        assert reconstructed[2]["role"] == "assistant"
        assert reconstructed[2]["content"] == "I'm doing well, thank you! How can I help you today?"
        
        # Check that the summary is included
        assert reconstructed[3]["role"] == "system"
        assert "Previous conversation summary:" in reconstructed[3]["content"]
        
        # Check that the latest user message is included
        assert reconstructed[4]["role"] == "user"
        assert reconstructed[4]["content"] == "What's the weather like?"
    
    def test_reconstruct_history_without_summary_preserves_all_initial_messages(self, test_session: Session):
        """Test that all initial messages are preserved when no summary exists."""
        # Create user and conversation
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Create messages with multiple initial messages
        messages = [
            Message(
                conversation_id=conversation.id,
                role="system",
                content="You are a helpful assistant.",
                message_metadata={"type": "system_prompt"}
            ),
            Message(
                conversation_id=conversation.id,
                role="system",
                content="Always provide accurate information.",
                message_metadata={"type": "system_instruction"}
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Hello!",
                message_metadata={}
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Hi there! How can I help you?",
                message_metadata={}
            )
        ]
        
        for message in messages:
            test_session.add(message)
        test_session.commit()
        
        # Test reconstruction without summary
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4"
        )
        
        with patch('limp.services.context.openai.OpenAI'):
            context_manager = ContextManager(config)
            
            # Mock the database query
            with patch.object(test_session, 'query') as mock_query:
                mock_query.return_value.filter.return_value.order_by.return_value.all.return_value = messages
                
                reconstructed = context_manager.reconstruct_history_with_summary(test_session, conversation.id)
        
        # Verify that all messages are preserved
        assert len(reconstructed) == 4
        
        # Check that both system messages are preserved
        assert reconstructed[0]["role"] == "system"
        assert reconstructed[0]["content"] == "You are a helpful assistant."
        
        assert reconstructed[1]["role"] == "system"
        assert reconstructed[1]["content"] == "Always provide accurate information."
        
        # Check that user and assistant messages are preserved
        assert reconstructed[2]["role"] == "user"
        assert reconstructed[2]["content"] == "Hello!"
        
        assert reconstructed[3]["role"] == "assistant"
        assert reconstructed[3]["content"] == "Hi there! How can I help you?"
    
    def test_consistency_between_with_and_without_summary(self, test_session: Session):
        """Test that the same initial messages are preserved regardless of summary existence."""
        # Create user and conversation
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Create initial messages
        initial_messages = [
            Message(
                conversation_id=conversation.id,
                role="system",
                content="You are a helpful assistant.",
                message_metadata={"type": "system_prompt"}
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Hello!",
                message_metadata={}
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Hi there!",
                message_metadata={}
            )
        ]
        
        for message in initial_messages:
            test_session.add(message)
        test_session.commit()
        
        config = LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4"
        )
        
        with patch('limp.services.context.openai.OpenAI'):
            context_manager = ContextManager(config)
            
            # Test without summary
            with patch.object(test_session, 'query') as mock_query:
                mock_query.return_value.filter.return_value.order_by.return_value.all.return_value = initial_messages
                
                without_summary = context_manager.reconstruct_history_with_summary(test_session, conversation.id)
            
            # Test with summary (add summary message)
            messages_with_summary = initial_messages + [
                Message(
                    conversation_id=conversation.id,
                    role="summary",
                    content="User greeted the assistant.",
                    message_metadata={"type": "conversation_summary"}
                )
            ]
            
            with patch.object(test_session, 'query') as mock_query:
                mock_query.return_value.filter.return_value.order_by.return_value.all.return_value = messages_with_summary
                
                with_summary = context_manager.reconstruct_history_with_summary(test_session, conversation.id)
        
        # The initial messages should be the same in both cases
        assert len(without_summary) == 3  # system + user + assistant
        assert len(with_summary) == 4     # system + user + assistant + summary
        
        # Check that the initial messages are identical
        assert without_summary[0] == with_summary[0]  # system message
        assert without_summary[1] == with_summary[1]  # user message
        assert without_summary[2] == with_summary[2]  # assistant message
        
        # The only difference should be the summary
        assert with_summary[3]["role"] == "system"
        assert "Previous conversation summary:" in with_summary[3]["content"]
