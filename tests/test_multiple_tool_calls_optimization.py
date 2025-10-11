"""
Regression test for multiple tool calls optimization.

This test verifies that the optimize_messages_for_tool_calls function correctly handles
scenarios where an assistant makes multiple tool calls in a single response.
"""

import pytest
from limp.services.context import ContextManager
from limp.config import LLMConfig


class TestMultipleToolCallsOptimization:
    """Test that multiple tool calls in a single assistant message are handled correctly."""

    @pytest.fixture
    def context_manager(self):
        """Create a ContextManager instance for testing."""
        llm_config = LLMConfig(
            api_key="test_key",
            model="gpt-4",
            max_tokens=1000,
            temperature=0.7
        )
        return ContextManager(llm_config)

    def test_single_assistant_message_with_multiple_tool_calls(self, context_manager):
        """Test that all tool responses for a single assistant message are preserved."""
        messages = [
            {"role": "user", "content": "Get resources and combo cube data"},
            {
                "role": "assistant",
                "content": "I'll help you get the resources and combo cube data.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "getResources",
                            "arguments": '{"organization_id": 4884}'
                        }
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {
                            "name": "getComboCube",
                            "arguments": '{"organization_id": 4884}'
                        }
                    }
                ]
            },
            {"role": "tool", "content": "Resources: [...]", "tool_call_id": "call_1"},
            {"role": "tool", "content": "Combo cube: [...]", "tool_call_id": "call_2"}
        ]

        optimized = context_manager.optimize_messages_for_tool_calls(messages)

        # Verify that the assistant message with tool calls is present
        assistant_messages = [m for m in optimized if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_messages) == 1

        # Verify that both tool responses are present
        tool_messages = [m for m in optimized if m.get("role") == "tool"]
        assert len(tool_messages) == 2

        # Verify the tool call IDs
        tool_call_ids = [m.get("tool_call_id") for m in tool_messages]
        assert "call_1" in tool_call_ids
        assert "call_2" in tool_call_ids

    def test_multiple_iterations_with_single_tool_calls(self, context_manager):
        """Test that only the latest successful tool call is kept across multiple iterations."""
        messages = [
            {"role": "user", "content": "Get resources"},
            # First iteration
            {
                "role": "assistant",
                "content": "I'll get the resources.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "getResources", "arguments": '{"organization_id": 4884}'}
                    }
                ]
            },
            {"role": "tool", "content": "Resources: [...]", "tool_call_id": "call_1"},
            # Second iteration
            {
                "role": "assistant",
                "content": "I'll get more data.",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "getComboCube", "arguments": '{"organization_id": 4884}'}
                    }
                ]
            },
            {"role": "tool", "content": "Combo cube: [...]", "tool_call_id": "call_2"}
        ]

        optimized = context_manager.optimize_messages_for_tool_calls(messages)

        # Verify that only the second assistant message is present
        assistant_messages = [m for m in optimized if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_messages) == 1
        assert assistant_messages[0]["tool_calls"][0]["id"] == "call_2"

        # Verify that only the second tool response is present
        tool_messages = [m for m in optimized if m.get("role") == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["tool_call_id"] == "call_2"

    def test_latest_assistant_message_with_multiple_tool_calls(self, context_manager):
        """Test that all tool responses for the latest assistant message are preserved."""
        messages = [
            {"role": "user", "content": "Get resources"},
            # First iteration - single tool call
            {
                "role": "assistant",
                "content": "I'll get the resources.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "getResources", "arguments": '{"organization_id": 4884}'}
                    }
                ]
            },
            {"role": "tool", "content": "Resources: [...]", "tool_call_id": "call_1"},
            # Second iteration - multiple tool calls
            {
                "role": "assistant",
                "content": "I'll get more data.",
                "tool_calls": [
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "getComboCube", "arguments": '{"organization_id": 4884}'}
                    },
                    {
                        "id": "call_3",
                        "type": "function",
                        "function": {"name": "getProjects", "arguments": '{"organization_id": 4884}'}
                    }
                ]
            },
            {"role": "tool", "content": "Combo cube: [...]", "tool_call_id": "call_2"},
            {"role": "tool", "content": "Projects: [...]", "tool_call_id": "call_3"}
        ]

        optimized = context_manager.optimize_messages_for_tool_calls(messages)

        # Verify that only the second assistant message is present
        assistant_messages = [m for m in optimized if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_messages) == 1
        assert len(assistant_messages[0]["tool_calls"]) == 2

        # Verify that both tool responses from the second iteration are present
        tool_messages = [m for m in optimized if m.get("role") == "tool"]
        assert len(tool_messages) == 2

        # Verify the tool call IDs
        tool_call_ids = [m.get("tool_call_id") for m in tool_messages]
        assert "call_2" in tool_call_ids
        assert "call_3" in tool_call_ids
        assert "call_1" not in tool_call_ids

    def test_failed_tool_call_with_multiple_calls(self, context_manager):
        """Test that failed tool calls don't cause issues with multiple tool calls."""
        messages = [
            {"role": "user", "content": "Get resources"},
            {
                "role": "assistant",
                "content": "I'll get the resources.",
                "tool_calls": [
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "getResources", "arguments": '{"organization_id": 4884}'}
                    },
                    {
                        "id": "call_2",
                        "type": "function",
                        "function": {"name": "getComboCube", "arguments": '{"organization_id": 4884}'}
                    }
                ]
            },
            {"role": "tool", "content": "Error: Access denied", "tool_call_id": "call_1"},
            {"role": "tool", "content": "Combo cube: [...]", "tool_call_id": "call_2"}
        ]

        optimized = context_manager.optimize_messages_for_tool_calls(messages)

        # Verify that the assistant message is present
        assistant_messages = [m for m in optimized if m.get("role") == "assistant" and "tool_calls" in m]
        assert len(assistant_messages) == 1

        # Verify that both tool responses are present (including the failed one)
        tool_messages = [m for m in optimized if m.get("role") == "tool"]
        assert len(tool_messages) == 2

    def test_no_tool_calls(self, context_manager):
        """Test that regular messages without tool calls are preserved."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi! How can I help you?"},
            {"role": "user", "content": "Get resources"},
            {"role": "assistant", "content": "Sure!"}
        ]

        optimized = context_manager.optimize_messages_for_tool_calls(messages)

        # All messages should be preserved
        assert len(optimized) == len(messages)

    def test_empty_messages(self, context_manager):
        """Test that empty messages list is handled correctly."""
        messages = []
        optimized = context_manager.optimize_messages_for_tool_calls(messages)
        assert len(optimized) == 0
