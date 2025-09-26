"""
Main entry point for LIMP application.
"""

import uvicorn
import logging
from pathlib import Path

from limp.config import load_config
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
        # Load configuration
        config_path = Path("config.yaml")
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            logger.info("Please create a config.yaml file with your configuration")
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

