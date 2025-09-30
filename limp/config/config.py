"""
Configuration management for LIMP system.
"""

import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field


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
    redirect_uri: str
    scope: Optional[str] = None


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


class AdminConfig(BaseModel):
    """Admin interface configuration."""
    enabled: bool = Field(default=False)
    username: Optional[str] = None
    password: Optional[str] = None


class AlertConfig(BaseModel):
    """Alert configuration."""
    enabled: bool = Field(default=False)
    webhook_url: Optional[str] = None


class Config(BaseModel):
    """Main configuration model."""
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    llm: LLMConfig
    external_systems: List[ExternalSystemConfig] = Field(default_factory=list)
    im_platforms: List[IMPlatformConfig] = Field(default_factory=list)
    admin: AdminConfig = Field(default_factory=AdminConfig)
    alerts: AlertConfig = Field(default_factory=AlertConfig)
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
