"""
Demonstration test showing context management in action.
This test simulates a long conversation that triggers summarization.
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

from limp.services.context import ContextManager
from limp.config import LLMConfig
from limp.models.conversation import Message


class TestContextManagementDemo:
    """Demonstration of context management functionality."""
    
    @pytest.fixture
    def llm_config(self):
        """Create a test LLM configuration with low threshold for demo."""
        return LLMConfig(
            provider="openai",
            api_key="test-key",
            model="gpt-4",
            max_tokens=4000,
            temperature=0.7,
            max_iterations=8,
            context_threshold=0.1,  # Very low threshold for demo
            context_window_size=1000,  # Small window for demo
            summary_max_tokens=200
        )
    
    @pytest.fixture
    def context_manager(self, llm_config):
        """Create a context manager instance."""
        with patch('limp.services.context.openai.OpenAI'):
            return ContextManager(llm_config)
    
    def test_context_management_demo(self, context_manager):
        """Demonstrate context management with a simulated long conversation."""
        # Create a long conversation that would exceed the context threshold
        long_messages = []
        for i in range(20):
            long_messages.append({
                "role": "user",
                "content": f"This is a very long message number {i}. " * 100  # Make it very long
            })
            long_messages.append({
                "role": "assistant", 
                "content": f"This is a very long response number {i}. " * 100
            })
        
        # Test that the conversation should be summarized
        should_summarize = context_manager.should_summarize(long_messages)
        assert should_summarize, "Long conversation should trigger summarization"
        
        # Test summarization
        with patch.object(context_manager.client.chat.completions, 'create') as mock_create:
            mock_response = Mock()
            mock_response.choices = [Mock()]
            mock_response.choices[0].message.content = "This is a summary of a long conversation about various topics."
            mock_create.return_value = mock_response
            
            summary = context_manager.summarize_conversation(long_messages, exclude_tool_calls=True)
            assert "summary" in summary.lower()
            assert len(summary) < len(" ".join([msg["content"] for msg in long_messages]))
    
    def test_summary_storage_and_reconstruction(self, context_manager):
        """Test storing and reconstructing conversation with summaries."""
        # Mock database session
        mock_db = Mock()
        
        # Create mock messages with an existing summary
        mock_messages = [
            Mock(spec=Message),
            Mock(spec=Message), 
            Mock(spec=Message),
            Mock(spec=Message)
        ]
        
        # Original user request
        mock_messages[0].role = "user"
        mock_messages[0].content = "What is the weather like today?"
        mock_messages[0].created_at = datetime(2024, 1, 1, 10, 0, 0)
        mock_messages[0].message_metadata = None
        
        # Summary of previous conversation
        mock_messages[1].role = "summary"
        mock_messages[1].content = "Previous conversation was about weather, user asked about temperature and conditions."
        mock_messages[1].created_at = datetime(2024, 1, 1, 10, 30, 0)
        mock_messages[1].message_metadata = {"type": "conversation_summary"}
        
        # New messages after summary
        mock_messages[2].role = "user"
        mock_messages[2].content = "What about tomorrow?"
        mock_messages[2].created_at = datetime(2024, 1, 1, 11, 0, 0)
        mock_messages[2].message_metadata = None
        
        mock_messages[3].role = "assistant"
        mock_messages[3].content = "Tomorrow will be sunny with a high of 75°F."
        mock_messages[3].created_at = datetime(2024, 1, 1, 11, 1, 0)
        mock_messages[3].message_metadata = None
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        # Test reconstruction
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should include: original request + summary + new messages
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "What is the weather like today?"
        assert history[1]["role"] == "system"
        assert "Previous conversation was about weather" in history[1]["content"]
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "What about tomorrow?"
        assert history[3]["role"] == "assistant"
        assert history[3]["content"] == "Tomorrow will be sunny with a high of 75°F."
    
    def test_multiple_summarizations(self, context_manager):
        """Test handling multiple summarizations in a very long conversation."""
        # Mock database session
        mock_db = Mock()
        
        # Create messages with multiple summaries
        mock_messages = [
            Mock(spec=Message),  # Original request
            Mock(spec=Message),  # First summary
            Mock(spec=Message),  # More messages
            Mock(spec=Message),  # Second summary
            Mock(spec=Message),  # Latest messages
        ]
        
        mock_messages[0].role = "user"
        mock_messages[0].content = "Original request"
        mock_messages[0].created_at = datetime(2024, 1, 1, 10, 0, 0)
        
        mock_messages[1].role = "summary"
        mock_messages[1].content = "First summary of early conversation"
        mock_messages[1].created_at = datetime(2024, 1, 1, 10, 30, 0)
        
        mock_messages[2].role = "user"
        mock_messages[2].content = "More conversation"
        mock_messages[2].created_at = datetime(2024, 1, 1, 11, 0, 0)
        
        mock_messages[3].role = "summary"
        mock_messages[3].content = "Second summary of middle conversation"
        mock_messages[3].created_at = datetime(2024, 1, 1, 11, 30, 0)
        
        mock_messages[4].role = "user"
        mock_messages[4].content = "Latest message"
        mock_messages[4].created_at = datetime(2024, 1, 1, 12, 0, 0)
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_messages
        
        # Test reconstruction - should use the latest summary
        history = context_manager.reconstruct_history_with_summary(mock_db, 1)
        
        # Should include: original request + more conversation + latest summary + latest message
        assert len(history) == 4
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "Original request"
        assert history[1]["role"] == "user"
        assert history[1]["content"] == "More conversation"
        assert history[2]["role"] == "system"
        assert "Second summary of middle conversation" in history[2]["content"]
        assert history[3]["role"] == "user"
        assert history[3]["content"] == "Latest message"
