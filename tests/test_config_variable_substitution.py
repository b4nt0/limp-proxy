"""
Tests for variable substitution in configuration management.
"""

import pytest
import tempfile
import yaml
import os
from pathlib import Path
from datetime import datetime

from limp.config import load_config
from limp.config.config import substitute_variables, _get_builtin_variable, _substitute_config_values


def test_builtin_variables():
    """Test built-in variable functionality."""
    # Test today variable
    today_value = _get_builtin_variable('today')
    assert today_value is not None
    assert isinstance(today_value, str)
    # Should be in YYYY-MM-DD format
    assert len(today_value) == 10
    assert today_value.count('-') == 2
    
    # Test non-existent built-in variable
    non_existent = _get_builtin_variable('nonexistent')
    assert non_existent is None


def test_substitute_variables_builtin():
    """Test variable substitution with built-in variables."""
    # Test single built-in variable
    result = substitute_variables("Today is ${today}")
    assert result is not None
    assert "Today is" in result
    assert result != "Today is ${today}"  # Should be substituted
    
    # Test built-in variable in mixed content
    result = substitute_variables("Date: ${today}, some other text")
    assert "Date:" in result
    assert "some other text" in result
    assert "${today}" not in result


def test_substitute_variables_environment():
    """Test variable substitution with environment variables."""
    # Set test environment variable
    os.environ['TEST_VAR'] = 'test_value'
    
    try:
        # Test single environment variable
        result = substitute_variables("Value is ${TEST_VAR}")
        assert result == "Value is test_value"
        
        # Test environment variable in mixed content
        result = substitute_variables("Prefix ${TEST_VAR} suffix")
        assert result == "Prefix test_value suffix"
        
    finally:
        # Clean up
        del os.environ['TEST_VAR']


def test_substitute_variables_priority():
    """Test variable substitution priority (environment over built-in)."""
    # Set environment variable that conflicts with built-in
    os.environ['today'] = '2023-01-01'
    
    try:
        # Environment variable should take priority over built-in
        result = substitute_variables("Date: ${today}")
        assert result == "Date: 2023-01-01"
        
    finally:
        # Clean up
        del os.environ['today']


def test_substitute_variables_missing():
    """Test variable substitution with missing variables."""
    # Test missing variable
    result = substitute_variables("Missing: ${MISSING_VAR}")
    assert result == "Missing: "
    
    # Test multiple missing variables
    result = substitute_variables("Missing: ${MISSING1} and ${MISSING2}")
    assert result == "Missing:  and "


def test_substitute_variables_mixed():
    """Test variable substitution with mixed variable types."""
    # Set environment variable
    os.environ['ENV_VAR'] = 'env_value'
    
    try:
        # Test mix of environment, built-in, and missing variables
        result = substitute_variables("Env: ${ENV_VAR}, Today: ${today}, Missing: ${MISSING}")
        assert "Env: env_value" in result
        assert "Today:" in result
        assert "Missing: " in result
        assert "${ENV_VAR}" not in result
        assert "${today}" not in result
        assert "${MISSING}" not in result
        
    finally:
        # Clean up
        del os.environ['ENV_VAR']


def test_substitute_variables_non_string():
    """Test variable substitution with non-string inputs."""
    # Test with integer
    result = substitute_variables(123)
    assert result == 123
    
    # Test with None
    result = substitute_variables(None)
    assert result is None
    
    # Test with boolean
    result = substitute_variables(True)
    assert result is True


def test_substitute_variables_none_conversion():
    """Test that 'None' string is converted to actual None."""
    # Test with missing variable that should result in None
    result = substitute_variables("${MISSING_VAR}")
    assert result == ""
    
    # Test with explicit None string
    result = substitute_variables("None")
    assert result is None


def test_substitute_config_values_dict():
    """Test recursive variable substitution in dictionaries."""
    config_data = {
        "string_value": "Hello ${ENV_VAR}",
        "nested": {
            "nested_string": "Today is ${today}",
            "nested_number": 42
        },
        "number_value": 123
    }
    
    # Set environment variable
    os.environ['ENV_VAR'] = 'World'
    
    try:
        result = _substitute_config_values(config_data)
        
        assert result["string_value"] == "Hello World"
        assert "Today is" in result["nested"]["nested_string"]
        assert result["nested"]["nested_number"] == 42
        assert result["number_value"] == 123
        
    finally:
        # Clean up
        del os.environ['ENV_VAR']


def test_substitute_config_values_list():
    """Test recursive variable substitution in lists."""
    config_data = [
        "First ${ENV_VAR}",
        42,
        {
            "nested": "Second ${ENV_VAR}"
        },
        "Third ${today}"
    ]
    
    # Set environment variable
    os.environ['ENV_VAR'] = 'item'
    
    try:
        result = _substitute_config_values(config_data)
        
        assert result[0] == "First item"
        assert result[1] == 42
        assert result[2]["nested"] == "Second item"
        assert "Third" in result[3]
        
    finally:
        # Clean up
        del os.environ['ENV_VAR']


def test_load_config_with_variables():
    """Test loading configuration with variable substitution."""
    config_data = {
        "llm": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4",
            "max_tokens": 4000
        },
        "database": {
            "url": "${DATABASE_URL}"
        },
        "bot": {
            "name": "Test Bot",
            "system_prompts": [
                "You are a helpful assistant.",
                "Today is ${today}"
            ]
        }
    }
    
    # Set environment variables
    os.environ['OPENAI_API_KEY'] = 'test-api-key'
    os.environ['DATABASE_URL'] = 'sqlite:///test.db'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        assert config.llm.api_key == 'test-api-key'
        assert config.database.url == 'sqlite:///test.db'
        assert config.bot.name == 'Test Bot'
        assert len(config.bot.system_prompts) == 2
        assert config.bot.system_prompts[0] == 'You are a helpful assistant.'
        assert 'Today is' in config.bot.system_prompts[1]
        assert '${today}' not in config.bot.system_prompts[1]
        
    finally:
        Path(config_path).unlink()
        # Clean up environment variables
        del os.environ['OPENAI_API_KEY']
        del os.environ['DATABASE_URL']


def test_load_config_with_missing_variables():
    """Test loading configuration with missing variables."""
    config_data = {
        "llm": {
            "api_key": "${MISSING_API_KEY}",
            "model": "gpt-4"
        },
        "database": {
            "url": "sqlite:///test.db"
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        # Missing variable should result in empty string
        assert config.llm.api_key == ""
        assert config.database.url == "sqlite:///test.db"
        
    finally:
        Path(config_path).unlink()


def test_load_config_with_external_systems_variables():
    """Test loading configuration with variables in external systems."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "external_systems": [
            {
                "name": "test-system",
                "oauth2": {
                    "client_id": "${CLIENT_ID}",
                    "client_secret": "${CLIENT_SECRET}",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api"
            }
        ]
    }
    
    # Set environment variables
    os.environ['CLIENT_ID'] = 'test-client-id'
    os.environ['CLIENT_SECRET'] = 'test-client-secret'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        assert len(config.external_systems) == 1
        assert config.external_systems[0].name == "test-system"
        assert config.external_systems[0].oauth2.client_id == "test-client-id"
        assert config.external_systems[0].oauth2.client_secret == "test-client-secret"
        
    finally:
        Path(config_path).unlink()
        # Clean up environment variables
        del os.environ['CLIENT_ID']
        del os.environ['CLIENT_SECRET']


def test_load_config_with_im_platforms_variables():
    """Test loading configuration with variables in IM platforms."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "im_platforms": [
            {
                "platform": "slack",
                "app_id": "${SLACK_APP_ID}",
                "client_id": "${SLACK_CLIENT_ID}",
                "client_secret": "${SLACK_CLIENT_SECRET}",
                "signing_secret": "${SLACK_SIGNING_SECRET}"
            }
        ]
    }
    
    # Set environment variables
    os.environ['SLACK_APP_ID'] = 'test-slack-app-id'
    os.environ['SLACK_CLIENT_ID'] = 'test-slack-client-id'
    os.environ['SLACK_CLIENT_SECRET'] = 'test-slack-client-secret'
    os.environ['SLACK_SIGNING_SECRET'] = 'test-slack-signing-secret'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        assert len(config.im_platforms) == 1
        assert config.im_platforms[0].platform == "slack"
        assert config.im_platforms[0].app_id == "test-slack-app-id"
        assert config.im_platforms[0].client_id == "test-slack-client-id"
        assert config.im_platforms[0].client_secret == "test-slack-client-secret"
        assert config.im_platforms[0].signing_secret == "test-slack-signing-secret"
        
    finally:
        Path(config_path).unlink()
        # Clean up environment variables
        del os.environ['SLACK_APP_ID']
        del os.environ['SLACK_CLIENT_ID']
        del os.environ['SLACK_CLIENT_SECRET']
        del os.environ['SLACK_SIGNING_SECRET']


def test_load_config_with_admin_variables():
    """Test loading configuration with variables in admin settings."""
    config_data = {
        "llm": {
            "api_key": "test-key"
        },
        "admin": {
            "enabled": True,
            "username": "${ADMIN_USERNAME}",
            "password": "${ADMIN_PASSWORD}"
        }
    }
    
    # Set environment variables
    os.environ['ADMIN_USERNAME'] = 'test-admin'
    os.environ['ADMIN_PASSWORD'] = 'test-password'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        assert config.admin.enabled is True
        assert config.admin.username == "test-admin"
        assert config.admin.password == "test-password"
        
    finally:
        Path(config_path).unlink()
        # Clean up environment variables
        del os.environ['ADMIN_USERNAME']
        del os.environ['ADMIN_PASSWORD']


def test_load_config_complex_variable_substitution():
    """Test complex variable substitution scenarios."""
    config_data = {
        "llm": {
            "api_key": "${OPENAI_API_KEY}",
            "model": "gpt-4",
            "max_tokens": 4000,
            "temperature": 0.7
        },
        "database": {
            "url": "${DATABASE_URL}",
            "echo": False
        },
        "bot": {
            "name": "LIMP",
            "url": "${BOT_URL}",
            "system_prompts": [
                "You are a helpful AI assistant.",
                "Today is ${today}",
                "Environment: ${ENVIRONMENT}"
            ]
        },
        "external_systems": [
            {
                "name": "primary-system",
                "primary": True,
                "oauth2": {
                    "client_id": "${CLIENT_ID}",
                    "client_secret": "${CLIENT_SECRET}",
                    "authorization_url": "https://example.com/oauth/authorize",
                    "token_url": "https://example.com/oauth/token"
                },
                "openapi_spec": "https://example.com/api/openapi.json",
                "base_url": "https://example.com/api"
            }
        ],
        "im_platforms": [
            {
                "platform": "slack",
                "app_id": "${SLACK_APP_ID}",
                "client_id": "${SLACK_CLIENT_ID}",
                "client_secret": "${SLACK_CLIENT_SECRET}",
                "signing_secret": "${SLACK_SIGNING_SECRET}"
            }
        ],
        "admin": {
            "enabled": True,
            "username": "${ADMIN_USERNAME}",
            "password": "${ADMIN_PASSWORD}"
        }
    }
    
    # Set all environment variables
    test_vars = {
        'OPENAI_API_KEY': 'test-openai-key',
        'DATABASE_URL': 'sqlite:///test.db',
        'BOT_URL': 'https://test-bot.example.com',
        'ENVIRONMENT': 'test',
        'CLIENT_ID': 'test-client-id',
        'CLIENT_SECRET': 'test-client-secret',
        'SLACK_APP_ID': 'test-slack-app-id',
        'SLACK_CLIENT_ID': 'test-slack-client-id',
        'SLACK_CLIENT_SECRET': 'test-slack-client-secret',
        'SLACK_SIGNING_SECRET': 'test-slack-signing-secret',
        'ADMIN_USERNAME': 'test-admin',
        'ADMIN_PASSWORD': 'test-password'
    }
    
    for key, value in test_vars.items():
        os.environ[key] = value
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        # Test LLM configuration
        assert config.llm.api_key == 'test-openai-key'
        assert config.llm.model == 'gpt-4'
        
        # Test database configuration
        assert config.database.url == 'sqlite:///test.db'
        
        # Test bot configuration
        assert config.bot.name == 'LIMP'
        assert config.bot.url == 'https://test-bot.example.com'
        assert len(config.bot.system_prompts) == 3
        assert config.bot.system_prompts[0] == 'You are a helpful AI assistant.'
        assert 'Today is' in config.bot.system_prompts[1]
        assert config.bot.system_prompts[2] == 'Environment: test'
        
        # Test external systems
        assert len(config.external_systems) == 1
        assert config.external_systems[0].name == 'primary-system'
        assert config.external_systems[0].primary is True
        assert config.external_systems[0].oauth2.client_id == 'test-client-id'
        assert config.external_systems[0].oauth2.client_secret == 'test-client-secret'
        
        # Test IM platforms
        assert len(config.im_platforms) == 1
        assert config.im_platforms[0].platform == 'slack'
        assert config.im_platforms[0].app_id == 'test-slack-app-id'
        
        # Test admin configuration
        assert config.admin.enabled is True
        assert config.admin.username == 'test-admin'
        assert config.admin.password == 'test-password'
        
    finally:
        Path(config_path).unlink()
        # Clean up all environment variables
        for key in test_vars.keys():
            if key in os.environ:
                del os.environ[key]


def test_variable_substitution_edge_cases():
    """Test edge cases for variable substitution."""
    # Test empty variable name
    result = substitute_variables("${}")
    assert result == ""
    
    # Test variable with spaces
    result = substitute_variables("${ VAR_WITH_SPACES }")
    assert result == ""
    
    # Test nested braces (this is a complex case that may not be fully supported)
    result = substitute_variables("${${NESTED}}")
    # The result should not contain the original pattern
    assert "${" not in result
    
    # Test variable at start and end
    result = substitute_variables("${START}middle${END}")
    assert result == "middle"
    
    # Test multiple same variables
    result = substitute_variables("${SAME} and ${SAME}")
    assert result == " and "
    
    # Test variable with special characters
    result = substitute_variables("${VAR-WITH-DASH}")
    assert result == ""
    
    # Test variable with underscores
    result = substitute_variables("${VAR_WITH_UNDERSCORES}")
    assert result == ""


def test_variable_substitution_performance():
    """Test variable substitution performance with many variables."""
    # Create a string with many variables
    many_vars = " ".join([f"${{VAR_{i}}}" for i in range(100)])
    
    # This should not raise an exception and should complete quickly
    result = substitute_variables(many_vars)
    assert isinstance(result, str)
    # All variables should be substituted (to empty strings since they don't exist)
    assert "${" not in result


def test_variable_substitution_with_environment_priority():
    """Test that environment variables take priority over .env file variables."""
    # Create a temporary .env file
    env_content = "TEST_VAR=dotenv_value\n"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(env_content)
        env_path = f.name
    
    try:
        # Set environment variable (should take priority over .env)
        os.environ['TEST_VAR'] = 'env_value'
        
        # Initialize environment config with the .env file
        from limp.config.config import EnvironmentConfig
        env_config = EnvironmentConfig(env_path)
        
        # Test that environment value takes priority
        result = substitute_variables("Value: ${TEST_VAR}", env_config)
        assert result == "Value: env_value"
        
    finally:
        Path(env_path).unlink()
        # Clean up environment variable
        if 'TEST_VAR' in os.environ:
            del os.environ['TEST_VAR']


def test_variable_substitution_priority_order():
    """Test the complete priority order: environment > .env > built-in > None."""
    # Create a temporary .env file
    env_content = "PRIORITY_VAR=dotenv_value\n"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(env_content)
        env_path = f.name
    
    try:
        # Set environment variable
        os.environ['PRIORITY_VAR'] = 'env_value'
        
        # Initialize environment config with the .env file
        from limp.config.config import EnvironmentConfig
        env_config = EnvironmentConfig(env_path)
        
        # Test environment priority (should win)
        result = substitute_variables("Environment: ${PRIORITY_VAR}", env_config)
        assert result == "Environment: env_value"
        
        # Test .env priority when no environment variable
        del os.environ['PRIORITY_VAR']
        # Create a new env_config to ensure .env file is loaded fresh
        env_config_fresh = EnvironmentConfig(env_path)
        result = substitute_variables("Dotenv: ${PRIORITY_VAR}", env_config_fresh)
        assert result == "Dotenv: dotenv_value"
        
        # Test environment priority over built-in
        os.environ['today'] = '2023-01-01'
        result = substitute_variables("Env today: ${today}", env_config)
        assert result == "Env today: 2023-01-01"
        
        # Test built-in priority over missing
        del os.environ['today']
        result = substitute_variables("Built-in today: ${today}", env_config)
        assert "Built-in today:" in result
        assert result != "Built-in today: ${today}"
        
        # Test missing variable
        result = substitute_variables("Missing: ${MISSING_VAR}", env_config)
        assert result == "Missing: "
        
    finally:
        Path(env_path).unlink()
        # Clean up environment variables
        if 'PRIORITY_VAR' in os.environ:
            del os.environ['PRIORITY_VAR']
        if 'today' in os.environ:
            del os.environ['today']


def test_load_config_with_dotenv_file():
    """Test loading configuration with .env file variable substitution."""
    # Create a temporary .env file
    env_content = "OPENAI_API_KEY=dotenv-api-key\nDATABASE_URL=sqlite:///dotenv.db\n"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
        f.write(env_content)
        env_path = f.name
    
    try:
        config_data = {
            "llm": {
                "api_key": "${OPENAI_API_KEY}",
                "model": "gpt-4"
            },
            "database": {
                "url": "${DATABASE_URL}"
            }
        }
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(config_data, f)
            config_path = f.name
        
        try:
            # Initialize environment config with the .env file
            from limp.config.config import EnvironmentConfig
            env_config = EnvironmentConfig(env_path)
            
            config = load_config(config_path, env_config)
            
            # Should use .env values (since no environment variables are set)
            assert config.llm.api_key == 'dotenv-api-key'
            assert config.database.url == 'sqlite:///dotenv.db'
            
        finally:
            Path(config_path).unlink()
            
    finally:
        Path(env_path).unlink()
