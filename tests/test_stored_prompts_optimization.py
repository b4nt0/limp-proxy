"""
Tests for stored prompts optimization functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from limp.config import LLMConfig, StoredToolPromptConfig
from limp.api.im import get_optimized_tools


class TestStoredPromptsOptimization:
    """Test stored prompts optimization."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = Mock()
        self.config.llm = Mock()
        self.config.llm.stored_tools_prompts = [
            StoredToolPromptConfig(external_system_name="test-system", prompt_id="tool_prompt_123")
        ]
        
        self.tools_service = Mock()
        self.llm_service = Mock()
        
        # Mock the get_stored_tools_prompt method to return mock tools
        self.llm_service.get_stored_tools_prompt.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "stored_tool_from_tool_prompt_123",
                    "description": "Tool retrieved from stored prompt tool_prompt_123",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "param1": {"type": "string", "description": "Parameter from stored prompt"}
                        }
                    }
                }
            }
        ]
    
    def test_optimization_with_stored_tools_prompt(self):
        """Test that stored tool prompts are used instead of OpenAPI conversion."""
        system_configs = [
            {"name": "test-system", "openapi_spec": "https://example.com/api.json"}
        ]
        
        # Call the optimized function
        tools = get_optimized_tools(system_configs, self.config, self.tools_service, self.llm_service)
        
        # Verify that stored tools were retrieved
        self.llm_service.get_stored_tools_prompt.assert_called_once_with("tool_prompt_123")
        
        # Verify that OpenAPI conversion was NOT called (this is the optimization!)
        self.tools_service.get_cleaned_tools_for_openai.assert_not_called()
        
        # Verify that we got the stored tools
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "stored_tool_from_tool_prompt_123"
    
    def test_fallback_to_openapi_when_stored_prompt_fails(self):
        """Test that system falls back to OpenAPI conversion when stored prompt fails."""
        # Mock stored prompt failure
        self.llm_service.get_stored_tools_prompt.return_value = []
        
        # Mock OpenAPI conversion
        self.tools_service.get_cleaned_tools_for_openai.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "openapi_tool",
                    "description": "Tool from OpenAPI conversion"
                }
            }
        ]
        
        system_configs = [
            {"name": "test-system", "openapi_spec": "https://example.com/api.json"}
        ]
        
        # Call the optimized function
        tools = get_optimized_tools(system_configs, self.config, self.tools_service, self.llm_service)
        
        # Verify that stored tools were attempted
        self.llm_service.get_stored_tools_prompt.assert_called_once_with("tool_prompt_123")
        
        # Verify that OpenAPI conversion was called as fallback
        self.tools_service.get_cleaned_tools_for_openai.assert_called_once_with([{"name": "test-system", "openapi_spec": "https://example.com/api.json"}])
        
        # Verify that we got the OpenAPI tools
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "openapi_tool"
    
    def test_no_optimization_without_stored_tools_prompt(self):
        """Test that OpenAPI conversion is used when no stored tool prompt is available."""
        # Remove stored tool prompts
        self.config.llm.stored_tools_prompts = []
        
        # Mock OpenAPI conversion
        self.tools_service.get_cleaned_tools_for_openai.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "openapi_tool",
                    "description": "Tool from OpenAPI conversion"
                }
            }
        ]
        
        system_configs = [
            {"name": "test-system", "openapi_spec": "https://example.com/api.json"}
        ]
        
        # Call the optimized function
        tools = get_optimized_tools(system_configs, self.config, self.tools_service, self.llm_service)
        
        # Verify that stored tools were NOT attempted
        self.llm_service.get_stored_tools_prompt.assert_not_called()
        
        # Verify that OpenAPI conversion was called
        self.tools_service.get_cleaned_tools_for_openai.assert_called_once_with([{"name": "test-system", "openapi_spec": "https://example.com/api.json"}])
        
        # Verify that we got the OpenAPI tools
        assert len(tools) == 1
        assert tools[0]["function"]["name"] == "openapi_tool"
    
    def test_mixed_systems_with_and_without_stored_prompts(self):
        """Test optimization with mixed systems - some with stored prompts, some without."""
        # Add another system without stored prompt
        self.config.llm.stored_tools_prompts = [
            StoredToolPromptConfig(external_system_name="test-system", prompt_id="tool_prompt_123")
        ]
        
        # Mock OpenAPI conversion for the system without stored prompt
        self.tools_service.get_cleaned_tools_for_openai.return_value = [
            {
                "type": "function",
                "function": {
                    "name": "openapi_tool",
                    "description": "Tool from OpenAPI conversion"
                }
            }
        ]
        
        system_configs = [
            {"name": "test-system", "openapi_spec": "https://example.com/api.json"},
            {"name": "other-system", "openapi_spec": "https://other.com/api.json"}
        ]
        
        # Call the optimized function
        tools = get_optimized_tools(system_configs, self.config, self.tools_service, self.llm_service)
        
        # Verify that stored tools were attempted for test-system
        self.llm_service.get_stored_tools_prompt.assert_called_once_with("tool_prompt_123")
        
        # Verify that OpenAPI conversion was called for other-system
        self.tools_service.get_cleaned_tools_for_openai.assert_called_once_with([{"name": "other-system", "openapi_spec": "https://other.com/api.json"}])
        
        # Verify that we got tools from both sources
        assert len(tools) == 2
        assert tools[0]["function"]["name"] == "stored_tool_from_tool_prompt_123"
        assert tools[1]["function"]["name"] == "openapi_tool"
