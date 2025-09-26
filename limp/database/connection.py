"""
Database connection and session management.
"""

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Generator
import logging

from ..config import DatabaseConfig
from ..models.base import Base

logger = logging.getLogger(__name__)

# Global engine variable
_engine = None


def get_database_url(config: DatabaseConfig) -> str:
    """Get database URL from configuration."""
    return config.url


def create_engine(config: DatabaseConfig):
    """Create SQLAlchemy engine."""
    global _engine
    database_url = get_database_url(config)
    
    # Special handling for SQLite
    if database_url.startswith("sqlite"):
        _engine = sa_create_engine(
            database_url,
            echo=config.echo,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
    else:
        _engine = sa_create_engine(
            database_url,
            echo=config.echo
        )
    
    return _engine


def get_session() -> Generator[Session, None, None]:
    """Get database session - FastAPI dependency."""
    if _engine is None:
        raise RuntimeError("Database engine not initialized. Call create_engine first.")
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def init_database(engine):
    """Initialize database tables."""
    try:
        # Create all tables
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise