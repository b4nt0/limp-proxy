"""
Tests for builtin tools functionality.
"""

import pytest
from unittest.mock import Mock, patch
from sqlalchemy.orm import Session

from limp.services.tools import ToolsService
from limp.services.builtin_tools import LimpBuiltinStartOver
from limp.models.user import User
from limp.models.conversation import Conversation, Message
from limp.api.im import get_conversation_history


class TestBuiltinTools:
    """Test builtin tools functionality."""
    
    def test_get_builtin_tools(self):
        """Test getting builtin tools."""
        tools_service = ToolsService()
        builtin_tools = tools_service.get_builtin_tools()
        
        assert len(builtin_tools) == 2
        assert builtin_tools[0]["type"] == "function"
        assert builtin_tools[0]["function"]["name"] == "LimpBuiltinStartOver"
        assert "Start a new conversation" in builtin_tools[0]["function"]["description"]
        
        # Check the new authorization tool
        assert builtin_tools[1]["type"] == "function"
        assert builtin_tools[1]["function"]["name"] == "LimpBuiltinRequestAuthorization"
        assert "Request authorization for external systems" in builtin_tools[1]["function"]["description"]
    
    def test_limpbultin_start_over_execution(self):
        """Test LimpBuiltinStartOver tool execution."""
        tool = LimpBuiltinStartOver()
        result = tool.execute("{}")
        
        assert result["success"] is True
        assert result["result"] == "New conversation successfully started"
        assert result["action"] == "start_over"
    
    def test_limpbultin_start_over_with_invalid_json(self):
        """Test LimpBuiltinStartOver with invalid JSON arguments."""
        tool = LimpBuiltinStartOver()
        result = tool.execute("invalid json")
        
        assert result["success"] is True
        assert result["result"] == "New conversation successfully started"
        assert result["action"] == "start_over"
    
    def test_execute_builtin_tool_reflection(self):
        """Test builtin tool execution using reflection."""
        tools_service = ToolsService()
        result = tools_service.execute_builtin_tool("LimpBuiltinStartOver", "{}")
        
        assert result["success"] is True
        assert result["result"] == "New conversation successfully started"
        assert result["action"] == "start_over"
    
    def test_execute_builtin_tool_invalid_name(self):
        """Test builtin tool execution with invalid tool name."""
        tools_service = ToolsService()
        result = tools_service.execute_builtin_tool("InvalidTool", "{}")
        
        assert result["success"] is False
        assert "not a builtin tool" in result["error"]
    
    def test_execute_builtin_tool_nonexistent(self):
        """Test builtin tool execution with nonexistent tool."""
        tools_service = ToolsService()
        result = tools_service.execute_builtin_tool("LimpBuiltinNonExistent", "{}")
        
        assert result["success"] is False
        assert "not found or failed to execute" in result["error"]
    
    def test_tools_merging_in_workflow(self):
        """Test that builtin tools are merged with external tools."""
        tools_service = ToolsService()
        
        # Mock external tools
        external_tools = [
            {
                "type": "function",
                "function": {
                    "name": "external_tool",
                    "description": "External tool"
                }
            }
        ]
        
        # Mock the get_cleaned_tools_for_openai method
        with patch.object(tools_service, 'get_cleaned_tools_for_openai', return_value=external_tools):
            builtin_tools = tools_service.get_builtin_tools()
            all_tools = external_tools + builtin_tools
            
            # Should have both external and builtin tools (1 external + 2 builtin)
            assert len(all_tools) == 3
            assert any(tool["function"]["name"] == "external_tool" for tool in all_tools)
            assert any(tool["function"]["name"] == "LimpBuiltinStartOver" for tool in all_tools)
    
    def test_builtin_tool_integration_with_database(self, test_session: Session, test_config):
        """Test builtin tool integration with database and conversation history."""
        # Create test user
        user = User(external_id="test_user_builtin", platform="teams", display_name="Test User Builtin")
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
        
        # Create test messages
        from datetime import datetime, timedelta
        base_time = datetime.now()
        messages = [
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Hello",
                created_at=base_time - timedelta(hours=2)
            ),
            Message(
                conversation_id=conversation.id,
                role="assistant",
                content="Hi there!",
                created_at=base_time - timedelta(hours=1)
            ),
            Message(
                conversation_id=conversation.id,
                role="system",
                content="/new",
                created_at=base_time - timedelta(minutes=30)
            ),
            Message(
                conversation_id=conversation.id,
                role="user",
                content="Start fresh",
                created_at=base_time
            )
        ]
        
        for message in messages:
            test_session.add(message)
        test_session.commit()
        
        # Test conversation history retrieval with builtin tool break detection
        with patch('limp.api.im.get_config', return_value=test_config):
            history = get_conversation_history(
                test_session, 
                conversation.id, 
                platform="teams"
            )
        
        # Should only contain messages after the /new system message
        assert len(history) == 1, f"Expected 1 message after /new, got {len(history)}"
        assert history[0]["content"] == "Start fresh", f"Expected 'Start fresh', got {history[0]['content']}"
    
    def test_builtin_tool_system_message_persistence(self, test_session: Session, test_config):
        """Test that builtin tool system messages are persisted to database."""
        from limp.api.im import store_system_message
        
        # Create test user
        user = User(external_id="test_user_persistence", platform="teams", display_name="Test User Persistence")
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
        
        # Store system message using the new function
        system_message = store_system_message(test_session, conversation.id, "/new")
        
        # Verify the message was stored
        assert system_message.role == "system"
        assert system_message.content == "/new"
        assert system_message.conversation_id == conversation.id
        
        # Verify it appears in conversation history (but gets filtered out by break detection)
        with patch('limp.api.im.get_config', return_value=test_config):
            history = get_conversation_history(
                test_session, 
                conversation.id, 
                platform="teams"
            )
        
        # The system message should trigger break detection, so history should be empty
        # (since there are no messages after the /new system message)
        assert len(history) == 0, "System message should trigger break detection, resulting in empty history"
        
        # Now add a message after the system message to test break detection
        from datetime import datetime
        user_message = Message(
            conversation_id=conversation.id,
            role="user",
            content="Message after /new",
            created_at=datetime.now()
        )
        test_session.add(user_message)
        test_session.commit()
        
        # Now the history should contain only the message after the /new system message
        with patch('limp.api.im.get_config', return_value=test_config):
            history = get_conversation_history(
                test_session, 
                conversation.id, 
                platform="teams"
            )
        
        # Should only contain the message after the /new system message
        assert len(history) == 1, f"Expected 1 message after /new, got {len(history)}"
        assert history[0]["content"] == "Message after /new", f"Expected 'Message after /new', got {history[0]['content']}"
    
    def test_builtin_tool_error_handling(self):
        """Test builtin tool error handling."""
        # Create a custom tool class that raises an exception
        class FailingTool(LimpBuiltinStartOver):
            def _execute(self, arguments: str):
                raise Exception("Test error")
        
        tool = FailingTool()
        result = tool.execute("{}")
        
        # The base class should handle the exception
        assert result["success"] is False
        assert "Test error" in result["error"]
