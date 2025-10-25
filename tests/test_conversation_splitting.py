"""
Tests for conversation splitting logic.
Tests /new command detection and time-based break detection for both Slack and Teams.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from unittest.mock import Mock, patch

from limp.models.user import User
from limp.models.conversation import Conversation, Message
from limp.api.im import (
    detect_conversation_break_from_formatted_history,
    get_conversation_history
)
from limp.config import Config, IMPlatformConfig


class TestConversationSplitting:
    """Test conversation splitting logic."""
    
    def test_new_command_detection_slack(self):
        """Test /new command detection for Slack."""
        config = self._create_mock_config()
        
        history = [
            {"role": "user", "content": "Hello", "created_at": datetime.now() - timedelta(hours=10)},
            {"role": "assistant", "content": "Hi there!", "created_at": datetime.now() - timedelta(hours=9)},
            {"role": "user", "content": "/new", "created_at": datetime.now() - timedelta(hours=8)},
            {"role": "user", "content": "Start over", "created_at": datetime.now() - timedelta(hours=7)},
        ]
        
        break_index = detect_conversation_break_from_formatted_history(history, "slack", config)
        assert break_index == 3, f"Expected break at index 3, got {break_index}"
    
    def test_new_command_detection_teams(self):
        """Test /new command detection for Teams."""
        config = self._create_mock_config()
        
        history = [
            {"role": "user", "content": "Hello", "created_at": datetime.now() - timedelta(hours=10)},
            {"role": "assistant", "content": "Hi there!", "created_at": datetime.now() - timedelta(hours=9)},
            {"role": "user", "content": "/new", "created_at": datetime.now() - timedelta(hours=8)},
            {"role": "user", "content": "Start over", "created_at": datetime.now() - timedelta(hours=7)},
        ]
        
        break_index = detect_conversation_break_from_formatted_history(history, "teams", config)
        assert break_index == 3, f"Expected break at index 3, got {break_index}"
    
    def test_time_based_detection_teams(self):
        """Test time-based break detection for Teams."""
        config = self._create_mock_config()
        
        now = datetime.now()
        history = [
            {"role": "user", "content": "Hello", "created_at": now - timedelta(hours=10)},
            {"role": "assistant", "content": "Hi there!", "created_at": now - timedelta(hours=9)},
            {"role": "user", "content": "New message", "created_at": now},
        ]
        
        break_index = detect_conversation_break_from_formatted_history(history, "teams", config)
        assert break_index == 2, f"Expected break at index 2, got {break_index}"
    
    def test_time_based_detection_slack_ignored(self):
        """Test that time-based breaks are ignored for Slack."""
        config = self._create_mock_config()
        
        now = datetime.now()
        history = [
            {"role": "user", "content": "Hello", "created_at": now - timedelta(hours=10)},
            {"role": "assistant", "content": "Hi there!", "created_at": now - timedelta(hours=9)},
            {"role": "user", "content": "New message", "created_at": now},
        ]
        
        break_index = detect_conversation_break_from_formatted_history(history, "slack", config)
        assert break_index == -1, f"Expected no break for Slack, got {break_index}"
    
    def test_no_break_detection(self):
        """Test when no break should be detected."""
        config = self._create_mock_config()
        
        now = datetime.now()
        history = [
            {"role": "user", "content": "Hello", "created_at": now - timedelta(hours=1)},
            {"role": "assistant", "content": "Hi there!", "created_at": now - timedelta(minutes=30)},
            {"role": "user", "content": "New message", "created_at": now},
        ]
        
        for platform in ["slack", "teams"]:
            break_index = detect_conversation_break_from_formatted_history(history, platform, config)
            assert break_index == -1, f"Expected no break for {platform}, got {break_index}"
    
    def test_edge_cases(self):
        """Test edge cases for break detection."""
        config = self._create_mock_config()
        
        # Test empty history
        break_index = detect_conversation_break_from_formatted_history([], "teams", config)
        assert break_index == -1, f"Expected no break for empty history, got {break_index}"
        
        # Test single message
        history = [{"role": "user", "content": "Hello", "created_at": datetime.now()}]
        break_index = detect_conversation_break_from_formatted_history(history, "teams", config)
        assert break_index == -1, f"Expected no break for single message, got {break_index}"
        
        # Test /new at the beginning
        history = [
            {"role": "user", "content": "/new", "created_at": datetime.now() - timedelta(hours=1)},
            {"role": "user", "content": "Start fresh", "created_at": datetime.now()}
        ]
        break_index = detect_conversation_break_from_formatted_history(history, "teams", config)
        assert break_index == 1, f"Expected break at index 1, got {break_index}"
    
    def test_performance_large_history(self):
        """Test performance with large conversation history."""
        config = self._create_mock_config()
        
        # Create large history (1000 messages)
        base_time = datetime.now()
        history = []
        for i in range(1000):
            history.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "created_at": base_time - timedelta(hours=1000-i)
            })
        
        # Insert /new command in the middle
        history[500]["content"] = "/new"
        
        import time
        start_time = time.time()
        break_index = detect_conversation_break_from_formatted_history(history, "teams", config)
        end_time = time.time()
        
        assert break_index == 501, f"Expected break at index 501, got {break_index}"
        assert end_time - start_time < 1.0, f"Break detection took too long: {end_time - start_time:.3f}s"
    
    def test_integration_with_database(self, test_session: Session, test_config):
        """Test integration with database and context manager."""
        # Create test user
        user = User(external_id="test_user_split", platform="teams", display_name="Test User")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # Create test conversation
        conversation = Conversation(
            user_id=user.id,
            channel_id="test_channel",
            context={"conversation_type": "dm"}
        )
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Create test messages with /new command
        base_time = datetime.now()
        messages = [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Hello",
                created_at=base_time - timedelta(hours=10)
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Hi there!",
                created_at=base_time - timedelta(hours=9)
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="/new",
                created_at=base_time - timedelta(hours=8)
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Start over",
                created_at=base_time - timedelta(hours=7)
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="I'm ready to help!",
                created_at=base_time - timedelta(hours=6)
            )
        ]
        
        for message in messages:
            test_session.add(message)
        test_session.commit()
        
        # Test conversation history retrieval with break detection
        with patch('limp.api.im.get_config', return_value=test_config):
            history = get_conversation_history(
                test_session, 
                conversation.id, 
                platform="teams"
            )
        
        # Verify that history was trimmed after /new command
        # Should only contain messages after /new (2 messages: "Start over" and "I'm ready to help!")
        assert len(history) == 2, f"Expected 2 messages after trimming, got {len(history)}"
        
        # Verify the content of remaining messages
        assert history[0]["content"] == "Start over", f"Expected 'Start over', got {history[0]['content']}"
        assert history[1]["content"] == "I'm ready to help!", f"Expected 'I'm ready to help!', got {history[1]['content']}"
        
        # Verify that created_at field is NOT present (removed for JSON serialization)
        for message in history:
            assert "created_at" not in message, "created_at field should not be present in LLM messages"
    
    def test_time_based_integration_with_database(self, test_session: Session, test_config):
        """Test time-based break detection with database."""
        # Create test user
        user = User(external_id="test_user_time_split", platform="teams", display_name="Test User Time")
        test_session.add(user)
        test_session.commit()
        test_session.refresh(user)
        
        # Create test conversation
        conversation = Conversation(
            user_id=user.id,
            channel_id="test_channel",
            context={"conversation_type": "dm"}
        )
        test_session.add(conversation)
        test_session.commit()
        test_session.refresh(conversation)
        
        # Create test messages with time gap (no /new command)
        base_time = datetime.now()
        messages = [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Hello",
                created_at=base_time - timedelta(hours=10)  # 10 hours ago
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Hi there!",
                created_at=base_time - timedelta(hours=9)   # 9 hours ago
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="New message after long gap",
                created_at=base_time  # Now (10+ hours later)
            )
        ]
        
        for message in messages:
            test_session.add(message)
        test_session.commit()
        
        # Test conversation history retrieval with time-based break detection
        with patch('limp.api.im.get_config', return_value=test_config):
            history = get_conversation_history(
                test_session, 
                conversation.id, 
                platform="teams"
            )
        
        # Verify that history was trimmed after time gap
        # Should only contain the last message
        assert len(history) == 1, f"Expected 1 message after time gap trimming, got {len(history)}"
        assert history[0]["content"] == "New message after long gap", f"Expected 'New message after long gap', got {history[0]['content']}"
    
    def _create_mock_config(self):
        """Create a mock configuration for testing."""
        class MockTeamsConfig:
            conversation_timeout_hours = 8
        
        class MockConfig:
            def get_im_platform_by_key(self, key):
                if key == "teams":
                    return MockTeamsConfig()
                raise ValueError(f"Platform {key} not found")
        
        return MockConfig()
