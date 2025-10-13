"""
Context management service for handling conversation history and summarization.
"""

import tiktoken
import openai
from typing import List, Dict, Any, Optional, Tuple
import logging
from sqlalchemy.orm import Session

from ..config import LLMConfig
from ..models.conversation import Message

logger = logging.getLogger(__name__)


class ContextManager:
    """Manages conversation context and summarization."""
    
    def __init__(self, llm_config: LLMConfig):
        self.config = llm_config
        self.client = openai.OpenAI(
            api_key=llm_config.api_key,
            base_url=llm_config.base_url
        )
        self._context_window_size = None
        self._encoding = None
    
    def _get_encoding(self):
        """Get tiktoken encoding for the model."""
        if self._encoding is None:
            try:
                self._encoding = tiktoken.encoding_for_model(self.config.model)
            except KeyError:
                # Fallback to cl100k_base for unknown models
                self._encoding = tiktoken.get_encoding("cl100k_base")
        return self._encoding
    
    def _get_context_window_size(self) -> int:
        """Get the context window size for the model."""
        if self._context_window_size is None:
            if self.config.context_window_size:
                self._context_window_size = self.config.context_window_size
            else:
                # Use lookup table for known models
                self._context_window_size = self._get_model_context_window_size(self.config.model)
        
        return self._context_window_size
    
    def _get_model_context_window_size(self, model_name: str) -> int:
        """Get context window size for a specific model using lookup table."""
        # Context window sizes for known models (in tokens)
        context_limits = {
            # GPT-3.5 models
            "gpt-3.5-turbo": 4096,
            "gpt-3.5-turbo-16k": 16384,
            "gpt-3.5-turbo-1106": 16384,
            "gpt-3.5-turbo-0125": 16384,
            
            # GPT-4 models
            "gpt-4": 8192,
            "gpt-4-32k": 32768,
            "gpt-4-0613": 8192,
            "gpt-4-32k-0613": 32768,
            "gpt-4-1106-preview": 128000,
            "gpt-4-turbo": 128000,
            "gpt-4-turbo-preview": 128000,
            "gpt-4-turbo-2024-04-09": 128000,
            "gpt-4-turbo-2024-11-20": 128000,
            "gpt-4o": 128000,
            "gpt-4o-2024-05-13": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4o-mini-2024-07-18": 128000,
            
            # GPT-5 models (future-proofing)
            "gpt-5": 200000,  # Estimated based on trend
            "gpt-5-turbo": 200000,
            "gpt-5-32k": 200000,
            "gpt-5-128k": 200000,
            
            # Other models
            "o1-preview": 128000,
            "o1-mini": 128000,
        }
        
        # Direct lookup
        if model_name in context_limits:
            return context_limits[model_name]
        
        # Pattern matching for variants
        model_lower = model_name.lower()
        
        # GPT-5 pattern matching
        if "gpt-5" in model_lower:
            if "32k" in model_lower:
                return 200000  # Estimated
            elif "128k" in model_lower:
                return 200000  # Estimated
            else:
                return 200000  # Default GPT-5
        
        # GPT-4 pattern matching
        elif "gpt-4" in model_lower:
            if "32k" in model_lower:
                return 32768
            elif "128k" in model_lower or "turbo" in model_lower or "o" in model_lower:
                return 128000
            else:
                return 8192  # Default GPT-4
        
        # GPT-3.5 pattern matching
        elif "gpt-3.5" in model_lower:
            if "16k" in model_lower:
                return 16384
            else:
                return 4096  # Default GPT-3.5
        
        # Claude pattern matching
        elif "claude" in model_lower:
            return 200000  # Claude models have large context windows
        
        # Default fallback
        logger.warning(f"Unknown model '{model_name}', using default context window size of 8192")
        return 8192
    
    def count_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Count tokens in a list of messages."""
        encoding = self._get_encoding()
        total_tokens = 0
        
        for message in messages:
            # Count tokens for the message content
            content = message.get("content", "")
            if content:
                total_tokens += len(encoding.encode(content))
            
            # Add tokens for role and other metadata
            total_tokens += 4  # Every message has ~4 tokens of overhead
            
            # Add tokens for tool calls if present
            if "tool_calls" in message:
                for tool_call in message["tool_calls"]:
                    total_tokens += len(encoding.encode(tool_call.get("function", {}).get("name", "")))
                    total_tokens += len(encoding.encode(tool_call.get("function", {}).get("arguments", "")))
                    total_tokens += 4  # Tool call overhead
        
        return total_tokens
    
    def should_summarize(self, messages: List[Dict[str, str]]) -> bool:
        """Check if conversation should be summarized based on context threshold."""
        current_tokens = self.count_tokens(messages)
        context_window_size = self._get_context_window_size()
        threshold_tokens = int(context_window_size * self.config.context_threshold)
        
        logger.debug(f"Context check: {current_tokens}/{context_window_size} tokens ({current_tokens/context_window_size:.2%})")
        return current_tokens >= threshold_tokens
    
    def get_context_usage_percentage(self, messages: List[Dict[str, str]], system_prompts: List[str] = None) -> float:
        """Get the percentage of context window used by the messages and system prompts."""
        if not messages and not system_prompts:
            return 0.0
        
        # Count tokens in messages
        message_tokens = self.count_tokens(messages) if messages else 0
        
        # Count tokens in system prompts
        system_tokens = 0
        if system_prompts:
            for prompt in system_prompts:
                encoding = self._get_encoding()
                system_tokens += len(encoding.encode(prompt))
                system_tokens += 4  # Message overhead
        
        total_tokens = message_tokens + system_tokens
        context_window_size = self._get_context_window_size()
        return (total_tokens / context_window_size) * 100
    
    def append_context_usage_to_message(self, base_message: str, messages: List[Dict[str, str]], system_prompts: List[str] = None) -> str:
        """Append context usage percentage to an existing temporary message."""
        usage_percentage = self.get_context_usage_percentage(messages, system_prompts)
        return f"{base_message} {usage_percentage:.1f}% context"
    
    def create_summarization_message(self) -> str:
        """Create a temporary message notifying about summarization."""
        return "Summarizing conversation to manage context..."
    
    def summarize_conversation(
        self, 
        messages: List[Dict[str, str]], 
        exclude_tool_calls: bool = True
    ) -> str:
        """Summarize conversation history, excluding tool calls if requested."""
        # Filter out tool calls if requested
        filtered_messages = []
        for message in messages:
            if exclude_tool_calls and message.get("role") in ["tool", "tool_request", "tool_response"]:
                continue
            filtered_messages.append(message)
        
        if not filtered_messages:
            return "No conversation history to summarize."
        
        # Create a prompt for summarization
        conversation_text = ""
        for message in filtered_messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            if content:
                conversation_text += f"{role}: {content}\n"
        
        summary_prompt = f"""Please summarize the following conversation in a concise way, preserving key information and context. The summary should be no more than {self.config.summary_max_tokens} tokens.

Conversation:
{conversation_text}

Summary:"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": "You are a helpful assistant that creates concise summaries of conversations."},
                    {"role": "user", "content": summary_prompt}
                ],
                max_tokens=self.config.summary_max_tokens,
                temperature=0.3  # Lower temperature for more consistent summaries
            )
            
            summary = response.choices[0].message.content
            logger.info(f"Generated conversation summary ({len(summary)} chars)")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to generate conversation summary: {e}")
            return "Failed to generate summary due to an error."
    
    def create_summary_message(self, summary: str) -> Dict[str, str]:
        """Create a summary message for storage in the database."""
        return {
            "role": "summary",
            "content": summary
        }
    
    def reconstruct_history_with_summary(
        self, 
        db: Session, 
        conversation_id: int
    ) -> List[Dict[str, str]]:
        """Reconstruct conversation history with summaries for context management."""
        # Get all messages for the conversation
        messages = db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(Message.created_at.asc()).all()
        
        if not messages:
            return []
        
        # Find the latest summary
        latest_summary = None
        latest_summary_index = -1
        
        for i, message in enumerate(messages):
            if message.role == "summary":
                latest_summary = message
                latest_summary_index = i
        
        # If no summary exists, return all messages
        if latest_summary is None:
            return self._format_messages_for_llm(messages)
        
        # Get messages from the beginning up to the summary (preserving all initial context)
        messages_before_summary = messages[:latest_summary_index]
        
        # Get messages after the latest summary
        messages_after_summary = messages[latest_summary_index + 1:]
        
        # Reconstruct history: all initial messages + summary + messages after summary
        reconstructed = []
        
        # Add all messages from the beginning (preserving system messages, etc.)
        formatted_initial_messages = self._format_messages_for_llm(messages_before_summary)
        reconstructed.extend(formatted_initial_messages)
        
        # Add the summary as a system message
        if latest_summary:
            reconstructed.append({
                "role": "system",
                "content": f"Previous conversation summary: {latest_summary.content}"
            })
        
        # Add messages after the summary using the existing formatting logic
        formatted_messages_after_summary = self._format_messages_for_llm(messages_after_summary)
        reconstructed.extend(formatted_messages_after_summary)
        
        return reconstructed
    
    def _format_messages_for_llm(self, messages: List[Message]) -> List[Dict[str, str]]:
        """Format database messages for LLM consumption with tool call optimization."""
        formatted = []
        
        # Track tool calls to optimize - keep only the latest successful tool call
        tool_calls_by_id = {}  # tool_call_id -> (request_message, response_message)
        latest_successful_tool_call_id = None
        
        # First pass: collect all tool calls and find the latest successful one
        for message in messages:
            if message.role == "tool_request":
                tool_call_id = message.message_metadata.get("tool_call_id", "")
                if tool_call_id:
                    tool_calls_by_id[tool_call_id] = (message, None)
            elif message.role == "tool_response":
                tool_call_id = message.message_metadata.get("tool_call_id", "")
                success = message.message_metadata.get("success", False)
                if tool_call_id and tool_call_id in tool_calls_by_id:
                    tool_calls_by_id[tool_call_id] = (tool_calls_by_id[tool_call_id][0], message)
                    if success:
                        latest_successful_tool_call_id = tool_call_id
        
        # Second pass: format messages with optimization
        for message in messages:
            if message.role in ["user", "assistant", "system"]:
                formatted.append({
                    "role": message.role,
                    "content": message.content
                })
            elif message.role == "tool_request":
                tool_call_id = message.message_metadata.get("tool_call_id", "")
                # Only include if it's the latest successful tool call or if there are no successful tool calls
                if (latest_successful_tool_call_id and tool_call_id == latest_successful_tool_call_id) or \
                   (not latest_successful_tool_call_id and tool_call_id in tool_calls_by_id):
                    tool_name = message.message_metadata.get("tool_name", "unknown")
                    tool_arguments = message.message_metadata.get("tool_arguments", "{}")
                    
                    formatted.append({
                        "role": "assistant",
                        "content": message.content,
                        "tool_calls": [{
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": tool_arguments
                            }
                        }]
                    })
            elif message.role == "tool_response":
                tool_call_id = message.message_metadata.get("tool_call_id", "")
                # Only include if it's the latest successful tool call or if there are no successful tool calls
                if (latest_successful_tool_call_id and tool_call_id == latest_successful_tool_call_id) or \
                   (not latest_successful_tool_call_id and tool_call_id in tool_calls_by_id):
                    formatted.append({
                        "role": "tool",
                        "content": message.content,
                        "tool_call_id": tool_call_id
                    })
        
        return formatted

    def store_summary(self, db: Session, conversation_id: int, summary: str) -> Message:
        """Store a conversation summary in the database."""
        summary_message = Message(
            conversation_id=conversation_id,
            role="summary",
            content=summary,
            message_metadata={"type": "conversation_summary"}
        )
        db.add(summary_message)
        db.commit()
        db.refresh(summary_message)
        return summary_message
