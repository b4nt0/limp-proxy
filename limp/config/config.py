"""
Configuration management for LIMP system.
"""

import os
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field
try:
    from dotenv import load_dotenv
except ImportError:
    # Fallback for when python-dotenv is not installed
    def load_dotenv(path: Optional[str] = None) -> None:
        pass


class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = Field(default="sqlite:///./limp.db")
    echo: bool = Field(default=False)


class LLMConfig(BaseModel):
    """LLM configuration."""
    provider: str = Field(default="openai")
    api_key: str
    model: str = Field(default="gpt-4")
    base_url: Optional[str] = None
    max_tokens: int = Field(default=4000)
    temperature: float = Field(default=0.7)


class OAuth2Config(BaseModel):
    """OAuth2 configuration for external systems."""
    client_id: str
    client_secret: str
    authorization_url: str
    token_url: str
    scope: Optional[str] = None
    test_endpoint: Optional[str] = None  # Optional endpoint for token validation


class ExternalSystemConfig(BaseModel):
    """External system configuration."""
    name: str
    oauth2: OAuth2Config
    openapi_spec: str  # URL or file path to OpenAPI spec
    base_url: str
    primary: bool = Field(default=False)


class IMPlatformConfig(BaseModel):
    """Instant messaging platform configuration."""
    platform: str  # 'slack' or 'teams'
    app_id: str
    client_id: str
    client_secret: str
    signing_secret: Optional[str] = None
    verification_token: Optional[str] = None
    # Teams-specific conversation settings
    conversation_timeout_hours: Optional[int] = Field(default=8, description="Hours after which a new conversation starts in Teams DMs")


class AdminConfig(BaseModel):
    """Admin interface configuration."""
    enabled: bool = Field(default=False)
    username: Optional[str] = None
    password: Optional[str] = None


class AlertConfig(BaseModel):
    """Alert configuration."""
    enabled: bool = Field(default=False)
    webhook_url: Optional[str] = None


class LoggingConfig(BaseModel):
    """Logging configuration."""
    level: str = Field(default="INFO", description="Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)")


class BotConfig(BaseModel):
    """Bot configuration."""
    name: str = Field(default="LIMP", description="Display name of this LIMP instance")
    url: Optional[str] = Field(default=None, description="URL where LIMP is deployed")
    system_prompts: List[str] = Field(default_factory=list, description="List of system prompts to include in LLM conversations")


class Config(BaseModel):
    """Main configuration model."""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig
    external_systems: List[ExternalSystemConfig] = Field(default_factory=list)
    im_platforms: List[IMPlatformConfig] = Field(default_factory=list)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    bot: BotConfig = Field(default_factory=BotConfig)
    max_iterations: int = Field(default=10)
    prompts_dir: str = Field(default="./prompts")
    context_files_dir: str = Field(default="./context")
    
    def get_primary_system(self) -> Optional[ExternalSystemConfig]:
        """Get the primary external system, if any."""
        primary_systems = [system for system in self.external_systems if system.primary]
        return primary_systems[0] if primary_systems else None
    
    def assign_primary_system(self, system_name: str) -> None:
        """Assign a system as primary by name. Clears any existing primary system."""
        # First, clear all existing primary flags
        for system in self.external_systems:
            system.primary = False
        
        # Find and set the specified system as primary
        for system in self.external_systems:
            if system.name == system_name:
                system.primary = True
                return
        
        # If we get here, the system wasn't found
        available_names = [system.name for system in self.external_systems]
        raise ValueError(f"External system '{system_name}' not found. Available systems: {available_names}")
    
    def get_im_platform_by_key(self, platform_key: str) -> IMPlatformConfig:
        """Get IM platform configuration by platform key (e.g., 'slack', 'teams')."""
        for platform in self.im_platforms:
            if platform.platform.lower() == platform_key.lower():
                return platform
        
        # If we get here, the platform wasn't found
        available_platforms = [platform.platform for platform in self.im_platforms]
        raise ValueError(f"IM platform '{platform_key}' not found. Available platforms: {available_platforms}")


def load_config(config_path: str) -> Config:
    """Load configuration from YAML file."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_file, 'r') as f:
        config_data = yaml.safe_load(f)
    
    config = Config(**config_data)
    
    # Sanity check: ensure at most one primary external system
    primary_systems = [system for system in config.external_systems if system.primary]
    if len(primary_systems) > 1:
        primary_names = [system.name for system in primary_systems]
        raise ValueError(f"Multiple primary external systems found: {primary_names}. Only one primary system is allowed.")
    
    return config


# Global config variable
_config: Optional[Config] = None


def get_config() -> Config:
    """Get the global configuration."""
    global _config
    if _config is None:
        raise RuntimeError("Configuration not initialized. Call load_config first.")
    return _config


def set_config(config: Config) -> None:
    """Set the global configuration."""
    global _config
    _config = config


class EnvironmentConfig:
    """Environment configuration manager with fallback support."""
    
    def __init__(self, env_file_path: Optional[str] = None):
        """
        Initialize environment configuration.
        
        Args:
            env_file_path: Path to .env file. If None, will look for .env in current directory.
        """
        self.env_file_path = env_file_path or ".env"
        self._load_env_file()
    
    def _load_env_file(self) -> None:
        """Load environment variables from .env file if it exists."""
        env_path = Path(self.env_file_path)
        if env_path.exists():
            load_dotenv(env_path)
    
    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get environment variable with fallback support.
        
        Priority order:
        1. Environment variable (takes priority)
        2. .env file variable
        3. Default value
        
        Args:
            key: Environment variable name
            default: Default value if not found in environment or .env
            
        Returns:
            Environment variable value or default
        """
        # First check environment variables (highest priority)
        value = os.getenv(key)
        if value is not None:
            return value
        
        # If not found in environment, .env file is already loaded by load_dotenv
        # So we can check again (this will include .env values)
        value = os.getenv(key)
        if value is not None:
            return value
        
        # Return default if not found anywhere
        return default
    
    def get_config_path(self) -> str:
        """
        Get configuration file path with environment support.
        
        Returns:
            Path to configuration file
        """
        return self.get("LIMP_CONFIG", default="config.yaml")


# Global environment config instance
_env_config: Optional[EnvironmentConfig] = None


def get_env_config() -> EnvironmentConfig:
    """Get the global environment configuration."""
    global _env_config
    if _env_config is None:
        _env_config = EnvironmentConfig()
    return _env_config


def initialize_env_config(env_file_path: Optional[str] = None) -> EnvironmentConfig:
    """Initialize environment configuration with optional .env file path."""
    global _env_config
    _env_config = EnvironmentConfig(env_file_path)
    return _env_config
