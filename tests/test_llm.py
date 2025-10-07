"""
Tests for LLM service.
"""

import pytest
import json
import yaml
import tempfile
import os
from unittest.mock import Mock, patch
from openai import OpenAI

from limp.services.llm import LLMService
from limp.services.tools import ToolsService
from limp.config import LLMConfig


def test_llm_service_initialization():
    """Test LLM service initialization."""
    config = LLMConfig(
        api_key="test-key",
        model="gpt-4",
        max_tokens=1000,
        temperature=0.7
    )
    
    service = LLMService(config)
    
    assert service.config.api_key == "test-key"
    assert service.config.model == "gpt-4"
    assert service.config.max_tokens == 1000
    assert service.config.temperature == 0.7


@patch('limp.services.llm.openai.OpenAI')
def test_chat_completion_success(mock_openai):
    """Test successful chat completion."""
    # Mock OpenAI client
    mock_client = Mock()
    mock_openai.return_value = mock_client
    
    # Mock response
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = "Hello, world!"
    mock_response.choices[0].message.tool_calls = None
    mock_response.choices[0].finish_reason = "stop"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 15
    
    mock_client.chat.completions.create.return_value = mock_response
    
    # Create service
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    # Test chat completion
    messages = [{"role": "user", "content": "Hello"}]
    response = service.chat_completion(messages)
    
    # Verify response
    assert response["content"] == "Hello, world!"
    assert response["tool_calls"] is None
    assert response["finish_reason"] == "stop"
    assert response["usage"]["prompt_tokens"] == 10
    assert response["usage"]["completion_tokens"] == 5
    assert response["usage"]["total_tokens"] == 15


@patch('limp.services.llm.openai.OpenAI')
def test_chat_completion_with_tools(mock_openai):
    """Test chat completion with tools."""
    # Mock OpenAI client
    mock_client = Mock()
    mock_openai.return_value = mock_client
    
    # Mock tool call
    mock_tool_call = Mock()
    mock_tool_call.id = "call_123"
    mock_tool_call.type = "function"
    mock_tool_call.function.name = "test_function"
    mock_tool_call.function.arguments = '{"arg1": "value1"}'
    
    # Mock response
    mock_response = Mock()
    mock_response.choices = [Mock()]
    mock_response.choices[0].message.content = None
    mock_response.choices[0].message.tool_calls = [mock_tool_call]
    mock_response.choices[0].finish_reason = "tool_calls"
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 5
    mock_response.usage.total_tokens = 15
    
    mock_client.chat.completions.create.return_value = mock_response
    
    # Create service
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    # Test chat completion with tools
    messages = [{"role": "user", "content": "Hello"}]
    tools = [{"type": "function", "function": {"name": "test_function"}}]
    response = service.chat_completion(messages, tools)
    
    # Verify response
    assert response["content"] is None
    assert len(response["tool_calls"]) == 1
    assert response["tool_calls"][0].id == "call_123"
    assert response["tool_calls"][0].function.name == "test_function"
    assert response["finish_reason"] == "tool_calls"


@patch('limp.services.llm.openai.OpenAI')
def test_chat_completion_error(mock_openai):
    """Test chat completion error handling."""
    # Mock OpenAI client to raise exception
    mock_client = Mock()
    mock_openai.return_value = mock_client
    mock_client.chat.completions.create.side_effect = Exception("API Error")
    
    # Create service
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    # Test chat completion with error
    messages = [{"role": "user", "content": "Hello"}]
    
    with pytest.raises(Exception) as exc_info:
        service.chat_completion(messages)
    
    assert "API Error" in str(exc_info.value)


def test_format_messages_with_context():
    """Test formatting messages with context."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    user_message = "Hello, how are you?"
    conversation_history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help you?"}
    ]
    system_prompts = ["You are a helpful assistant."]
    
    messages = service.format_messages_with_context(
        user_message,
        conversation_history,
        system_prompts
    )
    
    # Verify message structure
    assert len(messages) == 4
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful assistant."
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "Hi"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["content"] == "Hello! How can I help you?"
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "Hello, how are you?"


def test_format_messages_without_system_prompt():
    """Test formatting messages without system prompt."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    user_message = "Hello, how are you?"
    conversation_history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help you?"}
    ]
    
    messages = service.format_messages_with_context(
        user_message,
        conversation_history
    )
    
    # Verify message structure
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hi"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hello! How can I help you?"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Hello, how are you?"


def test_format_messages_with_multiple_system_prompts():
    """Test formatting messages with multiple system prompts."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    user_message = "Hello, how are you?"
    conversation_history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help you?"}
    ]
    system_prompts = [
        "You are a helpful AI assistant.",
        "Always be polite and professional.",
        "If you need to access external systems, ask the user to authorize access first."
    ]
    
    messages = service.format_messages_with_context(
        user_message,
        conversation_history,
        system_prompts
    )
    
    # Verify message structure
    assert len(messages) == 6  # 3 system prompts + 2 history + 1 current
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful AI assistant."
    assert messages[1]["role"] == "system"
    assert messages[1]["content"] == "Always be polite and professional."
    assert messages[2]["role"] == "system"
    assert messages[2]["content"] == "If you need to access external systems, ask the user to authorize access first."
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "Hi"
    assert messages[4]["role"] == "assistant"
    assert messages[4]["content"] == "Hello! How can I help you?"
    assert messages[5]["role"] == "user"
    assert messages[5]["content"] == "Hello, how are you?"


def test_format_messages_with_empty_system_prompts():
    """Test formatting messages with empty system prompts list."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    user_message = "Hello, how are you?"
    conversation_history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help you?"}
    ]
    system_prompts = []
    
    messages = service.format_messages_with_context(
        user_message,
        conversation_history,
        system_prompts
    )
    
    # Verify message structure (no system prompts, no schema prompts)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hi"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hello! How can I help you?"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Hello, how are you?"


def test_format_messages_with_none_system_prompts():
    """Test formatting messages with None system prompts."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    user_message = "Hello, how are you?"
    conversation_history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help you?"}
    ]
    
    messages = service.format_messages_with_context(
        user_message,
        conversation_history,
        None
    )


def test_format_messages_with_schema_prompts():
    """Test formatting messages including schema prompts."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    user_message = "Hello, how are you?"
    conversation_history = [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello! How can I help you?"}
    ]
    system_prompts = ["You are a helpful assistant."]
    schema_prompts = [
        "API Endpoint: getOrganizations\nMethod: GET /api/v1/organizations\nResponse: { data: Organization[] }",
        "API Response Schema: Organization\nSchema structure:\n- id: integer\n- name: string"
    ]
    
    messages = service.format_messages_with_context(
        user_message,
        conversation_history,
        system_prompts,
        schema_prompts=schema_prompts
    )
    
    # Expect: 1 system + 2 schema + 2 history + 1 user = 6
    assert len(messages) == 6
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "You are a helpful assistant."
    assert messages[1]["role"] == "system"
    assert "API Endpoint: getOrganizations" in messages[1]["content"]
    assert messages[2]["role"] == "system"
    assert "API Response Schema: Organization" in messages[2]["content"]
    assert messages[3]["role"] == "user"
    assert messages[3]["content"] == "Hi"
    assert messages[4]["role"] == "assistant"
    assert messages[4]["content"] == "Hello! How can I help you?"
    assert messages[5]["role"] == "user"
    assert messages[5]["content"] == "Hello, how are you?"
    
    # Ensure schema prompts are included as system messages
    assert any(m["role"] == "system" and "API Endpoint:" in m["content"] for m in messages)
    assert any(m["role"] == "system" and "API Response Schema:" in m["content"] for m in messages)


def test_extract_tool_calls():
    """Test extracting tool calls from response."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    # Mock tool call
    mock_tool_call = Mock()
    mock_tool_call.id = "call_123"
    mock_tool_call.type = "function"
    mock_tool_call.function.name = "test_function"
    mock_tool_call.function.arguments = '{"arg1": "value1"}'
    
    response = {
        "tool_calls": [mock_tool_call]
    }
    
    tool_calls = service.extract_tool_calls(response)
    
    # Verify tool calls
    assert len(tool_calls) == 1
    assert tool_calls[0]["id"] == "call_123"
    assert tool_calls[0]["type"] == "function"
    assert tool_calls[0]["function"]["name"] == "test_function"
    assert tool_calls[0]["function"]["arguments"] == '{"arg1": "value1"}'


def test_is_tool_call_response():
    """Test checking if response contains tool calls."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    # Test with tool calls
    response_with_tools = {"tool_calls": [{"id": "call_123"}]}
    assert service.is_tool_call_response(response_with_tools) is True
    
    # Test without tool calls
    response_without_tools = {"content": "Hello, world!"}
    assert service.is_tool_call_response(response_without_tools) is False
    
    # Test with empty tool calls
    response_empty_tools = {"tool_calls": []}
    assert service.is_tool_call_response(response_empty_tools) is False


def test_get_error_message():
    """Test getting user-friendly error messages."""
    config = LLMConfig(api_key="test-key")
    service = LLMService(config)
    
    # Test rate limit error
    rate_limit_error = Exception("rate_limit_exceeded")
    message = service.get_error_message(rate_limit_error)
    assert "busy" in message.lower()
    
    # Test authentication error
    auth_error = Exception("authentication_failed")
    message = service.get_error_message(auth_error)
    assert "authentication" in message.lower()
    
    # Test quota error
    quota_error = Exception("quota_exceeded")
    message = service.get_error_message(quota_error)
    assert "quota" in message.lower()
    
    # Test generic error
    generic_error = Exception("unknown_error")
    message = service.get_error_message(generic_error)
    assert "issue" in message.lower()


# Tests for ToolsService
class TestToolsService:
    """Test suite for ToolsService."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.tools_service = ToolsService()
        
        # Sample OpenAPI spec for testing
        self.sample_spec = {
            "openapi": "3.0.0",
            "info": {
                "title": "Test API",
                "version": "1.0.0"
            },
            "paths": {
                "/users": {
                    "get": {
                        "operationId": "getUsers",
                        "description": "Get all users",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "schema": {"type": "integer"},
                                "description": "Number of users to return"
                            }
                        ]
                    },
                    "post": {
                        "operationId": "createUser",
                        "description": "Create a new user",
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "email": {"type": "string"}
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    
    def test_load_openapi_spec_json_file(self):
        """Test loading OpenAPI spec from JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_spec, f)
            temp_file = f.name
        
        try:
            result = self.tools_service.load_openapi_spec(temp_file)
            assert result == self.sample_spec
            assert result["openapi"] == "3.0.0"
            assert result["info"]["title"] == "Test API"
        finally:
            os.unlink(temp_file)
    
    def test_load_openapi_spec_yaml_file(self):
        """Test loading OpenAPI spec from YAML file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(self.sample_spec, f)
            temp_file = f.name
        
        try:
            result = self.tools_service.load_openapi_spec(temp_file)
            assert result == self.sample_spec
            assert result["openapi"] == "3.0.0"
            assert result["info"]["title"] == "Test API"
        finally:
            os.unlink(temp_file)
    
    def test_load_openapi_spec_yml_file(self):
        """Test loading OpenAPI spec from .yml file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as f:
            yaml.dump(self.sample_spec, f)
            temp_file = f.name
        
        try:
            result = self.tools_service.load_openapi_spec(temp_file)
            assert result == self.sample_spec
            assert result["openapi"] == "3.0.0"
            assert result["info"]["title"] == "Test API"
        finally:
            os.unlink(temp_file)
    
    @patch('requests.get')
    def test_load_openapi_spec_http_json(self, mock_get):
        """Test loading OpenAPI spec from HTTP URL with JSON content."""
        mock_response = Mock()
        mock_response.text = json.dumps(self.sample_spec)
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.tools_service.load_openapi_spec("http://example.com/api.json")
        
        assert result == self.sample_spec
        assert result["openapi"] == "3.0.0"
        assert result["info"]["title"] == "Test API"
        mock_get.assert_called_once_with("http://example.com/api.json")
    
    @patch('requests.get')
    def test_load_openapi_spec_http_yaml(self, mock_get):
        """Test loading OpenAPI spec from HTTP URL with YAML content."""
        mock_response = Mock()
        mock_response.text = yaml.dump(self.sample_spec)
        mock_response.headers = {'content-type': 'application/x-yaml'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.tools_service.load_openapi_spec("http://example.com/api.yaml")
        
        assert result == self.sample_spec
        assert result["openapi"] == "3.0.0"
        assert result["info"]["title"] == "Test API"
        mock_get.assert_called_once_with("http://example.com/api.yaml")
    
    @patch('requests.get')
    def test_load_openapi_spec_http_yaml_by_extension(self, mock_get):
        """Test loading OpenAPI spec from HTTP URL with YAML extension."""
        mock_response = Mock()
        mock_response.text = yaml.dump(self.sample_spec)
        mock_response.headers = {'content-type': 'text/plain'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.tools_service.load_openapi_spec("http://example.com/api.yaml")
        
        assert result == self.sample_spec
        assert result["openapi"] == "3.0.0"
        assert result["info"]["title"] == "Test API"
        mock_get.assert_called_once_with("http://example.com/api.yaml")
    
    @patch('requests.get')
    def test_load_openapi_spec_http_json_fallback_to_yaml(self, mock_get):
        """Test loading OpenAPI spec from HTTP URL with JSON fallback to YAML."""
        mock_response = Mock()
        mock_response.text = yaml.dump(self.sample_spec)
        mock_response.headers = {'content-type': 'application/json'}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = self.tools_service.load_openapi_spec("http://example.com/api.json")
        
        assert result == self.sample_spec
        assert result["openapi"] == "3.0.0"
        assert result["info"]["title"] == "Test API"
        mock_get.assert_called_once_with("http://example.com/api.json")
    
    def test_load_openapi_spec_json_fallback_to_yaml_file(self):
        """Test loading OpenAPI spec from file with JSON fallback to YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            yaml.dump(self.sample_spec, f)
            temp_file = f.name
        
        try:
            result = self.tools_service.load_openapi_spec(temp_file)
            assert result == self.sample_spec
            assert result["openapi"] == "3.0.0"
            assert result["info"]["title"] == "Test API"
        finally:
            os.unlink(temp_file)
    
    def test_load_openapi_spec_file_not_found(self):
        """Test loading OpenAPI spec from non-existent file."""
        with pytest.raises(Exception):
            self.tools_service.load_openapi_spec("nonexistent.json")
    
    @patch('requests.get')
    def test_load_openapi_spec_http_error(self, mock_get):
        """Test loading OpenAPI spec from HTTP URL with error."""
        mock_get.side_effect = Exception("Network error")
        
        with pytest.raises(Exception) as exc_info:
            self.tools_service.load_openapi_spec("http://example.com/api.json")
        
        assert "Network error" in str(exc_info.value)
    
    def test_load_openapi_spec_invalid_json_and_yaml(self):
        """Test loading OpenAPI spec with invalid JSON and YAML."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("invalid content that is neither JSON nor YAML")
            temp_file = f.name
        
        try:
            # YAML's safe_load doesn't raise exceptions for invalid content,
            # it just returns the string as-is, so this should succeed
            result = self.tools_service.load_openapi_spec(temp_file)
            assert result == "invalid content that is neither JSON nor YAML"
        finally:
            os.unlink(temp_file)
    
    def test_convert_to_openai_tools(self):
        """Test converting OpenAPI spec to OpenAI tools format."""
        tools = self.tools_service.convert_to_openai_tools(self.sample_spec)
        
        assert len(tools) == 2  # GET and POST operations
        
        # Check GET tool
        get_tool = next(tool for tool in tools if tool["function"]["name"] == "getUsers")
        assert get_tool["type"] == "function"
        assert get_tool["function"]["description"] == "Get all users"
        assert "limit" in get_tool["function"]["parameters"]["properties"]
        
        # Check POST tool
        post_tool = next(tool for tool in tools if tool["function"]["name"] == "createUser")
        assert post_tool["type"] == "function"
        assert "Create a new user" in post_tool["function"]["description"]
    
    def test_get_available_tools(self):
        """Test getting available tools from system configurations."""
        # Create a temporary JSON file for the test
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(self.sample_spec, f)
            temp_file = f.name
        
        try:
            system_configs = [
                {
                    "name": "test_system",
                    "openapi_spec": temp_file
                }
            ]
            
            tools = self.tools_service.get_available_tools(system_configs)
            
            assert len(tools) == 2  # GET and POST operations
            assert all(tool["system"] == "test_system" for tool in tools)
        finally:
            os.unlink(temp_file)
    
    def test_get_available_tools_with_invalid_spec(self):
        """Test getting available tools with invalid system configuration."""
        system_configs = [
            {
                "name": "invalid_system",
                "openapi_spec": "invalid_url"
            }
        ]
        
        # Should not raise exception, but log error
        tools = self.tools_service.get_available_tools(system_configs)
        assert tools == []
