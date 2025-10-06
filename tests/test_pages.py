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
    # Check that manifest link is present
    assert "Download Slack Manifest" in response.content.decode("utf-8")
    assert "/api/slack/manifest" in response.content.decode("utf-8")


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
    # Check that manifest link is NOT present when Slack is not configured
    assert "Download Slack Manifest" not in response.content.decode("utf-8")
    assert "/api/slack/manifest" not in response.content.decode("utf-8")


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


def test_slack_manifest_endpoint(test_client: TestClient):
    """Test Slack manifest endpoint."""
    response = test_client.get("/api/slack/manifest")
    
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/x-yaml"
    assert "attachment; filename=slack-manifest.yaml" in response.headers["content-disposition"]
    
    # Check that the manifest contains expected content
    manifest_content = response.content.decode("utf-8")
    assert "display_information:" in manifest_content
    assert "name: LIMP" in manifest_content
    assert "bot_user:" in manifest_content
    assert "display_name: LIMP" in manifest_content
    assert "oauth_config:" in manifest_content
    assert "settings:" in manifest_content
    
    # Check that bot_url placeholder has been replaced with actual URL
    assert "{{ bot_url }}" not in manifest_content
    assert "http://testserver" in manifest_content  # TestClient uses testserver as base URL


def test_slack_manifest_endpoint_missing_template(test_client: TestClient):
    """Test Slack manifest endpoint when template is missing."""
    with patch("fastapi.templating.Jinja2Templates.get_template", side_effect=Exception("Template not found")):
        response = test_client.get("/api/slack/manifest")
        
        assert response.status_code == 500
        assert "Internal server error" in response.json()["detail"]


def test_bot_description_configuration():
    """Test that bot description is properly configured and used in templates."""
    from limp.config import Config, DatabaseConfig, LLMConfig, BotConfig
    from limp.api.main import create_app
    from fastapi.testclient import TestClient
    
    # Test with custom bot description
    config = Config(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        llm=LLMConfig(api_key="test-api-key", model="gpt-4"),
        bot=BotConfig(
            name="Test Bot",
            description="Custom bot description for testing"
        )
    )
    
    app = create_app(config)
    client = TestClient(app)
    
    # Test main page with custom description
    response = client.get("/")
    content = response.content.decode("utf-8")
    assert "Custom bot description for testing" in content
    assert "Test Bot" in content
    
    # Test manifest with custom description
    response = client.get("/api/slack/manifest")
    manifest_content = response.content.decode("utf-8")
    assert "Custom bot description for testing" in manifest_content
    assert "Test Bot" in manifest_content


def test_bot_description_default():
    """Test that default bot description is used when not specified."""
    from limp.config import Config, DatabaseConfig, LLMConfig, BotConfig
    from limp.api.main import create_app
    from fastapi.testclient import TestClient
    
    # Test with default bot description (empty description should use default)
    config = Config(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        llm=LLMConfig(api_key="test-api-key", model="gpt-4"),
        bot=BotConfig(name="Test Bot")  # No description specified
    )
    
    app = create_app(config)
    client = TestClient(app)
    
    # Test main page with default description
    response = client.get("/")
    content = response.content.decode("utf-8")
    assert "Provide AI assistance directly in your chat applications." in content
    
    # Test manifest with default description
    response = client.get("/api/slack/manifest")
    manifest_content = response.content.decode("utf-8")
    assert "Provide AI assistance directly in your chat applications." in manifest_content
