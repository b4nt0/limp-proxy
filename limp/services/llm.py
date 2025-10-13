"""
LLM service for OpenAI integration.
"""

import openai
from typing import List, Dict, Any, Optional
import logging

from ..config import LLMConfig

logger = logging.getLogger(__name__)


class LLMService:
    """LLM service for OpenAI ChatGPT integration."""
    
    def __init__(self, config: LLMConfig):
        self.config = config
        self.client = openai.OpenAI(
            api_key=config.api_key,
            base_url=config.base_url
        )
    
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """Send chat completion request to LLM."""
        try:
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "stream": stream,
            }

            if self.config.model.startswith("gpt-5"):
                kwargs["max_completion_tokens"] = self.config.max_tokens
            else:
                kwargs["max_tokens"] = self.config.max_tokens
                kwargs["temperature"] = self.config.temperature
            
            if tools:
                kwargs["tools"] = tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice
            
            if stream:
                return self._handle_streaming_response(kwargs)
            else:
                return self._handle_non_streaming_response(kwargs)
                
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise
    
    def _handle_non_streaming_response(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Handle non-streaming response."""
        response = self.client.chat.completions.create(**kwargs)
        
        # Check if response was truncated due to length limits
        if response.choices[0].finish_reason == 'length':
            content = response.choices[0].message.content or ""
            # When finish_reason is 'length', the content is often empty or minimal
            if content.strip():
                # If we have some content, try to end it gracefully
                if not content.rstrip().endswith(('.', '!', '?', ':', ';')):
                    content = content.rstrip() + "..."
                truncated_message = "\n\n[Response was truncated due to length limits. The response was too long to fit within the token limit. Consider asking for a shorter response or breaking your question into smaller parts.]"
                content += truncated_message
            else:
                # No content available - this is the common case with length truncation
                content = "[Response was truncated due to length limits. The response was too long to fit within the token limit. Consider asking for a shorter response or breaking your question into smaller parts.]"
        else:
            content = response.choices[0].message.content
        
        return {
            "content": content,
            "tool_calls": response.choices[0].message.tool_calls,
            "finish_reason": response.choices[0].finish_reason,
            "usage": {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens
            }
        }
    
    def _handle_streaming_response(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Handle streaming response to avoid truncation."""
        collected_content = []
        tool_calls = []
        finish_reason = None
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        try:
            stream = self.client.chat.completions.create(**kwargs)
            
            for chunk in stream:
                if chunk.choices:
                    choice = chunk.choices[0]
                    
                    # Collect content
                    if hasattr(choice.delta, 'content') and choice.delta.content:
                        collected_content.append(choice.delta.content)
                    
                    # Collect tool calls
                    if hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                        for tool_call in choice.delta.tool_calls:
                            if tool_call.index < len(tool_calls):
                                # Continue existing tool call
                                if tool_call.function:
                                    if tool_call.function.name:
                                        tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                                    if tool_call.function.arguments:
                                        tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                            else:
                                # Start new tool call
                                tool_calls.append({
                                    "id": tool_call.id,
                                    "type": tool_call.type,
                                    "function": {
                                        "name": tool_call.function.name or "",
                                        "arguments": tool_call.function.arguments or ""
                                    }
                                })
                    
                    # Track finish reason
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                
                # Track usage if available
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens
                    }
            
            content = "".join(collected_content)
            
            # Handle truncation in streaming
            if finish_reason == 'length':
                if content.strip():
                    if not content.rstrip().endswith(('.', '!', '?', ':', ';')):
                        content = content.rstrip() + "..."
                    content += "\n\n[Response was truncated due to length limits. The response was too long to fit within the token limit.]"
                else:
                    content = "[Response was truncated due to length limits. The response was too long to fit within the token limit.]"
            
            return {
                "content": content,
                "tool_calls": tool_calls if tool_calls else None,
                "finish_reason": finish_reason,
                "usage": usage
            }
            
        except Exception as e:
            logger.error(f"Streaming response failed: {e}")
            # Fallback to non-streaming
            kwargs["stream"] = False
            return self._handle_non_streaming_response(kwargs)
    
    def format_messages_with_context(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        system_prompts: Optional[List[str]] = None,
        schema_prompts: Optional[List[str]] = None
    ) -> List[Dict[str, str]]:
        """Format messages with conversation context."""
        messages = []
        
        # Add system prompts first
        if system_prompts:
            for system_prompt in system_prompts:
                messages.append({"role": "system", "content": system_prompt})
        
        # Add schema prompts for API context
        if schema_prompts:
            for schema_prompt in schema_prompts:
                messages.append({"role": "system", "content": schema_prompt})
        
        # Add conversation history
        messages.extend(conversation_history)
        
        # Add current user message if provided and not empty
        if user_message:
            messages.append({"role": "user", "content": user_message})
        
        return messages
    
    def extract_tool_calls(self, response: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract tool calls from LLM response."""
        tool_calls = response.get("tool_calls", [])
        if not tool_calls:
            return []
        
        return [
            {
                "id": tool_call.id,
                "type": tool_call.type,
                "function": {
                    "name": tool_call.function.name,
                    "arguments": tool_call.function.arguments
                }
            }
            for tool_call in tool_calls
        ]
    
    def is_tool_call_response(self, response: Dict[str, Any]) -> bool:
        """Check if response contains tool calls."""
        return bool(response.get("tool_calls"))
    
    def continue_truncated_response(
        self,
        messages: List[Dict[str, str]],
        truncated_content: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        use_streaming: bool = True
    ) -> Dict[str, Any]:
        """Continue a truncated response by asking the LLM to continue from where it left off."""
        try:
            # Create a continuation message
            continuation_messages = messages.copy()
            continuation_messages.append({
                "role": "user", 
                "content": f"Please continue your previous response from where you left off. Your previous response was: '{truncated_content}'"
            })
            
            # Use streaming to avoid truncation in continuation
            return self.chat_completion(continuation_messages, tools, stream=use_streaming)
        except Exception as e:
            logger.error(f"Failed to continue truncated response: {e}")
            raise
    
    def summarize_truncated_response(
        self,
        messages: List[Dict[str, str]],
        truncated_content: str,
        tools: Optional[List[Dict[str, Any]]] = None,
        use_streaming: bool = True
    ) -> Dict[str, Any]:
        """Create a summary of a truncated response to fit within token limits."""
        try:
            # Create a summarization request
            summary_messages = messages.copy()
            summary_messages.append({
                "role": "user", 
                "content": f"Please provide a concise summary of the following response that was truncated due to length limits: '{truncated_content}'. Focus on the key points and main conclusions."
            })
            
            # Use streaming to avoid truncation in summary
            return self.chat_completion(summary_messages, tools, stream=use_streaming)
        except Exception as e:
            logger.error(f"Failed to summarize truncated response: {e}")
            raise
    
    def get_truncated_response_metadata(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata about a truncated response for recovery options."""
        if response.get("finish_reason") != "length":
            return {}
        
        content = response.get("content", "")
        usage = response.get("usage", {})
        
        return {
            "is_truncated": True,
            "content_length": len(content),
            "tokens_used": usage.get("completion_tokens", 0),
            "max_tokens": self.config.max_tokens,
            "recovery_options": [
                "continue",
                "summarize", 
                "retry_with_streaming"
            ]
        }
    
    def stream_chat_completion(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """Stream chat completion with optional callback for real-time updates."""
        try:
            kwargs = {
                "model": self.config.model,
                "messages": messages,
                "stream": True,
            }

            if self.config.model.startswith("gpt-5"):
                kwargs["max_completion_tokens"] = self.config.max_tokens
            else:
                kwargs["max_tokens"] = self.config.max_tokens
                kwargs["temperature"] = self.config.temperature
            
            if tools:
                kwargs["tools"] = tools
                if tool_choice:
                    kwargs["tool_choice"] = tool_choice
            
            collected_content = []
            tool_calls = []
            finish_reason = None
            usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
            
            stream = self.client.chat.completions.create(**kwargs)
            
            for chunk in stream:
                if chunk.choices:
                    choice = chunk.choices[0]
                    
                    # Collect content
                    if hasattr(choice.delta, 'content') and choice.delta.content:
                        collected_content.append(choice.delta.content)
                        
                        # Call callback with incremental content if provided
                        if callback:
                            callback(choice.delta.content)
                    
                    # Collect tool calls
                    if hasattr(choice.delta, 'tool_calls') and choice.delta.tool_calls:
                        for tool_call in choice.delta.tool_calls:
                            if tool_call.index < len(tool_calls):
                                # Continue existing tool call
                                if tool_call.function:
                                    if tool_call.function.name:
                                        tool_calls[tool_call.index]["function"]["name"] = tool_call.function.name
                                    if tool_call.function.arguments:
                                        tool_calls[tool_call.index]["function"]["arguments"] += tool_call.function.arguments
                            else:
                                # Start new tool call
                                tool_calls.append({
                                    "id": tool_call.id,
                                    "type": tool_call.type,
                                    "function": {
                                        "name": tool_call.function.name or "",
                                        "arguments": tool_call.function.arguments or ""
                                    }
                                })
                    
                    # Track finish reason
                    if choice.finish_reason:
                        finish_reason = choice.finish_reason
                
                # Track usage if available
                if hasattr(chunk, 'usage') and chunk.usage:
                    usage = {
                        "prompt_tokens": chunk.usage.prompt_tokens,
                        "completion_tokens": chunk.usage.completion_tokens,
                        "total_tokens": chunk.usage.total_tokens
                    }
            
            content = "".join(collected_content)
            
            # Handle truncation in streaming
            if finish_reason == 'length':
                if content.strip():
                    if not content.rstrip().endswith(('.', '!', '?', ':', ';')):
                        content = content.rstrip() + "..."
                    content += "\n\n[Response was truncated due to length limits. The response was too long to fit within the token limit.]"
                else:
                    content = "[Response was truncated due to length limits. The response was too long to fit within the token limit.]"
            
            return {
                "content": content,
                "tool_calls": tool_calls if tool_calls else None,
                "finish_reason": finish_reason,
                "usage": usage
            }
            
        except Exception as e:
            logger.error(f"Streaming chat completion failed: {e}")
            raise
    
    def get_error_message(self, error: Exception) -> str:
        """Get user-friendly error message for LLM errors."""
        if "rate_limit" in str(error).lower():
            return "The AI service is currently busy. Please try again in a moment."
        elif "authentication" in str(error).lower():
            return "There was an authentication issue with the AI service."
        elif "quota" in str(error).lower():
            return "The AI service quota has been exceeded. Please contact support."
        else:
            return "There was an issue communicating with the AI service. Please try again."

