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
    assert result is None
    
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
            "api_key": "test-key",  # Provide required field
            "model": "gpt-4",
            "context_window_size": "${MISSING_CONTEXT_WINDOW_SIZE}"  # Optional field that should be omitted
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
        
        # Required field should be present
        assert config.llm.api_key == "test-key"
        assert config.llm.model == "gpt-4"
        # Missing optional variable should be omitted, allowing Pydantic default
        assert config.llm.context_window_size is None
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
    assert result is None
    
    # Test variable with spaces
    result = substitute_variables("${ VAR_WITH_SPACES }")
    assert result is None
    
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
    assert result is None
    
    # Test variable with underscores
    result = substitute_variables("${VAR_WITH_UNDERSCORES}")
    assert result is None


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


def test_substitute_variables_with_default_values():
    """Test variable substitution with default values."""
    # Test with default value when variable is missing
    result = substitute_variables("Value: ${MISSING_VAR|default_value}")
    assert result == "Value: default_value"
    
    # Test with default value when variable exists in environment
    os.environ['EXISTING_VAR'] = 'env_value'
    try:
        result = substitute_variables("Value: ${EXISTING_VAR|default_value}")
        assert result == "Value: env_value"  # Environment should take priority
    finally:
        del os.environ['EXISTING_VAR']
    
    # Test with multiple variables with defaults
    result = substitute_variables("First: ${MISSING1|first_default}, Second: ${MISSING2|second_default}")
    assert result == "First: first_default, Second: second_default"


def test_substitute_variables_default_value_priority():
    """Test that environment variables take priority over default values."""
    # Set environment variable
    os.environ['PRIORITY_VAR'] = 'env_value'
    
    try:
        # Environment should take priority over default
        result = substitute_variables("Value: ${PRIORITY_VAR|default_value}")
        assert result == "Value: env_value"
        
        # Test with .env file priority over default
        from limp.config.config import EnvironmentConfig
        env_config = EnvironmentConfig()
        # Mock the .env file behavior by setting a value in env_config
        # This is a bit tricky since we need to test the priority order
        result = substitute_variables("Value: ${PRIORITY_VAR|default_value}", env_config)
        assert result == "Value: env_value"  # Environment still takes priority
        
    finally:
        del os.environ['PRIORITY_VAR']


def test_substitute_variables_default_value_with_builtin():
    """Test default value fallback with built-in variables."""
    # Test that built-in variables take priority over defaults
    result = substitute_variables("Date: ${today|2023-01-01}")
    assert "Date:" in result
    assert result != "Date: 2023-01-01"  # Should use built-in today, not default
    
    # Test with missing built-in variable (should use default)
    result = substitute_variables("Missing: ${nonexistent_builtin|default_value}")
    assert result == "Missing: default_value"


def test_substitute_variables_default_value_data_types():
    """Test default values with different data types."""
    # String default
    result = substitute_variables("String: ${MISSING_STR|hello}")
    assert result == "String: hello"
    
    # Number default (as string)
    result = substitute_variables("Number: ${MISSING_NUM|42}")
    assert result == "Number: 42"
    
    # Boolean default (as string)
    result = substitute_variables("Boolean: ${MISSING_BOOL|true}")
    assert result == "Boolean: true"
    
    # Float default (as string)
    result = substitute_variables("Float: ${MISSING_FLOAT|3.14}")
    assert result == "Float: 3.14"
    
    # Empty string default
    result = substitute_variables("Empty: ${MISSING_EMPTY|}")
    assert result == "Empty: "
    
    # None default (as string)
    result = substitute_variables("None: ${MISSING_NONE|None}")
    assert result == "None: None"


def test_substitute_variables_default_value_edge_cases():
    """Test edge cases for default value syntax."""
    # Test with pipe in default value
    result = substitute_variables("Pipe: ${MISSING|value|with|pipes}")
    assert result == "Pipe: value|with|pipes"
    
    # Test with empty variable name and default
    result = substitute_variables("Empty: ${|default}")
    assert result == "Empty: default"
    
    # Test with spaces around pipe
    result = substitute_variables("Spaces: ${MISSING | default_value}")
    assert result == "Spaces: default_value"
    
    # Test with multiple pipes (should split on first one)
    result = substitute_variables("Multiple: ${MISSING|first|second}")
    assert result == "Multiple: first|second"


def test_substitute_variables_default_value_mixed_syntax():
    """Test mixing default and non-default variable syntax."""
    # Set one environment variable
    os.environ['EXISTING_VAR'] = 'env_value'
    
    try:
        result = substitute_variables("Existing: ${EXISTING_VAR}, Missing: ${MISSING_VAR|default}, Today: ${today}")
        assert "Existing: env_value" in result
        assert "Missing: default" in result
        assert "Today:" in result
        assert "${EXISTING_VAR}" not in result
        assert "${MISSING_VAR" not in result
        assert "${today}" not in result
        
    finally:
        del os.environ['EXISTING_VAR']


def test_load_config_with_default_values():
    """Test loading configuration with default value substitution."""
    config_data = {
        "llm": {
            "api_key": "${OPENAI_API_KEY|default-api-key}",
            "model": "gpt-4",
            "max_tokens": 4000
        },
        "database": {
            "url": "${DATABASE_URL|sqlite:///default.db}"
        },
        "bot": {
            "name": "Test Bot",
            "url": "${BOT_URL|https://default.example.com}",
            "system_prompts": [
                "You are a helpful assistant.",
                "Environment: ${ENVIRONMENT|development}"
            ]
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        # Mock the environment variable lookup to ensure it returns None
        import unittest.mock
        with unittest.mock.patch('os.getenv', return_value=None):
            config = load_config(config_path)
            
            # Should use default values since no environment variables are set
            assert config.llm.api_key == 'default-api-key'
            assert config.database.url == 'sqlite:///default.db'
            assert config.bot.name == 'Test Bot'
            assert config.bot.url == 'https://default.example.com'
            assert len(config.bot.system_prompts) == 2
            assert config.bot.system_prompts[0] == 'You are a helpful assistant.'
            assert config.bot.system_prompts[1] == 'Environment: development'
        
    finally:
        Path(config_path).unlink()


def test_load_config_with_default_values_and_environment():
    """Test loading configuration with default values when environment variables exist."""
    config_data = {
        "llm": {
            "api_key": "${OPENAI_API_KEY|default-api-key}",
            "model": "gpt-4"
        },
        "database": {
            "url": "${DATABASE_URL|sqlite:///default.db}"
        }
    }
    
    # Set environment variables
    os.environ['OPENAI_API_KEY'] = 'env-api-key'
    os.environ['DATABASE_URL'] = 'sqlite:///env.db'
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        # Should use environment values, not defaults
        assert config.llm.api_key == 'env-api-key'
        assert config.database.url == 'sqlite:///env.db'
        
    finally:
        Path(config_path).unlink()
        # Clean up environment variables
        del os.environ['OPENAI_API_KEY']
        del os.environ['DATABASE_URL']


def test_load_config_with_default_values_complex():
    """Test complex default value scenarios in configuration."""
    config_data = {
        "llm": {
            "api_key": "${OPENAI_API_KEY|default-key}",
            "model": "gpt-4",
            "max_tokens": 4000,
            "temperature": 0.7
        },
        "database": {
            "url": "${DATABASE_URL|sqlite:///default.db}",
            "echo": False
        },
        "bot": {
            "name": "LIMP",
            "url": "${BOT_URL|https://default.example.com}",
            "system_prompts": [
                "You are a helpful AI assistant.",
                "Today is ${today|2023-01-01}",
                "Environment: ${ENVIRONMENT|production}"
            ]
        },
        "external_systems": [
            {
                "name": "primary-system",
                "primary": True,
                "oauth2": {
                    "client_id": "${CLIENT_ID|default-client-id}",
                    "client_secret": "${CLIENT_SECRET|default-client-secret}",
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
                "app_id": "${SLACK_APP_ID|default-slack-app-id}",
                "client_id": "${SLACK_CLIENT_ID|default-slack-client-id}",
                "client_secret": "${SLACK_CLIENT_SECRET|default-slack-client-secret}",
                "signing_secret": "${SLACK_SIGNING_SECRET|default-slack-signing-secret}"
            }
        ],
        "admin": {
            "enabled": True,
            "username": "${ADMIN_USERNAME|default-admin}",
            "password": "${ADMIN_PASSWORD|default-password}"
        }
    }
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        yaml.dump(config_data, f)
        config_path = f.name
    
    try:
        config = load_config(config_path)
        
        # Test LLM configuration with defaults
        assert config.llm.api_key == 'default-key'
        assert config.llm.model == 'gpt-4'
        
        # Test database configuration with defaults
        assert config.database.url == 'sqlite:///default.db'
        
        # Test bot configuration with defaults
        assert config.bot.name == 'LIMP'
        assert config.bot.url == 'https://default.example.com'
        assert len(config.bot.system_prompts) == 3
        assert config.bot.system_prompts[0] == 'You are a helpful AI assistant.'
        assert 'Today is' in config.bot.system_prompts[1]  # Should use built-in today, not default
        assert config.bot.system_prompts[2] == 'Environment: production'
        
        # Test external systems with defaults
        assert len(config.external_systems) == 1
        assert config.external_systems[0].name == 'primary-system'
        assert config.external_systems[0].primary is True
        assert config.external_systems[0].oauth2.client_id == 'default-client-id'
        assert config.external_systems[0].oauth2.client_secret == 'default-client-secret'
        
        # Test IM platforms with defaults
        assert len(config.im_platforms) == 1
        assert config.im_platforms[0].platform == 'slack'
        assert config.im_platforms[0].app_id == 'default-slack-app-id'
        
        # Test admin configuration with defaults
        assert config.admin.enabled is True
        assert config.admin.username == 'default-admin'
        assert config.admin.password == 'default-password'
        
    finally:
        Path(config_path).unlink()


def test_substitute_variables_default_value_backward_compatibility():
    """Test that default value syntax doesn't break existing functionality."""
    # Test that existing syntax still works
    result = substitute_variables("Value: ${MISSING_VAR}")
    assert result == "Value: "
    
    # Test that existing syntax with environment variables still works
    os.environ['EXISTING_VAR'] = 'env_value'
    try:
        result = substitute_variables("Value: ${EXISTING_VAR}")
        assert result == "Value: env_value"
    finally:
        del os.environ['EXISTING_VAR']
    
    # Test that built-in variables still work
    result = substitute_variables("Date: ${today}")
    assert "Date:" in result
    assert result != "Date: ${today}"


def test_substitute_variables_default_value_performance():
    """Test performance with many default value variables."""
    # Create a string with many variables with defaults
    many_vars = " ".join([f"${{VAR_{i}|default_{i}}}" for i in range(100)])
    
    # This should not raise an exception and should complete quickly
    result = substitute_variables(many_vars)
    assert isinstance(result, str)
    # All variables should be substituted to their default values
    assert "${" not in result
    # Check that defaults are present
    assert "default_0" in result
    assert "default_99" in result


def test_substitute_variables_empty_string_handling():
    """Test that empty string substitutions are handled properly for Pydantic validation."""
    # Test that empty string substitution returns None
    result = substitute_variables("${MISSING_VAR}")
    assert result is None
    
    # Test that empty string with default returns the default
    result = substitute_variables("${MISSING_VAR|default}")
    assert result == "default"
    
    # Test that empty string with empty default returns None
    result = substitute_variables("${MISSING_VAR|}")
    assert result is None


def test_load_config_with_empty_variables():
    """Test loading configuration with empty variables that should be omitted."""
    config_data = {
        "llm": {
            "api_key": "test-key",
            "model": "gpt-4",
            "max_tokens": 4000,
            "temperature": 0.7,
            "context_window_size": "${MISSING_CONTEXT_WINDOW_SIZE}"  # This should be omitted
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
        
        # The context_window_size should be omitted, allowing Pydantic to use its default
        assert config.llm.api_key == "test-key"
        assert config.llm.model == "gpt-4"
        assert config.llm.max_tokens == 4000
        assert config.llm.temperature == 0.7
        # context_window_size should be None (Pydantic default)
        assert config.llm.context_window_size is None
        
    finally:
        Path(config_path).unlink()


def test_load_config_with_empty_variables_and_defaults():
    """Test loading configuration with empty variables that have default values."""
    config_data = {
        "llm": {
            "api_key": "test-key",
            "model": "gpt-4",
            "max_tokens": 4000,
            "temperature": 0.7,
            "context_window_size": "${MISSING_CONTEXT_WINDOW_SIZE|8192}"  # Should use default
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
        
        # The context_window_size should use the default value
        assert config.llm.api_key == "test-key"
        assert config.llm.model == "gpt-4"
        assert config.llm.max_tokens == 4000
        assert config.llm.temperature == 0.7
        assert config.llm.context_window_size == 8192
        
    finally:
        Path(config_path).unlink()


def test_load_config_with_mixed_empty_and_valid_variables():
    """Test loading configuration with mix of empty and valid variables."""
    config_data = {
        "llm": {
            "api_key": "test-key",  # Required field with actual value
            "model": "gpt-4",
            "max_tokens": "${OPENAI_MAX_TOKENS|4000}",  # Should use default
            "temperature": 0.7,
            "context_window_size": "${MISSING_CONTEXT_WINDOW_SIZE}"  # Should be omitted
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
        
        # api_key should be present
        assert config.llm.api_key == "test-key"
        assert config.llm.model == "gpt-4"
        assert config.llm.max_tokens == 4000
        assert config.llm.temperature == 0.7
        # context_window_size should be omitted, allowing Pydantic to use its default
        assert config.llm.context_window_size is None
        
    finally:
        Path(config_path).unlink()
