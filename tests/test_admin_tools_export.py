"""
Tests for admin tools export page and APIs.
"""

import json
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
        assert isinstance(data["prompts"], list)


