"""
Tests for built-in pages (install, install-success, root page).
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch

from limp.api.main import create_app
from limp.config import Config, DatabaseConfig, LLMConfig


def test_root_page_with_slack_configured(test_client: TestClient):
    """Test root page when Slack is configured."""
    response = test_client.get("/")
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Install to Slack" in response.content.decode("utf-8")
    assert "slack.com/oauth/v2/authorize" in response.content.decode("utf-8")


def test_root_page_without_slack_configured(test_client: TestClient):
    """Test root page when Slack is not configured."""
    # Create a test app without Slack configuration
    from limp.config import AdminConfig, IMPlatformConfig, ExternalSystemConfig, OAuth2Config
    
    test_config_no_slack = Config(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        llm=LLMConfig(
            api_key="test-api-key",
            model="gpt-4",
            max_tokens=1000,
            temperature=0.7
        ),
        admin=AdminConfig(enabled=True, username="admin", password="admin123"),
        im_platforms=[],  # No Slack configured
        external_systems=[
            ExternalSystemConfig(
                name="test-system",
                oauth2=OAuth2Config(
                    client_id="test-client-id",
                    client_secret="test-client-secret",
                    authorization_url="https://example.com/oauth/authorize",
                    token_url="https://example.com/oauth/token",
                    redirect_uri="http://localhost:8000/callback"
                ),
                openapi_spec="https://example.com/api/openapi.json",
                base_url="https://example.com/api"
            )
        ],
    )
    
    test_app_no_slack = create_app(test_config_no_slack)
    test_client_no_slack = TestClient(test_app_no_slack)
    
    response = test_client_no_slack.get("/")
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Slack Not Configured" in response.content.decode("utf-8")
    assert "Configuration Error" in response.content.decode("utf-8")


def test_install_success_page_slack(test_client: TestClient):
    """Test installation success page for Slack."""
    response = test_client.get("/install-success?system=slack&organization=Test%20Team")
    
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Installation Successful!" in response.content.decode("utf-8")
    assert "Test Team" in response.content.decode("utf-8")
    assert "Slack" in response.content.decode("utf-8")


def test_install_success_page_teams(test_client: TestClient):
    """Test installation success page for Teams."""
    response = test_client.get("/install-success?system=teams&organization=Test%20Organization")
    
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Installation Successful!" in response.content.decode("utf-8")
    assert "Test Organization" in response.content.decode("utf-8")
    assert "Teams" in response.content.decode("utf-8")


def test_install_success_page_no_organization(test_client: TestClient):
    """Test installation success page without organization name."""
    response = test_client.get("/install-success?system=slack")
    
    assert response.status_code == 200
    assert "<html" in response.content.decode("utf-8")
    assert "Installation Successful!" in response.content.decode("utf-8")
    assert "N/A" in response.content.decode("utf-8")  # Should show N/A for missing organization


def test_install_success_page_missing_system(test_client: TestClient):
    """Test installation success page with missing system parameter."""
    response = test_client.get("/install-success")
    
    assert response.status_code == 422  # FastAPI validation error for missing required parameter
