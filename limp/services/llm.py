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
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send chat completion request to LLM."""
        try:
            kwargs = {
                "model": self.config.model,
                "messages": messages,
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
            
            response = self.client.chat.completions.create(**kwargs)
            
            # Check if response was truncated due to length limits
            if response.choices[0].finish_reason == 'length':
                content = response.choices[0].message.content or ""
                truncated_message = "\n\n[Response was truncated due to length limits. The allowed response length was not sufficient to complete the full response.]"
                content += truncated_message
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
        except Exception as e:
            logger.error(f"LLM request failed: {e}")
            raise
    
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

