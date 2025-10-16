"""
Tests for database initialization with different database types.
"""

import pytest
import tempfile
import os
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from limp.database import init_database, create_engine as limp_create_engine
from limp.config import Config, DatabaseConfig, LLMConfig
from limp.models.base import Base


class TestDatabaseInitialization:
    """Test database initialization with different database configurations."""

    def test_sqlite_initialization(self):
        """Test that SQLite database initialization works correctly."""
        # Create a temporary SQLite database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        try:
            # Create engine with SQLite URL
            db_url = f"sqlite:///{db_path}"
            engine = create_engine(db_url)
            
            # Initialize database
            init_database(engine)
            
            # Verify tables were created by checking if we can query them
            with engine.connect() as conn:
                # Check if alembic_version table exists (created by migrations)
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='alembic_version'"))
                assert result.fetchone() is not None, "Alembic version table should exist"
                
                # Check if our application tables exist
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"))
                assert result.fetchone() is not None, "Users table should exist"
                
        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_postgresql_url_override(self):
        """Test that the database URL is correctly overridden for Alembic migrations."""
        # This test verifies that the fix works by checking the Alembic configuration
        # is updated with the correct database URL
        
        # Set test environment variables to make tests faster
        import os
        original_max_attempts = os.environ.get("DATABASE_INIT_MAX_ATTEMPTS")
        original_retry_delay = os.environ.get("DATABASE_INIT_RETRY_DELAY")
        original_connection_timeout = os.environ.get("DATABASE_CONNECTION_TIMEOUT")
        
        try:
            # Set fast test timeouts
            os.environ["DATABASE_INIT_MAX_ATTEMPTS"] = "1"
            os.environ["DATABASE_INIT_RETRY_DELAY"] = "1"
            os.environ["DATABASE_CONNECTION_TIMEOUT"] = "5"
            
            # Create a test configuration with a PostgreSQL URL
            postgres_url = "postgresql://test:test@localhost:5432/testdb"
            
            # Create engine
            engine = create_engine(postgres_url)
            
            # Track what URL is actually used by Alembic
            original_set_main_option = None
            captured_url = None
            
            try:
                from alembic.config import Config as AlembicConfig
                
                # Mock the set_main_option method to capture calls
                def mock_set_main_option(self, name, value):
                    nonlocal captured_url
                    if name == "sqlalchemy.url":
                        captured_url = value
                    return original_set_main_option(self, name, value)
                
                # Patch the method
                original_set_main_option = AlembicConfig.set_main_option
                AlembicConfig.set_main_option = mock_set_main_option
                
                # This should fail with connection error, but we should see the URL override
                with pytest.raises(Exception):  # Expected to fail due to connection
                    init_database(engine)
                
                # Verify that the correct URL was set (SQLAlchemy may mask the password)
                assert captured_url is not None, "Should have captured a URL"
                assert "postgresql://" in captured_url, f"Expected PostgreSQL URL, got {captured_url}"
                assert "localhost:5432/testdb" in captured_url, f"Expected localhost:5432/testdb in URL, got {captured_url}"
                
            finally:
                # Restore original method
                if original_set_main_option:
                    AlembicConfig.set_main_option = original_set_main_option
                    
        finally:
            # Restore original environment variables
            if original_max_attempts is not None:
                os.environ["DATABASE_INIT_MAX_ATTEMPTS"] = original_max_attempts
            elif "DATABASE_INIT_MAX_ATTEMPTS" in os.environ:
                del os.environ["DATABASE_INIT_MAX_ATTEMPTS"]
                
            if original_retry_delay is not None:
                os.environ["DATABASE_INIT_RETRY_DELAY"] = original_retry_delay
            elif "DATABASE_INIT_RETRY_DELAY" in os.environ:
                del os.environ["DATABASE_INIT_RETRY_DELAY"]
                
            if original_connection_timeout is not None:
                os.environ["DATABASE_CONNECTION_TIMEOUT"] = original_connection_timeout
            elif "DATABASE_CONNECTION_TIMEOUT" in os.environ:
                del os.environ["DATABASE_CONNECTION_TIMEOUT"]

    def test_memory_database_bypass(self):
        """Test that in-memory databases bypass Alembic and use create_all."""
        # Create in-memory SQLite engine
        engine = create_engine("sqlite:///:memory:")
        
        # This should not raise an exception
        init_database(engine)
        
        # Verify tables exist by checking metadata
        with engine.connect() as conn:
            # Check if we can query the users table (should exist)
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            tables = [row[0] for row in result.fetchall()]
            assert 'users' in tables, "Users table should exist in in-memory database"

    def test_database_initialization_with_config(self):
        """Test database initialization using the full application configuration."""
        # Create a temporary SQLite database
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        try:
            # Create configuration
            config = Config(
                database=DatabaseConfig(url=f"sqlite:///{db_path}"),
                llm=LLMConfig(api_key="test-key", model="gpt-4")
            )
            
            # Create engine using the application's create_engine function
            engine = limp_create_engine(config.database)
            
            # Initialize database
            init_database(engine)
            
            # Verify the database was initialized correctly
            with engine.connect() as conn:
                # Check alembic version table
                result = conn.execute(text("SELECT version_num FROM alembic_version"))
                version = result.fetchone()
                assert version is not None, "Alembic version should be recorded"
                
        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_database_url_override_in_alembic_config(self):
        """Test that the database URL override works correctly in Alembic configuration."""
        # This test specifically verifies that our fix correctly overrides
        # the hardcoded SQLite URL in alembic.ini
        
        # Create a temporary database file
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as tmp_file:
            db_path = tmp_file.name
        
        try:
            # Create a test database URL that's different from the hardcoded one
            test_url = f"sqlite:///{db_path}"
            
            # Create engine
            engine = create_engine(test_url)
            
            # Track what URL is actually used by Alembic
            original_set_main_option = None
            captured_calls = []
            
            try:
                from alembic.config import Config as AlembicConfig
                
                # Mock the set_main_option method to capture calls
                def mock_set_main_option(self, name, value):
                    captured_calls.append((name, value))
                    return original_set_main_option(self, name, value)
                
                # Patch the method
                original_set_main_option = AlembicConfig.set_main_option
                AlembicConfig.set_main_option = mock_set_main_option
                
                # This should succeed now that we have a valid database file
                init_database(engine)
                
                # Verify that sqlalchemy.url was set with our test URL
                url_calls = [call for call in captured_calls if call[0] == "sqlalchemy.url"]
                assert len(url_calls) > 0, "Should have called set_main_option for sqlalchemy.url"
                assert url_calls[0][1] == test_url, f"Expected URL {test_url}, got {url_calls[0][1]}"
                
            finally:
                # Restore original method
                if original_set_main_option:
                    AlembicConfig.set_main_option = original_set_main_option
                    
        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)
