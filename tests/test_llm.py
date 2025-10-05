"""
Tests for LLM service.
"""

import pytest
from unittest.mock import Mock, patch
from openai import OpenAI

from limp.services.llm import LLMService
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
    
    # Verify message structure (should be same as no system prompts)
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
    
    # Verify message structure (should be same as no system prompts)
    assert len(messages) == 3
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hi"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Hello! How can I help you?"
    assert messages[2]["role"] == "user"
    assert messages[2]["content"] == "Hello, how are you?"


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
