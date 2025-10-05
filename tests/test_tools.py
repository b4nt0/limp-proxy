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
        mock_response.text = json.dumps(mock_spec)
        mock_response.headers = {'content-type': 'application/json'}
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


def test_get_cleaned_tools_for_openai():
    """Test getting cleaned tools for OpenAI API."""
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
        }
    ]
    
    with patch.object(service, 'load_openapi_spec') as mock_load:
        mock_load.side_effect = lambda spec: spec  # Return spec as-is
        
        cleaned_tools = service.get_cleaned_tools_for_openai(system_configs)
        
        # Verify tools are cleaned (no system field)
        assert len(cleaned_tools) == 1
        assert cleaned_tools[0]["type"] == "function"
        assert cleaned_tools[0]["function"]["name"] == "getUsers"
        assert "system" not in cleaned_tools[0]


def test_get_system_name_for_tool():
    """Test getting system name for a specific tool."""
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
        
        # Test finding tool in first system
        system_name = service.get_system_name_for_tool("getUsers", system_configs)
        assert system_name == "system1"
        
        # Test finding tool in second system
        system_name = service.get_system_name_for_tool("getProducts", system_configs)
        assert system_name == "system2"
        
        # Test tool not found (fallback to first system)
        system_name = service.get_system_name_for_tool("nonExistentTool", system_configs)
        assert system_name == "system1"


def test_convert_parameters_with_arrays():
    """Test converting OpenAPI parameters with array types."""
    service = ToolsService()
    
    parameters = [
        {
            "name": "by_resource_ids",
            "in": "query",
            "required": False,
            "schema": {
                "type": "array",
                "items": {
                    "type": "integer"
                }
            },
            "description": "Filter by resource IDs."
        },
        {
            "name": "organization_id",
            "in": "query",
            "required": True,
            "schema": {
                "type": "integer"
            },
            "description": "ID of the organization."
        }
    ]
    
    result = service._convert_parameters(parameters)
    
    # Verify the schema structure
    assert result["type"] == "object"
    assert "by_resource_ids" in result["properties"]
    assert "organization_id" in result["properties"]
    
    # Verify array parameter has items specification
    by_resource_ids = result["properties"]["by_resource_ids"]
    assert by_resource_ids["type"] == "array"
    assert "items" in by_resource_ids
    assert by_resource_ids["items"]["type"] == "integer"
    
    # Verify regular parameter
    organization_id = result["properties"]["organization_id"]
    assert organization_id["type"] == "integer"
    
    # Verify required fields
    assert "organization_id" in result["required"]
    assert "by_resource_ids" not in result["required"]


def test_convert_to_openai_tools_with_rich_descriptions():
    """Test that OpenAPI tools include rich descriptions from summaries, descriptions, and tags."""
    service = ToolsService()
    
    openapi_spec = {
        "paths": {
            "/api/v1/organizations": {
                "get": {
                    "summary": "Get a list of organizations",
                    "description": "Returns a list of organizations that the authenticated user has access to.",
                    "tags": ["organization", "company", "context"],
                    "operationId": "getOrganizations",
                    "parameters": []
                }
            },
            "/api/v1/workspaces": {
                "get": {
                    "summary": "Get a list of portfolios",
                    "description": "Returns a list of portfolios for the selected organization.",
                    "tags": ["portfolio", "context"],
                    "operationId": "getPortfolios",
                    "parameters": [
                        {
                            "name": "organization_id",
                            "in": "query",
                            "required": True,
                            "description": "The ID of the organization whose portfolios should be listed.",
                            "schema": {"type": "integer"}
                        }
                    ]
                }
            }
        }
    }
    
    tools = service.convert_to_openai_tools(openapi_spec)
    
    # Verify we have the expected tools
    assert len(tools) == 2
    
    # Find the getOrganizations tool
    org_tool = next(tool for tool in tools if tool["function"]["name"] == "getOrganizations")
    assert org_tool is not None
    
    # Verify rich description includes summary, description, and tags
    description = org_tool["function"]["description"]
    assert "Get a list of organizations" in description
    assert "Returns a list of organizations that the authenticated user has access to." in description
    assert "Tags: organization, company, context" in description
    
    # Find the getPortfolios tool
    portfolio_tool = next(tool for tool in tools if tool["function"]["name"] == "getPortfolios")
    assert portfolio_tool is not None
    
    # Verify rich description
    description = portfolio_tool["function"]["description"]
    assert "Get a list of portfolios" in description
    assert "Returns a list of portfolios for the selected organization." in description
    assert "Tags: portfolio, context" in description
    
    # Verify parameter description is preserved
    params = portfolio_tool["function"]["parameters"]
    assert "organization_id" in params["properties"]
    assert params["properties"]["organization_id"]["description"] == "The ID of the organization whose portfolios should be listed."
    assert "organization_id" in params["required"]


def test_convert_parameters_with_enhanced_metadata():
    """Test that parameter conversion includes format, enum, and other metadata."""
    service = ToolsService()
    
    parameters = [
        {
            "name": "dt_from",
            "in": "query",
            "required": False,
            "description": "Start date of the interval (YYYY-MM-DD).",
            "schema": {
                "type": "string",
                "format": "date"
            }
        },
        {
            "name": "per_time_period",
            "in": "query",
            "required": True,
            "description": "Grouping by time: day, week, month, or year.",
            "schema": {
                "type": "string",
                "enum": ["day", "week", "month", "year"]
            }
        },
        {
            "name": "workspace_id",
            "in": "path",
            "required": True,
            "description": "ID of the portfolio.",
            "schema": {
                "type": "integer",
                "minimum": 1
            }
        }
    ]
    
    result = service._convert_parameters(parameters)
    
    # Verify date format is preserved
    dt_from = result["properties"]["dt_from"]
    assert dt_from["type"] == "string"
    assert dt_from["format"] == "date"
    assert "Start date of the interval (YYYY-MM-DD)." in dt_from["description"]
    
    # Verify enum values are preserved
    per_time_period = result["properties"]["per_time_period"]
    assert per_time_period["type"] == "string"
    assert per_time_period["enum"] == ["day", "week", "month", "year"]
    assert "Grouping by time: day, week, month, or year." in per_time_period["description"]
    assert "per_time_period" in result["required"]
    
    # Verify numeric constraints and path parameter context
    workspace_id = result["properties"]["workspace_id"]
    assert workspace_id["type"] == "integer"
    assert workspace_id["minimum"] == 1
    assert "ID of the portfolio." in workspace_id["description"]
    assert "(URL path parameter)" in workspace_id["description"]
    assert "workspace_id" in result["required"]
