"""
Pytest configuration and fixtures.
"""

import pytest
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from limp.database import init_database
from limp.models.base import Base
from limp.models.slack_organization import SlackOrganization  # Import to ensure table is created
from limp.config import Config, DatabaseConfig, LLMConfig
from limp.api.main import create_app

# Set fast test timeouts for all tests
os.environ.setdefault("DATABASE_INIT_MAX_ATTEMPTS", "1")
os.environ.setdefault("DATABASE_INIT_RETRY_DELAY", "1")
os.environ.setdefault("DATABASE_CONNECTION_TIMEOUT", "5")
os.environ.setdefault("DATABASE_POOL_TIMEOUT", "5")


@pytest.fixture
def test_db_url():
    """Test database URL."""
    return "sqlite:///:memory:"


@pytest.fixture
def test_engine(test_db_url):
    """Test database engine."""
    engine = create_engine(test_db_url, connect_args={"check_same_thread": False})
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    init_database(engine)
    
    yield engine
    
    # Clean up
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def test_session(test_engine):
    """Test database session."""
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def test_config():
    """Test configuration."""
    from limp.config import AdminConfig, IMPlatformConfig, ExternalSystemConfig, OAuth2Config
    
    return Config(
        database=DatabaseConfig(url="sqlite:///:memory:"),
        llm=LLMConfig(
            api_key="test-api-key",
            model="gpt-4",
            max_tokens=1000,
            temperature=0.7
        ),
        admin=AdminConfig(enabled=True, username="admin", password="admin123"),
        im_platforms=[
            IMPlatformConfig(
                platform="slack",
                app_id="test-app-id",
                client_id="test-client-id",
                client_secret="test-client-secret",
                signing_secret="test-signing-secret"
            ),
            IMPlatformConfig(
                platform="teams",
                app_id="test-app-id",
                client_id="test-client-id",
                client_secret="test-client-secret",
                signing_secret="test-signing-secret"
            ),
        ],
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
        ]
    )


@pytest.fixture
def test_app(test_config):
    """Test FastAPI application."""
    return create_app(test_config)


@pytest.fixture
def test_client(test_app):
    """Test client."""
    return TestClient(test_app)
