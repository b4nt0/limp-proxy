"""
Main entry point for LIMP application.
"""

import uvicorn
import logging
from pathlib import Path

from limp.config import load_config, get_env_config
from limp.api.main import create_app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

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
        
        config = load_config(str(config_path))
        
        # Create FastAPI app
        app = create_app(config)
        
        # Start server
        logger.info("Starting LIMP server...")
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info"
        )
        
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        raise


if __name__ == "__main__":
    main()

