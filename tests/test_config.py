"""
Tests for configuration management.
"""

import pytest
import tempfile
import yaml
import os
from pathlib import Path
from datetime import datetime

from limp.config import Config, load_config, DatabaseConfig, LLMConfig, OAuth2Config, ExternalSystemConfig
from limp.config.config import substitute_variables, _get_builtin_variable, _substitute_config_values


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
    assert config.max_iterations == 8  # Default value


def test_llm_config_with_max_iterations():
    """Test LLM config creation with custom max_iterations."""
    config = LLMConfig(
        api_key="test-key",
        model="gpt-4",
        max_tokens=1000,
        temperature=0.7,
        max_iterations=5
    )
    
    assert config.api_key == "test-key"
    assert config.model == "gpt-4"
    assert config.max_tokens == 1000
    assert config.temperature == 0.7
    assert config.provider == "openai"
    assert config.max_iterations == 5


def test_oauth2_config_creation():
    """Test OAuth2 config creation."""
    config = OAuth2Config(
        client_id="test-client-id",
        client_secret="test-client-secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token"
    )
    
    assert config.client_id == "test-client-id"
    assert config.client_secret == "test-client-secret"
    assert config.authorization_url == "https://example.com/oauth/authorize"
    assert config.token_url == "https://example.com/oauth/token"
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
    llm_config = LLMConfig(api_key="test-key", max_iterations=5)
    
    config = Config(
        llm=llm_config,
        prompts_dir="./test_prompts"
    )
    
    assert config.llm.api_key == "test-key"
    assert config.llm.max_iterations == 5
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
            "temperature": 0.5,
            "max_iterations": 10
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
            ]
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
        assert config.llm.max_iterations == 10
        assert len(config.external_systems) == 1
        assert config.external_systems[0].name == "test-system"
        
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


def test_external_system_primary_flag():
    """Test external system primary flag."""
    oauth2_config = OAuth2Config(
        client_id="test-client-id",
        client_secret="test-client-secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="http://localhost:8000/callback"
    )
    
    # Test default primary flag (should be False)
    system_config = ExternalSystemConfig(
        name="test-system",
        oauth2=oauth2_config,
        openapi_spec="https://example.com/api/openapi.json",
        base_url="https://example.com/api"
    )
    assert system_config.primary is False
    
    # Test explicit primary flag
    primary_system_config = ExternalSystemConfig(
        name="primary-system",
        oauth2=oauth2_config,
        openapi_spec="https://example.com/api/openapi.json",
        base_url="https://example.com/api",
        primary=True
    )
    assert primary_system_config.primary is True


def test_get_primary_system():
    """Test get_primary_system method."""
    llm_config = LLMConfig(api_key="test-key")
    
    oauth2_config = OAuth2Config(
        client_id="test-client-id",
        client_secret="test-client-secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="http://localhost:8000/callback"
    )
    
    # Test with no primary system
    config = Config(
        llm=llm_config,
        external_systems=[
            ExternalSystemConfig(
                name="system1",
                oauth2=oauth2_config,
                openapi_spec="https://example.com/api/openapi.json",
                base_url="https://example.com/api",
                primary=False
            ),
            ExternalSystemConfig(
                name="system2",
                oauth2=oauth2_config,
                openapi_spec="https://example.com/api/openapi.json",
                base_url="https://example.com/api",
                primary=False
            )
        ]
    )
    
    primary_system = config.get_primary_system()
    assert primary_system is None
    
    # Test with one primary system
    config.external_systems[0].primary = True
    primary_system = config.get_primary_system()
    assert primary_system is not None
    assert primary_system.name == "system1"
    assert primary_system.primary is True


def test_assign_primary_system():
    """Test assign_primary_system method."""
    llm_config = LLMConfig(api_key="test-key")
    
    oauth2_config = OAuth2Config(
        client_id="test-client-id",
        client_secret="test-client-secret",
        authorization_url="https://example.com/oauth/authorize",
        token_url="https://example.com/oauth/token",
        redirect_uri="http://localhost:8000/callback"
    )
    
    config = Config(
        llm=llm_config,
        external_systems=[
            ExternalSystemConfig(
                name="system1",
                oauth2=oauth2_config,
                openapi_spec="https://example.com/api/openapi.json",
                base_url="https://example.com/api",
                primary=False
            ),
            ExternalSystemConfig(
                name="system2",
                oauth2=oauth2_config,
                openapi_spec="https://example.com/api/openapi.json",
                base_url="https://example.com/api",
                primary=False
            )
        ]
    )
    
    # Test assigning primary system
    config.assign_primary_system("system1")
    assert config.external_systems[0].primary is True
    assert config.external_systems[1].primary is False
    assert config.get_primary_system().name == "system1"
    
    # Test switching primary system
    config.assign_primary_system("system2")
    assert config.external_systems[0].primary is False
    assert config.external_systems[1].primary is True
    assert config.get_primary_system().name == "system2"
    
    # Test assigning non-existent system
    with pytest.raises(ValueError, match="External system 'nonexistent' not found"):
        config.assign_primary_system("nonexistent")


def test_load_config_primary_system_sanity_check():
    """Test sanity check for multiple primary systems during config load."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "external_systems": [
            {
                "name": "system1",
                "oauth2": {
                    "client_id": "test-client-id",
                    "client_secret": "test-client-secret",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token",
                    "redirect_uri": "http://localhost:8000/callback"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api",
                "primary": True
            },
            {
                "name": "system2",
                "oauth2": {
                    "client_id": "test-client-id",
                    "client_secret": "test-client-secret",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token",
                    "redirect_uri": "http://localhost:8000/callback"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api",
                "primary": True
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        with pytest.raises(ValueError, match="Multiple primary external systems found"):
            load_config(config_path)
    finally:
        Path(config_path).unlink()


def test_load_config_single_primary_system():
    """Test loading config with single primary system (should succeed)."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "external_systems": [
            {
                "name": "system1",
                "oauth2": {
                    "client_id": "test-client-id",
                    "client_secret": "test-client-secret",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token",
                    "redirect_uri": "http://localhost:8000/callback"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api",
                "primary": True
            },
            {
                "name": "system2",
                "oauth2": {
                    "client_id": "test-client-id",
                    "client_secret": "test-client-secret",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token",
                    "redirect_uri": "http://localhost:8000/callback"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api",
                "primary": False
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        assert config is not None
        primary_system = config.get_primary_system()
        assert primary_system is not None
        assert primary_system.name == "system1"
        assert primary_system.primary is True
    finally:
        Path(config_path).unlink()


def test_load_config_no_primary_system():
    """Test loading config with no primary systems (should succeed)."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "external_systems": [
            {
                "name": "system1",
                "oauth2": {
                    "client_id": "test-client-id",
                    "client_secret": "test-client-secret",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token",
                    "redirect_uri": "http://localhost:8000/callback"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api",
                "primary": False
            }
        ]
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        assert config is not None
        primary_system = config.get_primary_system()
        assert primary_system is None
    finally:
        Path(config_path).unlink()


def test_bot_config_with_system_prompts():
    """Test bot configuration with system prompts."""
    from limp.config import BotConfig
    
    # Test with system prompts
    bot_config = BotConfig(
        name="Test Bot",
        url="https://example.com",
        system_prompts=[
            "You are a helpful AI assistant.",
            "Always be polite and professional.",
            "If you need to access external systems, ask the user to authorize access first."
        ]
    )
    
    assert bot_config.name == "Test Bot"
    assert bot_config.url == "https://example.com"
    assert len(bot_config.system_prompts) == 3
    assert bot_config.system_prompts[0] == "You are a helpful AI assistant."
    assert bot_config.system_prompts[1] == "Always be polite and professional."
    assert bot_config.system_prompts[2] == "If you need to access external systems, ask the user to authorize access first."


def test_bot_config_without_system_prompts():
    """Test bot configuration without system prompts (should default to empty list)."""
    from limp.config import BotConfig
    
    # Test without system prompts (should default to empty list)
    bot_config = BotConfig(
        name="Test Bot",
        url="https://example.com"
    )
    
    assert bot_config.name == "Test Bot"
    assert bot_config.url == "https://example.com"
    assert bot_config.system_prompts == []


def test_load_config_with_system_prompts():
    """Test loading config with system prompts."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "bot": {
            "name": "Test Bot",
            "url": "https://example.com",
            "system_prompts": [
                "You are a helpful AI assistant.",
                "Always be polite and professional.",
                "If you need to access external systems, ask the user to authorize access first."
            ]
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        assert config is not None
        assert config.bot.name == "Test Bot"
        assert config.bot.url == "https://example.com"
        assert len(config.bot.system_prompts) == 3
        assert config.bot.system_prompts[0] == "You are a helpful AI assistant."
        assert config.bot.system_prompts[1] == "Always be polite and professional."
        assert config.bot.system_prompts[2] == "If you need to access external systems, ask the user to authorize access first."
    finally:
        Path(config_path).unlink()


def test_load_config_without_system_prompts():
    """Test loading config without system prompts (should default to empty list)."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "bot": {
            "name": "Test Bot",
            "url": "https://example.com"
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        assert config is not None
        assert config.bot.name == "Test Bot"
        assert config.bot.url == "https://example.com"
        assert config.bot.system_prompts == []
    finally:
        Path(config_path).unlink()


def test_load_config_with_empty_system_prompts():
    """Test loading config with empty system prompts list."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "bot": {
            "name": "Test Bot",
            "url": "https://example.com",
            "system_prompts": []
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        assert config is not None
        assert config.bot.name == "Test Bot"
        assert config.bot.url == "https://example.com"
        assert config.bot.system_prompts == []
    finally:
        Path(config_path).unlink()

