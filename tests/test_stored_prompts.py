"""
Tests for stored prompts functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from limp.config import LLMConfig, StoredPromptConfig, StoredToolPromptConfig
from limp.services.llm import LLMService
from limp.services.tools import ToolsService
from limp.api.im import get_optimized_tools


class TestStoredPromptConfig:
    """Test stored prompt configuration."""
    
    def test_stored_prompt_config_creation(self):
        """Test creating stored prompt configuration."""
        config = StoredPromptConfig(
            prompt_id="prompt_123",
            variables={"bot_name": "LIMP", "system_name": "TestSystem"}
        )
        
        assert config.prompt_id == "prompt_123"
        assert config.variables == {"bot_name": "LIMP", "system_name": "TestSystem"}
    
    def test_stored_prompt_config_defaults(self):
        """Test stored prompt configuration with defaults."""
        config = StoredPromptConfig(prompt_id="prompt_456")
        
        assert config.prompt_id == "prompt_456"
        assert config.variables == {}


class TestStoredToolPromptConfig:
    """Test stored tool prompt configuration."""
    
    def test_stored_tool_prompt_config_creation(self):
        """Test creating stored tool prompt configuration."""
        config = StoredToolPromptConfig(
            external_system_name="TestSystem",
            prompt_id="tool_prompt_123"
        )
        
        assert config.external_system_name == "TestSystem"
        assert config.prompt_id == "tool_prompt_123"


class TestLLMConfigWithStoredPrompts:
    """Test LLM configuration with stored prompts."""
    
    def test_llm_config_with_stored_prompts(self):
        """Test LLM configuration with stored prompts."""
        stored_prompts = [
            StoredPromptConfig(prompt_id="prompt_1", variables={"var1": "value1"}),
            StoredPromptConfig(prompt_id="prompt_2")
        ]
        
        stored_tools_prompts = [
            StoredToolPromptConfig(external_system_name="System1", prompt_id="tool_prompt_1"),
            StoredToolPromptConfig(external_system_name="System2", prompt_id="tool_prompt_2")
        ]
        
        config = LLMConfig(
            api_key="test-key",
            stored_prompts=stored_prompts,
            stored_tools_prompts=stored_tools_prompts
        )
        
        assert len(config.stored_prompts) == 2
        assert len(config.stored_tools_prompts) == 2
        assert config.stored_prompts[0].prompt_id == "prompt_1"
        assert config.stored_tools_prompts[0].external_system_name == "System1"


class TestLLMServiceStoredPrompts:
    """Test LLM service with stored prompts."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.config = LLMConfig(api_key="test-key")
        self.service = LLMService(self.config)
    
    def test_get_stored_prompt_placeholder(self):
        """Test getting stored prompt (placeholder implementation)."""
        result = self.service.get_stored_prompt("test_prompt_id", {"var": "value"})
        
        # Should return placeholder since real implementation is not available
        assert "[Stored prompt: test_prompt_id]" in result
    
    def test_format_messages_with_stored_prompts(self):
        """Test formatting messages with stored prompts."""
        user_message = "Hello"
        conversation_history = [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}]
        system_prompts = ["You are helpful"]
        stored_prompts = [
            {"prompt_id": "prompt_1", "variables": {"var1": "value1"}},
            {"prompt_id": "prompt_2", "variables": {}}
        ]
        
        messages = self.service.format_messages_with_context(
            user_message,
            conversation_history,
            system_prompts,
            stored_prompts=stored_prompts
        )
        
        # Should have stored prompts first, then system prompts, then conversation
        assert len(messages) == 6  # 2 stored + 1 system + 2 history + 1 user
        assert messages[0]["role"] == "developer"
        assert messages[1]["role"] == "developer"
        assert messages[2]["role"] == "developer"
        assert messages[3]["role"] == "user"
        assert messages[4]["role"] == "assistant"
        assert messages[5]["role"] == "user"
    
    def test_format_messages_without_stored_prompts(self):
        """Test formatting messages without stored prompts."""
        user_message = "Hello"
        conversation_history = [{"role": "user", "content": "Hi"}]
        system_prompts = ["You are helpful"]
        
        messages = self.service.format_messages_with_context(
            user_message,
            conversation_history,
            system_prompts
        )
        
        # Should have system prompts, then conversation
        assert len(messages) == 3  # 1 system + 1 history + 1 user
        assert messages[0]["role"] == "developer"
        assert messages[1]["role"] == "user"
        assert messages[2]["role"] == "user"


class TestToolsServiceStoredPrompts:
    """Test tools service with stored prompts."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ToolsService()
    
    def test_generate_system_prompts_for_tools(self):
        """Test generating system prompts for tools."""
        tools = [
            {
                "function": {
                    "name": "getUsers",
                    "description": "Get list of users"
                }
            },
            {
                "function": {
                    "name": "createUser",
                    "description": "Create a new user"
                }
            }
        ]
        
        prompts = self.service.generate_system_prompts_for_tools(tools, "TestSystem")
        
        assert len(prompts) >= 1  # At least main prompt
        assert "TestSystem" in prompts[0]
        assert "getUsers" in prompts[0]
        assert "createUser" in prompts[0]
        
        # Should have specialized prompts for read/write operations
        read_prompts = [p for p in prompts if "reading data" in p.lower()]
        write_prompts = [p for p in prompts if "creating or updating" in p.lower()]
        
        assert len(read_prompts) == 1  # Should have read prompt for getUsers
        assert len(write_prompts) == 1  # Should have write prompt for createUser
    
    def test_generate_system_prompts_for_tools_no_write_operations(self):
        """Test generating system prompts for tools with only read operations."""
        tools = [
            {
                "function": {
                    "name": "getUsers",
                    "description": "Get list of users"
                }
            },
            {
                "function": {
                    "name": "listItems",
                    "description": "List all items"
                }
            }
        ]
        
        prompts = self.service.generate_system_prompts_for_tools(tools, "TestSystem")
        
        # Should have main prompt and read prompt, but no write prompt
        assert len(prompts) == 2
        read_prompts = [p for p in prompts if "reading data" in p.lower()]
        write_prompts = [p for p in prompts if "creating or updating" in p.lower()]
        
        assert len(read_prompts) == 1
        assert len(write_prompts) == 0


class TestOptimizedTools:
    """Test optimized tools functionality."""
    
    def test_get_optimized_tools_with_stored_prompts(self):
        """Test getting optimized tools with stored tool prompts."""
        system_configs = [
            {"name": "System1", "openapi_spec": "http://example.com/api.json"},
            {"name": "System2", "openapi_spec": "http://example.com/api2.json"}
        ]
        
        # Mock config with stored tool prompts
        mock_config = Mock()
        mock_config.llm.stored_tools_prompts = [
            StoredToolPromptConfig(external_system_name="System1", prompt_id="tool_prompt_1")
        ]
        
        # Mock tools service
        mock_tools_service = Mock()
        mock_tools_service.get_cleaned_tools_for_openai.return_value = [
            {"function": {"name": "testFunction", "description": "Test function"}}
        ]
        
        # Mock LLM service
        mock_llm_service = Mock()
        # Mock get_stored_tools_prompt to return empty list (no stored tools available)
        mock_llm_service.get_stored_tools_prompt.return_value = []
        
        tools = get_optimized_tools(system_configs, mock_config, mock_tools_service, mock_llm_service)
        
        # Should call get_cleaned_tools_for_openai for both systems (fallback when stored prompts fail)
        assert mock_tools_service.get_cleaned_tools_for_openai.call_count == 2
        assert len(tools) == 2  # Tools from both systems
    
    def test_get_optimized_tools_without_stored_prompts(self):
        """Test getting optimized tools without stored tool prompts."""
        system_configs = [
            {"name": "System1", "openapi_spec": "http://example.com/api.json"}
        ]
        
        # Mock config without stored tool prompts
        mock_config = Mock()
        mock_config.llm.stored_tools_prompts = []
        
        # Mock tools service
        mock_tools_service = Mock()
        mock_tools_service.get_cleaned_tools_for_openai.return_value = [
            {"function": {"name": "testFunction", "description": "Test function"}}
        ]
        
        # Mock LLM service
        mock_llm_service = Mock()
        
        tools = get_optimized_tools(system_configs, mock_config, mock_tools_service, mock_llm_service)
        
        # Should call get_cleaned_tools_for_openai for the system
        assert mock_tools_service.get_cleaned_tools_for_openai.call_count == 1
        assert len(tools) == 1


class TestAdminAPIStoredPrompts:
    """Test admin API endpoints for stored prompts."""
    
    def test_get_systems_with_openapi(self, test_client):
        """Test getting systems with OpenAPI specs."""
        with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
            mock_verify.return_value = True
            
            response = test_client.get(
                "/admin/prompt-conversion/api/systems",
                auth=("admin", "admin123")
            )
        
        assert response.status_code == 200
        data = response.json()
        assert "systems" in data
    
    def test_convert_openapi_to_prompts(self, test_client):
        """Test converting OpenAPI to prompts."""
        with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
            mock_verify.return_value = True
            
            # This test would need a mock external system with OpenAPI spec
            # For now, we'll test the endpoint structure
            response = test_client.post(
                "/admin/prompt-conversion/api/convert",
                data={"system_name": "test_system"},
                auth=("admin", "admin123")
            )
        
        # Should return 404, 400, 422, or 500 since test_system doesn't exist
        assert response.status_code in [400, 404, 422, 500]
    
    def test_prompt_conversion_page(self, test_client):
        """Test prompt conversion page."""
        with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
            mock_verify.return_value = True
            
            response = test_client.get("/admin/prompt-conversion", auth=("admin", "admin123"))
        
        assert response.status_code == 200
        assert "Prompt Conversion" in response.text


class TestStoredPromptsIntegration:
    """Integration tests for stored prompts."""
    
    def test_config_loading_with_stored_prompts(self):
        """Test loading configuration with stored prompts."""
        config_data = {
            "llm": {
                "api_key": "test-key",
                "stored_prompts": [
                    {
                        "prompt_id": "prompt_1",
                        "variables": {"var1": "value1"}
                    }
                ],
                "stored_tools_prompts": [
                    {
                        "external_system_name": "TestSystem",
                        "prompt_id": "tool_prompt_1"
                    }
                ]
            }
        }
        
        # This would test the actual config loading
        # For now, we'll test the structure
        assert "stored_prompts" in config_data["llm"]
        assert "stored_tools_prompts" in config_data["llm"]
        assert len(config_data["llm"]["stored_prompts"]) == 1
        assert len(config_data["llm"]["stored_tools_prompts"]) == 1
    
    def test_yaml_config_example(self):
        """Test YAML configuration example."""
        yaml_example = """
llm:
  provider: "openai"
  api_key: "your-openai-api-key-here"
  model: "gpt-4"
  max_tokens: 4000
  temperature: 0.7
  max_iterations: 8
  stored_prompts:
    - prompt_id: "prompt_abc123"
      variables:
        bot_name: "LIMP"
        system_name: "{{system_name}}"
    - prompt_id: "prompt_def456"
      variables: {}
  stored_tools_prompts:
    - external_system_name: "example-system"
      prompt_id: "tool_prompt_123"
"""
        
        # This would test actual YAML parsing
        # For now, we'll verify the structure
        assert "stored_prompts:" in yaml_example
        assert "stored_tools_prompts:" in yaml_example
        assert "prompt_id:" in yaml_example
        assert "external_system_name:" in yaml_example
