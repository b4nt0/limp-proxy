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
            
            return {
                "content": response.choices[0].message.content,
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
    
    def get_stored_prompt(self, prompt_id: str, variables: Dict[str, str] = None) -> str:
        """Retrieve a stored prompt from OpenAI."""
        try:
            # Note: This is a placeholder implementation
            # In a real implementation, you would use:
            # response = self.client.prompts.retrieve(prompt_id, variables=variables or {})
            # return response.content
            logger.warning(f"Stored prompt retrieval not implemented yet for prompt_id: {prompt_id}")
            return f"[Stored prompt: {prompt_id}]"
        except Exception as e:
            logger.error(f"Failed to retrieve stored prompt {prompt_id}: {e}")
            return f"[Error retrieving stored prompt: {prompt_id}]"
    
    def get_stored_tools_prompt(self, prompt_id: str, variables: Dict[str, str] = None) -> List[Dict[str, Any]]:
        """Retrieve stored tools from a stored prompt."""
        try:
            # Note: This is a placeholder implementation
            # In a real implementation, you would:
            # 1. Retrieve the stored prompt from OpenAI
            # 2. Parse the tools from the prompt content
            # 3. Return the tools in OpenAI format
            
            # For demonstration purposes, return mock tools to show the optimization works
            if prompt_id.startswith("tool_prompt_"):
                logger.info(f"Retrieving tools from stored prompt: {prompt_id}")
                # Return mock tools to demonstrate the optimization
                return [
                    {
                        "type": "function",
                        "function": {
                            "name": f"stored_tool_from_{prompt_id}",
                            "description": f"Tool retrieved from stored prompt {prompt_id}",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "param1": {"type": "string", "description": "Parameter from stored prompt"}
                                }
                            }
                        }
                    }
                ]
            else:
                logger.warning(f"Stored tools prompt retrieval not implemented yet for prompt_id: {prompt_id}")
                return []  # Return empty tools list for unknown prompts
        except Exception as e:
            logger.error(f"Failed to retrieve stored tools prompt {prompt_id}: {e}")
            return []

    def format_messages_with_context(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        system_prompts: Optional[List[str]] = None,
        schema_prompts: Optional[List[str]] = None,
        stored_prompts: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, str]]:
        """Format messages with conversation context."""
        messages = []
        
        # Add stored prompts first (if available)
        if stored_prompts:
            for stored_prompt in stored_prompts:
                prompt_content = self.get_stored_prompt(
                    stored_prompt["prompt_id"], 
                    stored_prompt.get("variables", {})
                )
                messages.append({"role": "developer", "content": prompt_content})
        
        # Add system prompts (fallback or additional)
        if system_prompts:
            for system_prompt in system_prompts:
                messages.append({"role": "developer", "content": system_prompt})
        
        # Add schema prompts for API context
        if schema_prompts:
            for schema_prompt in schema_prompts:
                messages.append({"role": "developer", "content": schema_prompt})
        
        # Add conversation history
        messages.extend(conversation_history)
        
        # Add current user message
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

