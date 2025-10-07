"""
Tests for admin tools export page and APIs.
"""

import json
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch


def test_tools_export_page_loads(test_client: TestClient):
    response = test_client.get("/admin/tools")
    assert response.status_code == 200
    html = response.content.decode("utf-8")
    assert "Export Tools & Prompts" in html


def test_tools_list_systems_authorized(test_client: TestClient):
    with patch('limp.api.admin.verify_admin_credentials') as mock_verify:
        mock_verify.return_value = True
        response = test_client.get("/admin/tools/api/systems", auth=("admin", "admin123"))
        assert response.status_code == 200
        data = response.json()
        assert "systems" in data


def test_tools_export_authorized(test_client: TestClient):
    # Mock verify and tools service methods that call out
    with patch('limp.api.admin.verify_admin_credentials') as mock_verify, \
         patch('limp.services.tools.ToolsService._get_or_load_spec') as mock_load_spec:
        mock_verify.return_value = True
        mock_load_spec.return_value = {
            "openapi": "3.0.0",
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "responses": {
                            "200": {"content": {"application/json": {"schema": {"type": "array", "items": {"type": "object", "properties": {"id": {"type": "string"}}}}}}}
                        }
                    }
                }
            }
        }

        response = test_client.get("/admin/tools/api/export", params={"system": "test-system"}, auth=("admin", "admin123"))
        assert response.status_code == 200
        data = response.json()
        assert data["system"] == "test-system"
        assert isinstance(data["tools"], list)
        assert isinstance(data["tool_prompts"], dict)
        # Check that tool prompts are generated for the operation
        assert "listItems" in data["tool_prompts"]


def test_tool_system_prompts_generation():
    """Test that ToolsService generates per-tool system prompts correctly."""
    from limp.services.tools import ToolsService
    
    tools_service = ToolsService()
    
    # Mock OpenAPI spec
    openapi_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "data": {
                                                "type": "array",
                                                "items": {
                                                    "type": "object",
                                                    "properties": {
                                                        "id": {"type": "string"},
                                                        "name": {"type": "string"}
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    
    tool_prompts = tools_service.generate_tool_system_prompts(openapi_spec)
    
    assert "getUsers" in tool_prompts
    assert "Tool Output Schema for getUsers" in tool_prompts["getUsers"]
    assert "data" in tool_prompts["getUsers"]  # Should describe the response structure


def test_tool_system_prompts_injection_logic():
    """Test that the logic for injecting tool-specific system prompts works correctly."""
    from limp.services.tools import ToolsService
    
    tools_service = ToolsService()
    
    # Test that generate_tool_system_prompts returns the expected format with comprehensive schema descriptions
    openapi_spec = {
        "openapi": "3.0.0",
        "paths": {
            "/users": {
                "get": {
                    "operationId": "getUsers",
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "data": {
                                                "type": "array",
                                                "items": {"$ref": "#/components/schemas/User"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        },
        "components": {
            "schemas": {
                "User": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer", "description": "User ID"},
                        "name": {"type": "string", "description": "User name"},
                        "email": {"type": "string", "description": "User email"}
                    }
                }
            }
        }
    }
    
    tool_prompts = tools_service.generate_tool_system_prompts(openapi_spec)
    
    # Verify the structure of the generated prompt
    assert "getUsers" in tool_prompts
    prompt = tool_prompts["getUsers"]
    assert "Tool Output Schema for getUsers" in prompt
    assert "data" in prompt  # Should describe the response structure
    assert "This describes the complete structure of data returned by the getUsers tool" in prompt
    # Should include referenced schema information
    assert "User Schema:" in prompt or "Referenced Types:" in prompt


