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
    """Initialize database tables using Alembic migrations."""
    try:
        # Use Alembic migrations instead of create_all
        from alembic.config import Config as AlembicConfig
        from alembic import command

        if engine.url.database == ':memory:':
            Base.metadata.create_all(bind=engine)
            logger.info("Created in-memory database tables successfully")
        else:        
            alembic_cfg = AlembicConfig("alembic.ini")
            # Set the database URL from the engine to override the hardcoded one in alembic.ini
            alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
            command.upgrade(alembic_cfg, "head")
            logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.error(f"Failed to apply database migrations: {e}")
        raise