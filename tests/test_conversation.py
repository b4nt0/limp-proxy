"""
Tests for conversation and message management.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from unittest.mock import Mock, patch

from limp.models.user import User
from limp.models.conversation import Conversation, Message
from limp.api.im import (
    get_or_create_conversation,
    should_create_new_conversation,
    store_user_message,
    store_assistant_message,
    get_conversation_history
)
from limp.config import Config, IMPlatformConfig


class TestConversationManagement:
    """Test conversation management logic."""
    
    def test_slack_thread_conversation(self, test_session: Session, test_config):
        """Test Slack thread-based conversation grouping."""
        # Create a user
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # First message in a thread
        message_data = {
            "user_id": "U123",
            "channel": "C123",
            "text": "Hello",
            "timestamp": "1234567890.123456"
        }
        
        with patch('limp.api.im.get_config', return_value=test_config):
            conversation = get_or_create_conversation(test_session, user.id, message_data, "slack")
            
            assert conversation.user_id == user.id
            assert conversation.context["thread_ts"] == "1234567890.123456"
            assert conversation.context["channel"] == "C123"
            
            # Reply in the same thread
            reply_data = {
                "user_id": "U123",
                "channel": "C123",
                "text": "Reply",
                "timestamp": "1234567891.123456",
                "thread_ts": "1234567890.123456"  # Same thread
            }
            
            same_conversation = get_or_create_conversation(test_session, user.id, reply_data, "slack")
            assert same_conversation.id == conversation.id
            
            # New message in different thread
            new_thread_data = {
                "user_id": "U123",
                "channel": "C123",
                "text": "New thread",
                "timestamp": "1234567892.123456"
            }
            
            new_conversation = get_or_create_conversation(test_session, user.id, new_thread_data, "slack")
            assert new_conversation.id != conversation.id
    
    def test_teams_dm_conversation_timeout(self, test_session: Session):
        """Test Teams DM conversation timeout logic."""
        # Create a user
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 2
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        with patch('limp.api.im.get_config', return_value=mock_config):
            # First message in DM
            message_data = {
                "user_id": "U123",
                "channel": "19:dm-channel-id",  # Teams DM channel
                "text": "Hello"
            }
            
            conversation = get_or_create_conversation(test_session, user.id, message_data, "teams")
            assert conversation.user_id == user.id
            assert conversation.context["conversation_type"] == "dm"
            
            # Simulate old conversation (3 hours ago)
            old_time = datetime.utcnow() - timedelta(hours=3)
            conversation.updated_at = old_time
            test_session.commit()
            
            # New message should create new conversation due to timeout
            new_message_data = {
                "user_id": "U123",
                "channel": "19:dm-channel-id",
                "text": "New message"
            }
            
            new_conversation = get_or_create_conversation(test_session, user.id, new_message_data, "teams")
            assert new_conversation.id != conversation.id
    
    def test_teams_new_command(self, test_session: Session):
        """Test Teams /new command to force new conversation."""
        # Create a user
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 8
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        with patch('limp.api.im.get_config', return_value=mock_config):
            # First message
            message_data = {
                "user_id": "U123",
                "channel": "19:dm-channel-id",
                "text": "Hello"
            }
            
            conversation = get_or_create_conversation(test_session, user.id, message_data, "teams")
            
            # /new command should create new conversation
            new_command_data = {
                "user_id": "U123",
                "channel": "19:dm-channel-id",
                "text": "/new"
            }
            
            new_conversation = get_or_create_conversation(test_session, user.id, new_command_data, "teams")
            assert new_conversation.id != conversation.id
    
    def test_teams_channel_no_timeout(self, test_session: Session):
        """Test Teams channel conversations don't use timeout."""
        # Create a user
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 1  # Very short timeout
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        with patch('limp.api.im.get_config', return_value=mock_config):
            # First message in channel
            message_data = {
                "user_id": "U123",
                "channel": "C123",  # Channel, not DM
                "text": "Hello"
            }
            
            conversation = get_or_create_conversation(test_session, user.id, message_data, "teams")
            assert conversation.context["conversation_type"] == "channel"
            
            # Simulate old conversation (2 hours ago)
            old_time = datetime.utcnow() - timedelta(hours=2)
            conversation.updated_at = old_time
            test_session.commit()
            
            # New message should reuse same conversation (no timeout for channels)
            new_message_data = {
                "user_id": "U123",
                "channel": "C123",
                "text": "New message"
            }
            
            same_conversation = get_or_create_conversation(test_session, user.id, new_message_data, "teams")
            assert same_conversation.id == conversation.id


class TestMessageStorage:
    """Test message storage and retrieval."""
    
    def test_store_user_message(self, test_session: Session):
        """Test storing user messages."""
        # Create user and conversation
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Store user message
        message = store_user_message(
            test_session, 
            conversation.id, 
            "Hello, world!", 
            "1234567890.123456"
        )
        
        assert message.conversation_id == conversation.id
        assert message.role == "user"
        assert message.content == "Hello, world!"
        assert message.message_metadata["timestamp"] == "1234567890.123456"
    
    def test_store_assistant_message(self, test_session: Session):
        """Test storing assistant messages."""
        # Create user and conversation
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Store assistant message
        metadata = {"tool_calls": [{"id": "call_123", "function": {"name": "get_weather"}}]}
        message = store_assistant_message(
            test_session, 
            conversation.id, 
            "Here's the weather information.", 
            metadata
        )
        
        assert message.conversation_id == conversation.id
        assert message.role == "assistant"
        assert message.content == "Here's the weather information."
        assert message.message_metadata == metadata
    
    def test_get_conversation_history(self, test_session: Session):
        """Test retrieving conversation history."""
        # Create user and conversation
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Store multiple messages
        store_user_message(test_session, conversation.id, "Hello")
        store_assistant_message(test_session, conversation.id, "Hi there!")
        store_user_message(test_session, conversation.id, "How are you?")
        store_assistant_message(test_session, conversation.id, "I'm doing well, thanks!")
        
        # Get conversation history
        history = get_conversation_history(test_session, conversation.id)
        
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Hello"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "Hi there!"
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "How are you?"
        assert history[3]["role"] == "assistant"
        assert history[3]["content"] == "I'm doing well, thanks!"


class TestConversationTimeout:
    """Test conversation timeout logic."""
    
    def test_should_create_new_conversation_timeout(self, test_session: Session):
        """Test timeout logic for creating new conversations."""
        # Create conversation with old timestamp
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(
            user_id=user.id,
            context={"conversation_type": "dm"}
        )
        # Set old timestamp
        conversation.updated_at = datetime.utcnow() - timedelta(hours=10)
        test_session.add(conversation)
        test_session.commit()
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 8
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        message_data = {"channel": "19:dm-channel"}
        
        # Should create new conversation due to timeout
        assert should_create_new_conversation(conversation, mock_config, message_data) is True
    
    def test_should_not_create_new_conversation_recent(self, test_session: Session):
        """Test that recent conversations don't timeout."""
        # Create conversation with recent timestamp
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(
            user_id=user.id,
            context={"conversation_type": "dm"}
        )
        # Set recent timestamp
        conversation.updated_at = datetime.utcnow() - timedelta(minutes=30)
        test_session.add(conversation)
        test_session.commit()
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 8
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        message_data = {"channel": "19:dm-channel"}
        
        # Should not create new conversation
        assert should_create_new_conversation(conversation, mock_config, message_data) is False
    
    def test_should_not_create_new_conversation_channel(self, test_session: Session):
        """Test that channel conversations don't timeout."""
        # Create conversation for channel
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(
            user_id=user.id,
            context={"conversation_type": "channel"}
        )
        # Set old timestamp
        conversation.updated_at = datetime.utcnow() - timedelta(hours=10)
        test_session.add(conversation)
        test_session.commit()
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 8
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        message_data = {"channel": "C123"}
        
        # Should not create new conversation (channels don't timeout)
        assert should_create_new_conversation(conversation, mock_config, message_data) is False
    
    def test_should_not_create_new_conversation_no_context(self, test_session: Session):
        """Test that conversations without context don't timeout."""
        # Create conversation without context
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        conversation = Conversation(user_id=user.id)
        # Set old timestamp
        conversation.updated_at = datetime.utcnow() - timedelta(hours=10)
        test_session.add(conversation)
        test_session.commit()
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 8
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        message_data = {"channel": "19:dm-channel"}
        
        # Should not create new conversation (no context)
        assert should_create_new_conversation(conversation, mock_config, message_data) is False


class TestConversationIntegration:
    """Integration tests for conversation management."""
    
    def test_full_conversation_flow_slack(self, test_session: Session, test_config):
        """Test complete conversation flow for Slack."""
        # Create user
        user = User(external_id="U123", platform="slack")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # First message
        message_data = {
            "user_id": "U123",
            "channel": "C123",
            "text": "Hello",
            "timestamp": "1234567890.123456"
        }
        
        with patch('limp.api.im.get_config', return_value=test_config):
            conversation = get_or_create_conversation(test_session, user.id, message_data, "slack")
            store_user_message(test_session, conversation.id, "Hello", "1234567890.123456")
            
            # Reply in thread
            reply_data = {
                "user_id": "U123",
                "channel": "C123",
                "text": "How are you?",
                "timestamp": "1234567891.123456",
                "thread_ts": "1234567890.123456"
            }
            
            same_conversation = get_or_create_conversation(test_session, user.id, reply_data, "slack")
            store_user_message(test_session, same_conversation.id, "How are you?", "1234567891.123456")
            
            # Assistant response
            store_assistant_message(test_session, same_conversation.id, "I'm doing well, thanks!")
            
            # Get history
            history = get_conversation_history(test_session, same_conversation.id)
            
            assert len(history) == 3
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "Hello"
            assert history[1]["role"] == "user"
            assert history[1]["content"] == "How are you?"
            assert history[2]["role"] == "assistant"
            assert history[2]["content"] == "I'm doing well, thanks!"
    
    def test_full_conversation_flow_teams_dm(self, test_session: Session):
        """Test complete conversation flow for Teams DM."""
        # Create user
        user = User(external_id="U123", platform="teams")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # Mock config
        mock_config = Mock()
        mock_teams_config = Mock()
        mock_teams_config.conversation_timeout_hours = 8
        mock_config.get_im_platform_by_key.return_value = mock_teams_config
        
        with patch('limp.api.im.get_config', return_value=mock_config):
            # First message in DM
            message_data = {
                "user_id": "U123",
                "channel": "19:dm-channel-id",
                "text": "Hello"
            }
            
            conversation = get_or_create_conversation(test_session, user.id, message_data, "teams")
            store_user_message(test_session, conversation.id, "Hello")
            store_assistant_message(test_session, conversation.id, "Hi there!")
            
            # Second message in same conversation
            message_data2 = {
                "user_id": "U123",
                "channel": "19:dm-channel-id",
                "text": "How are you?"
            }
            
            same_conversation = get_or_create_conversation(test_session, user.id, message_data2, "teams")
            store_user_message(test_session, same_conversation.id, "How are you?")
            store_assistant_message(test_session, same_conversation.id, "I'm doing well!")
            
            # Get history
            history = get_conversation_history(test_session, same_conversation.id)
            
            assert len(history) == 4
            assert history[0]["role"] == "user"
            assert history[0]["content"] == "Hello"
            assert history[1]["role"] == "assistant"
            assert history[1]["content"] == "Hi there!"
            assert history[2]["role"] == "user"
            assert history[2]["content"] == "How are you?"
            assert history[3]["role"] == "assistant"
            assert history[3]["content"] == "I'm doing well!"
