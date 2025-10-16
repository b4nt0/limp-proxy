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
    import os
    
    database_url = get_database_url(config)
    
    # Get connection timeout from environment
    connection_timeout = int(os.getenv("DATABASE_CONNECTION_TIMEOUT", "30"))
    
    import urllib.parse
    parsed_url = urllib.parse.urlparse(database_url)
    if parsed_url.password:
        masked_url = database_url.replace(parsed_url.password, "***")
        logger.info(f"Creating database engine with URL: {masked_url}")
    else:
        logger.info(f"Creating database engine with URL: {database_url}")
    
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
                "application_name": "limp"
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
                
                # CRITICAL: Override the database URL in Alembic configuration
                # This ensures Alembic uses the same database as our application
                database_url = str(engine.url)
                alembic_cfg.set_main_option("sqlalchemy.url", database_url)
                
                # Also set it in the alembic section to be absolutely sure
                alembic_cfg.set_section_option("alembic", "sqlalchemy.url", database_url)
                
                # Verify the URL was set correctly
                final_url = alembic_cfg.get_main_option("sqlalchemy.url")
                logger.info(f"Alembic will use URL: {final_url}")
                
                # Run migrations with the correct URL
                command.upgrade(alembic_cfg, "head")
                logger.info("Database migrations applied successfully")
                return  # Success, exit the retry loop
                
        except Exception as e:
            logger.error(f"Database initialization attempt {attempt}/{max_attempts} failed: {e}")
            logger.error(f"Engine URL was: {engine.url}")
            
            if attempt < max_attempts:
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Database initialization failed after {max_attempts} attempts")
                logger.error("Container will exit to prevent infinite restart loops")
                raise RuntimeError(f"Database initialization failed after {max_attempts} attempts. Last error: {e}")
    
    # This should never be reached due to the raise above, but just in case
    raise RuntimeError("Database initialization failed - unexpected end of retry loop")