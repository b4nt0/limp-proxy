"""
Tests for tools service.
"""

import pytest
import json
from unittest.mock import Mock, patch, mock_open
from limp.services.tools import ToolsService


def test_load_openapi_spec_from_url():
    """Test loading OpenAPI spec from URL."""
    service = ToolsService()
    
    # Mock OpenAPI spec
    mock_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "description": "Get all users",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "schema": {"type": "integer"}
                        }
                    ]
                }
            }
        }
    }
    
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = mock_spec
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        spec = service.load_openapi_spec("https://example.com/api/openapi.json")
        
        assert spec == mock_spec


def test_load_openapi_spec_from_file():
    """Test loading OpenAPI spec from file."""
    service = ToolsService()
    
    # Mock OpenAPI spec
    mock_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "description": "Get all users"
                }
            }
        }
    }
    
    with patch("builtins.open", mock_open(read_data=json.dumps(mock_spec))):
        spec = service.load_openapi_spec("./openapi.json")
        
        assert spec == mock_spec


def test_load_openapi_spec_error():
    """Test loading OpenAPI spec with error."""
    service = ToolsService()
    
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        with pytest.raises(Exception) as exc_info:
            service.load_openapi_spec("https://example.com/api/openapi.json")
        
        assert "Network error" in str(exc_info.value)


def test_convert_to_openai_tools():
    """Test converting OpenAPI spec to OpenAI tools format."""
    service = ToolsService()
    
    openapi_spec = {
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "description": "Get all users",
                    "parameters": [
                        {
                            "name": "limit",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "integer"},
                            "description": "Maximum number of users to return"
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
                                    },
                                    "required": ["name", "email"]
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    tools = service.convert_to_openai_tools(openapi_spec)
    
    # Verify tools structure
    assert len(tools) == 2
    
    # Check GET tool
    get_tool = next(t for t in tools if t["function"]["name"] == "getUsers")
    assert get_tool["type"] == "function"
    assert get_tool["function"]["description"] == "Get all users"
    assert "limit" in get_tool["function"]["parameters"]["properties"]
    assert "limit" in get_tool["function"]["parameters"]["required"]
    
    # Check POST tool
    post_tool = next(t for t in tools if t["function"]["name"] == "createUser")
    assert post_tool["type"] == "function"
    assert post_tool["function"]["description"] == "Create a new user"


def test_execute_tool_call_success():
    """Test successful tool call execution."""
    service = ToolsService()
    
    # Mock OpenAPI spec
    openapi_spec = {
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "description": "Get all users"
                }
            }
        }
    }
    
    system_config = {
        "name": "test_system",
        "openapi_spec": openapi_spec,
        "base_url": "https://example.com/api"
    }
    
    tool_call = {
        "function": {
            "name": "getUsers",
            "arguments": '{"limit": 10}'
        }
    }
    
    with patch('requests.get') as mock_get:
        mock_response = Mock()
        mock_response.json.return_value = {"users": []}
        mock_response.status_code = 200
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        
        result = service.execute_tool_call(tool_call, system_config, "test_token")
        
        # Verify result
        assert result["success"] is True
        assert result["data"] == {"users": []}
        assert result["status_code"] == 200
        
        # Verify request was made correctly
        mock_get.assert_called_once_with(
            "https://example.com/api/users",
            params={"limit": 10},
            headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"}
        )


def test_execute_tool_call_post():
    """Test POST tool call execution."""
    service = ToolsService()
    
    # Mock OpenAPI spec
    openapi_spec = {
        "paths": {
            "/users": {
                "post": {
                    "operationId": "createUser",
                    "description": "Create a new user"
                }
            }
        }
    }
    
    system_config = {
        "name": "test_system",
        "openapi_spec": openapi_spec,
        "base_url": "https://example.com/api"
    }
    
    tool_call = {
        "function": {
            "name": "createUser",
            "arguments": '{"name": "John", "email": "john@example.com"}'
        }
    }
    
    with patch('requests.post') as mock_post:
        mock_response = Mock()
        mock_response.json.return_value = {"id": 1, "name": "John"}
        mock_response.status_code = 201
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response
        
        result = service.execute_tool_call(tool_call, system_config, "test_token")
        
        # Verify result
        assert result["success"] is True
        assert result["data"] == {"id": 1, "name": "John"}
        assert result["status_code"] == 201
        
        # Verify request was made correctly
        mock_post.assert_called_once_with(
            "https://example.com/api/users",
            json={"name": "John", "email": "john@example.com"},
            headers={"Content-Type": "application/json", "Authorization": "Bearer test_token"}
        )


def test_execute_tool_call_error():
    """Test tool call execution with error."""
    service = ToolsService()
    
    # Mock OpenAPI spec
    openapi_spec = {
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "description": "Get all users"
                }
            }
        }
    }
    
    system_config = {
        "name": "test_system",
        "openapi_spec": openapi_spec,
        "base_url": "https://example.com/api"
    }
    
    tool_call = {
        "function": {
            "name": "getUsers",
            "arguments": '{"limit": 10}'
        }
    }
    
    with patch('requests.get') as mock_get:
        mock_get.side_effect = Exception("Network error")
        
        result = service.execute_tool_call(tool_call, system_config, "test_token")
        
        # Verify error result
        assert result["success"] is False
        assert "Network error" in result["error"]


def test_execute_tool_call_operation_not_found():
    """Test tool call with operation not found."""
    service = ToolsService()
    
    # Mock OpenAPI spec
    openapi_spec = {
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "description": "Get all users"
                }
            }
        }
    }
    
    system_config = {
        "name": "test_system",
        "openapi_spec": openapi_spec,
        "base_url": "https://example.com/api"
    }
    
    tool_call = {
        "function": {
            "name": "nonExistentOperation",
            "arguments": '{}'
        }
    }
    
    result = service.execute_tool_call(tool_call, system_config, "test_token")
    
    # Verify error result
    assert "error" in result
    assert "not found" in result["error"]


def test_get_available_tools():
    """Test getting available tools from system configurations."""
    service = ToolsService()
    
    # Mock system configs
    system_configs = [
        {
            "name": "system1",
            "openapi_spec": {
                "paths": {
                    "/users": {
                        "get": {
                            "operationId": "getUsers",
                            "description": "Get all users"
                        }
                    }
                }
            }
        },
        {
            "name": "system2",
            "openapi_spec": {
                "paths": {
                    "/products": {
                        "get": {
                            "operationId": "getProducts",
                            "description": "Get all products"
                        }
                    }
                }
            }
        }
    ]
    
    with patch.object(service, 'load_openapi_spec') as mock_load:
        mock_load.side_effect = lambda spec: spec  # Return spec as-is
        mock_load.return_value = system_configs[0]["openapi_spec"]
        
        tools = service.get_available_tools(system_configs)
        
        # Verify tools
        assert len(tools) == 2
        assert any(tool["function"]["name"] == "getUsers" for tool in tools)
        assert any(tool["function"]["name"] == "getProducts" for tool in tools)
        assert all("system" in tool for tool in tools)
