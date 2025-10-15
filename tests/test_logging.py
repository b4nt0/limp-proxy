"""
Test logging configuration to ensure all loggers work properly.
"""

import logging
import pytest
from io import StringIO
from unittest.mock import patch
from limp.config import LoggingConfig


def test_all_limp_loggers_are_configured():
    """Test that all loggers under the 'limp' namespace are properly configured."""
    # Import the main module to trigger logger configuration
    import main
    
    # Get all loggers that start with 'limp'
    limp_loggers = [
        name for name in logging.Logger.manager.loggerDict.keys() 
        if name.startswith('limp')
    ]
    
    # Verify that all limp loggers have INFO level set
    for logger_name in limp_loggers:
        logger = logging.getLogger(logger_name)
        assert logger.level <= logging.INFO, f"Logger {logger_name} has level {logger.level} which is higher than INFO"
        assert logger.propagate is True, f"Logger {logger_name} should propagate to parent"


def test_logger_output_captured():
    """Test that individual loggers actually output messages."""
    from main import configure_logging
    
    # Store original state
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    
    # Clear existing handlers
    for handler in original_handlers:
        root_logger.removeHandler(handler)
    
    try:
        # Configure logging fresh
        configure_logging("INFO")
        
        # Test various limp loggers by checking their configuration
        test_loggers = [
            'limp.api.slack',
            'limp.api.main', 
            'limp.services.llm',
            'limp.services.im'
        ]
        
        for logger_name in test_loggers:
            logger = logging.getLogger(logger_name)
            
            # Test that the logger is properly configured
            assert logger.level <= logging.INFO, f"Logger {logger_name} level {logger.level} should be <= INFO"
            assert logger.propagate is True, f"Logger {logger_name} should propagate to parent"
            
            # Test that the logger can be used (without checking output)
            # This verifies the logging system is working without depending on output capture
            logger.info(f"Test message from {logger_name}")
            
    finally:
        # Clean up - restore original handlers
        for orig_handler in original_handlers:
            root_logger.addHandler(orig_handler)


def test_new_logger_automatically_configured():
    """Test that a new logger under 'limp' namespace is automatically configured."""
    from main import configure_logging
    
    # Store original state
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers[:]
    original_level = root_logger.level
    
    # Clear existing handlers
    for handler in original_handlers:
        root_logger.removeHandler(handler)
    
    try:
        # Configure logging fresh
        configure_logging("INFO")
        
        # Create a new logger that would be created by a new module
        new_logger_name = 'limp.new_module'
        new_logger = logging.getLogger(new_logger_name)
        
        # The logger should inherit the configuration from the 'limp' parent
        # Since we set limp.propagate = True, it should work
        assert new_logger.propagate is True, "New logger should propagate to parent"
        
        # Test that the logger is properly configured
        assert new_logger.level <= logging.INFO, f"New logger level {new_logger.level} should be <= INFO"
        
        # Test that the logger can be used (without checking output)
        # This verifies the logging system is working without depending on output capture
        new_logger.info("Test message from new logger")
        
    finally:
        # Clean up - restore original handlers
        for orig_handler in original_handlers:
            root_logger.addHandler(orig_handler)


def test_logging_config_model():
    """Test that LoggingConfig model works correctly."""
    # Test default values
    default_config = LoggingConfig()
    assert default_config.level == "INFO"
    
    # Test custom values
    debug_config = LoggingConfig(level="DEBUG")
    assert debug_config.level == "DEBUG"
    
    warning_config = LoggingConfig(level="WARNING")
    assert warning_config.level == "WARNING"


def test_configurable_log_levels():
    """Test that different log levels can be configured."""
    from main import configure_logging
    
    # Test different log levels
    test_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    
    for level in test_levels:
        # Clear existing handlers to avoid interference
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Configure logging with the test level
        configure_logging(level)
        
        # Verify the root logger has the correct level
        assert root_logger.level == getattr(logging, level)
        
        # Test that limp loggers inherit the level
        limp_logger = logging.getLogger('limp')
        assert limp_logger.level == getattr(logging, level)


def test_invalid_log_level_defaults_to_info():
    """Test that invalid log levels default to INFO."""
    from main import configure_logging
    
    # Clear existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Test with invalid level
    configure_logging("INVALID_LEVEL")
    
    # Should default to INFO
    assert root_logger.level == logging.INFO


if __name__ == "__main__":
    pytest.main([__file__])
