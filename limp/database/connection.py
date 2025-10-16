"""
Database connection and session management.
"""

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from typing import Any, Generator, Tuple
import logging

from ..config import DatabaseConfig
from ..models.base import Base

logger = logging.getLogger(__name__)

# Global engine variable
_engine = None


def get_database_url(config: DatabaseConfig) -> str:
    """Get database URL from configuration."""
    return config.url


def create_engine(config: DatabaseConfig) -> Tuple[Any, str]:
    """Create SQLAlchemy engine."""
    global _engine
    import os
    
    database_url = get_database_url(config)
    
    # Get connection timeout from environment
    connection_timeout = int(os.getenv("DATABASE_CONNECTION_TIMEOUT", "30"))
    
    logger.debug(f"Creating database engine with URL: {database_url}")
    
    if database_url.startswith("sqlite"):
        _engine = sa_create_engine(
            database_url,
            echo=config.echo,
            poolclass=StaticPool,
            connect_args={"check_same_thread": False}
        )
    else:
        connect_args = {}
        if database_url.startswith("postgresql"):
            connect_args.update({
                "connect_timeout": connection_timeout,
                "application_name": "limp",
                "sslmode": "prefer",  # Try SSL first, fallback to non-SSL
                "gssencmode": "disable",  # Disable GSSAPI encryption
            })
        
        # Add pool timeout to prevent hanging
        pool_timeout = int(os.getenv("DATABASE_POOL_TIMEOUT", "30"))
        pool_recycle = int(os.getenv("DATABASE_POOL_RECYCLE", "3600"))  # 1 hour
        
        _engine = sa_create_engine(
            database_url,
            echo=config.echo,
            connect_args=connect_args,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=True  # Verify connections before use
        )
    
    return _engine, database_url


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


def init_database(engine, original_database_url=None):
    """Initialize database tables using Alembic migrations."""
    import time
    import os
    
    # Configuration for retry logic
    max_attempts = int(os.getenv("DATABASE_INIT_MAX_ATTEMPTS", "5"))
    retry_delay = int(os.getenv("DATABASE_INIT_RETRY_DELAY", "10"))  # seconds
    connection_timeout = int(os.getenv("DATABASE_CONNECTION_TIMEOUT", "30"))  # seconds
    
    logger.info(f"Database initialization: max_attempts={max_attempts}, retry_delay={retry_delay}s, timeout={connection_timeout}s")
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"Database initialization attempt {attempt}/{max_attempts}")
            
            # Use Alembic migrations instead of create_all
            from alembic.config import Config as AlembicConfig
            from alembic import command

            if engine.url.database == ':memory:':
                Base.metadata.create_all(bind=engine)
                logger.info("Created in-memory database tables successfully")
                return  # Success, exit the retry loop
            else:        
                logger.info(f"Initializing database with URL: {engine.url}")
                alembic_cfg = AlembicConfig("alembic.ini")
                
                # CRITICAL: Use the original database URL, not the sanitized engine.url
                # This ensures Alembic uses the real password, not the sanitized one
                alembic_database_url = original_database_url or str(engine.url)
                alembic_cfg.set_main_option("sqlalchemy.url", alembic_database_url)
                
                # Also set it in the alembic section
                alembic_cfg.set_section_option("alembic", "sqlalchemy.url", alembic_database_url)
                
                # Verify the URL was set correctly
                final_url = alembic_cfg.get_main_option("sqlalchemy.url")
                logger.debug(f"Alembic will use URL: {final_url}")
                
                # Run migrations with the correct URL
                command.upgrade(alembic_cfg, "head")
                logger.info("Database migrations applied successfully")
                return  # Success, exit the retry loop
                
        except Exception as e:
            logger.error(f"Database initialization attempt {attempt}/{max_attempts} failed: {e}")
            logger.debug(f"Engine URL was: {engine.url}")
            
            if attempt < max_attempts:
                # Progressive backoff
                delay = (attempt ** 2) * retry_delay
                logger.info(f"Retrying in {delay} seconds (progressive backoff: attempt {attempt}, delaying for {delay}s)...")
                time.sleep(delay)
            else:
                logger.error(f"Database initialization failed after {max_attempts} attempts")
                logger.error("Container will exit to prevent infinite restart loops")
                raise RuntimeError(f"Database initialization failed after {max_attempts} attempts. Last error: {e}")
    
    # This should never be reached due to the raise above, but just in case
    raise RuntimeError("Database initialization failed - unexpected end of retry loop")