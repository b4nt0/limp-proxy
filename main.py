"""
Main entry point for LIMP application.
"""

import uvicorn
import logging
from pathlib import Path

from limp.config import load_config, get_env_config
from limp.api.main import create_app

# Configure logging
def configure_logging(log_level: str = "INFO"):
    """Configure logging with the specified level."""
    # Convert string level to logging constant
    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }
    
    numeric_level = level_map.get(log_level.upper(), logging.INFO)
    
    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True  # Force reconfiguration even if logging was already configured
    )
    
    # Automatically configure all loggers under the 'limp' namespace
    def configure_limp_loggers():
        """Configure all loggers under the 'limp' namespace to use the specified level."""
        # Get all existing loggers
        existing_loggers = [name for name in logging.Logger.manager.loggerDict.keys()]
        
        # Set level for all loggers that start with 'limp'
        for logger_name in existing_loggers:
            if logger_name.startswith('limp'):
                logging.getLogger(logger_name).setLevel(numeric_level)
        
        # Also set the base 'limp' logger to ensure propagation
        limp_logger = logging.getLogger('limp')
        limp_logger.setLevel(numeric_level)
        limp_logger.propagate = True
    
    configure_limp_loggers()

logger = logging.getLogger(__name__)


def main():
    """Main application entry point."""
    try:
        # Get configuration path from environment
        env_config = get_env_config()
        config_path = Path(env_config.get_config_path())
        
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            logger.info(f"Please create a {config_path} file with your configuration")
            logger.info("You can also set LIMP_CONFIG environment variable to specify a different config file")
            return
        
        logger.info(f"Loading configuration from {config_path}")
        config = load_config(str(config_path))
        
        # Configure logging with the level from config
        configure_logging(config.logging.level)
        logger.info(f"Logging configured with level: {config.logging.level}")
        
        # Create FastAPI app
        app = create_app(config)
        
        # Start server
        logger.info("Starting LIMP server...")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            log_config=None  # Disable uvicorn's logging configuration override
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise


if __name__ == "__main__":
    main()

