#!/usr/bin/env python3
"""
Standalone database connection test script.
Run this inside the container to test the exact same connection as the application.
"""

import os
import sys
import urllib.parse
import logging
from sqlalchemy import create_engine, text
import psycopg2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_psycopg2_direct(database_url):
    """Test direct psycopg2 connection."""
    logger.info("=== Testing Direct psycopg2 Connection ===")
    
    try:
        # Parse the URL
        parsed_url = urllib.parse.urlparse(database_url)
        
        logger.info(f"Connection details:")
        logger.info(f"  Host: {parsed_url.hostname}")
        logger.info(f"  Port: {parsed_url.port}")
        logger.info(f"  Database: {parsed_url.path[1:] if parsed_url.path else 'postgres'}")
        logger.info(f"  User: {parsed_url.username}")
        logger.info(f"  Password length: {len(parsed_url.password) if parsed_url.password else 0}")
        
        # Try direct psycopg2 connection
        conn = psycopg2.connect(
            host=parsed_url.hostname,
            port=parsed_url.port or 5432,
            database=parsed_url.path[1:] if parsed_url.path else 'postgres',
            user=parsed_url.username,
            password=parsed_url.password,
            connect_timeout=10,
            application_name="limp-test-direct"
        )
        
        logger.info("✅ Direct psycopg2 connection successful!")
        
        # Test a simple query
        with conn.cursor() as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            logger.info(f"PostgreSQL version: {version}")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Direct psycopg2 connection failed: {e}")
        return False

def test_sqlalchemy_engine(database_url):
    """Test SQLAlchemy engine connection."""
    logger.info("=== Testing SQLAlchemy Engine Connection ===")
    
    try:
        # Create engine with same parameters as the application
        engine = create_engine(
            database_url,
            echo=True,  # Enable SQL logging
            connect_args={
                "connect_timeout": 30,
                "application_name": "limp-test-sqlalchemy",
                "sslmode": "prefer",
                "gssencmode": "disable"
            },
            pool_timeout=30,
            pool_recycle=3600,
            pool_pre_ping=True
        )
        
        logger.info("✅ SQLAlchemy engine created successfully!")
        
        # Test connection
        with engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.fetchone()[0]
            logger.info(f"PostgreSQL version via SQLAlchemy: {version}")
        
        engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"❌ SQLAlchemy engine connection failed: {e}")
        return False

def test_alembic_connection(database_url):
    """Test Alembic connection (what actually fails in the app)."""
    logger.info("=== Testing Alembic Connection ===")
    
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command
        
        # Create Alembic config
        alembic_cfg = AlembicConfig("alembic.ini")
        
        # Override the database URL (same as in the app)
        alembic_cfg.set_main_option("sqlalchemy.url", database_url)
        alembic_cfg.set_section_option("alembic", "sqlalchemy.url", database_url)
        
        logger.info(f"Alembic will use URL: {alembic_cfg.get_main_option('sqlalchemy.url')}")
        
        # Try to get current revision (this is what fails in the app)
        command.current(alembic_cfg)
        logger.info("✅ Alembic connection successful!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Alembic connection failed: {e}")
        return False

def main():
    """Main test function."""
    import argparse
    
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Test database connection")
    parser.add_argument("--url", "-u", help="Database URL to test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args()
    
    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("🔍 Database Connection Test Script")
    logger.info("=" * 50)
    
    # Get database URL from command line argument or environment variable
    database_url = args.url or os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("❌ No database URL provided!")
        logger.info("Please provide a database URL using one of these methods:")
        logger.info("1. Command line: python test_db_connection.py --url 'postgresql://user:pass@host:5432/db'")
        logger.info("2. Environment variable: DATABASE_URL='postgresql://user:pass@host:5432/db' python test_db_connection.py")
        logger.info("3. Short form: python test_db_connection.py -u 'postgresql://user:pass@host:5432/db'")
        sys.exit(1)
    
    # Mask password in logs
    parsed_url = urllib.parse.urlparse(database_url)
    if parsed_url.password:
        masked_url = database_url.replace(parsed_url.password, "***")
        logger.info(f"Testing connection to: {masked_url}")
    else:
        logger.info(f"Testing connection to: {database_url}")
    
    logger.info("")
    
    # Test 1: Direct psycopg2
    success1 = test_psycopg2_direct(database_url)
    logger.info("")
    
    # Test 2: SQLAlchemy engine
    success2 = test_sqlalchemy_engine(database_url)
    logger.info("")
    
    # Test 3: Alembic connection
    success3 = test_alembic_connection(database_url)
    logger.info("")
    
    # Summary
    logger.info("=== Test Results Summary ===")
    logger.info(f"Direct psycopg2: {'✅ PASS' if success1 else '❌ FAIL'}")
    logger.info(f"SQLAlchemy engine: {'✅ PASS' if success2 else '❌ FAIL'}")
    logger.info(f"Alembic connection: {'✅ PASS' if success3 else '❌ FAIL'}")
    
    if all([success1, success2, success3]):
        logger.info("🎉 All tests passed! The connection should work in the application.")
    else:
        logger.info("⚠️  Some tests failed. This explains why the application fails.")
        
        if success1 and not success2:
            logger.info("💡 Issue: SQLAlchemy configuration problem")
        elif success1 and success2 and not success3:
            logger.info("💡 Issue: Alembic configuration problem")
        elif not success1:
            logger.info("💡 Issue: Basic connection problem (check credentials)")

if __name__ == "__main__":
    main()
