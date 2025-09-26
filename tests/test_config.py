"""
Tests for configuration management.
"""

import pytest
import tempfile
import yaml
from pathlib import Path

from limp.config import Config, load_config, DatabaseConfig, LLMConfig, OAuth2Config, ExternalSystemConfig


def test_database_config_defaults():
    """Test database config defaults."""
    config = DatabaseConfig()
    assert config.url == "sqlite:///./limp.db"
    assert config.echo is False


def test_llm_config_creation():
    """Test LLM config creation."""
    config = LLMConfig(
        api_key="test-key",
        model="gpt-4",
        max_tokens=1000,
        temperature=0.7
    )
    
    assert config.api_key == "test-key"
    assert config.model == "gpt-4"
    assert config.max_tokens == 1000
    assert config.temperature == 0.7
    assert config.provider == "openai"


def test_oauth2_config_creation():
    """Test OAuth2 config creation."""
    config = OAuth2Config(
        client_id="test-client-id",
        client_secret="test-client-secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="http://localhost:8000/callback"
    )
    
    assert config.client_id == "test-client-id"
    assert config.client_secret == "test-client-secret"
    assert config.authorization_url == "https://example.com/oauth/authorize"
    assert config.token_url == "https://example.com/oauth/token"
    assert config.redirect_uri == "http://localhost:8000/callback"
    assert config.scope is None


def test_external_system_config_creation():
    """Test external system config creation."""
    oauth2_config = OAuth2Config(
        client_id="test-client-id",
        client_secret="test-client-secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="http://localhost:8000/callback"
    )
    
    system_config = ExternalSystemConfig(
        name="test-system",
        oauth2=oauth2_config,
        openapi_spec="https://example.com/api/openapi.json",
        base_url="https://example.com/api"
    )
    
    assert system_config.name == "test-system"
    assert system_config.oauth2.client_id == "test-client-id"
    assert system_config.openapi_spec == "https://example.com/api/openapi.json"
    assert system_config.base_url == "https://example.com/api"


def test_config_creation():
    """Test main config creation."""
    llm_config = LLMConfig(api_key="test-key")
    
    config = Config(
        llm=llm_config,
        max_iterations=5,
        prompts_dir="./test_prompts"
    )
    
    assert config.llm.api_key == "test-key"
    assert config.max_iterations == 5
    assert config.prompts_dir == "./test_prompts"
    assert config.database.url == "sqlite:///./limp.db"  # Default value


def test_load_config_from_file():
    """Test loading config from YAML file."""
    config_data = {
        "database": {
            "url": "sqlite:///test.db",
            "echo": True
        },
        "llm": {
            "api_key": "test-key",
            "model": "gpt-3.5-turbo",
            "max_tokens": 2000,
            "temperature": 0.5
        },
        "external_systems": [
            {
                "name": "test-system",
                "oauth2": {
                    "client_id": "test-client-id",
                    "client_secret": "test-client-secret",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token",
                    "redirect_uri": "http://localhost:8000/callback"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api"
            }
        ],
        "max_iterations": 15
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        assert config.database.url == "sqlite:///test.db"
        assert config.database.echo is True
        assert config.llm.api_key == "test-key"
        assert config.llm.model == "gpt-3.5-turbo"
        assert config.llm.max_tokens == 2000
        assert config.llm.temperature == 0.5
        assert len(config.external_systems) == 1
        assert config.external_systems[0].name == "test-system"
        assert config.max_iterations == 15
        
    finally:
        Path(config_path).unlink()


def test_load_config_file_not_found():
    """Test loading config from non-existent file."""
    with pytest.raises(FileNotFoundError):
        load_config("non-existent-config.yaml")


def test_config_validation():
    """Test config validation."""
    # Test missing required field
    with pytest.raises(ValueError):
        Config()  # Missing required llm field
    
    # Test invalid field type
    with pytest.raises(ValueError):
        LLMConfig(
            api_key="test-key",
            max_tokens="invalid"  # Should be int
        )

