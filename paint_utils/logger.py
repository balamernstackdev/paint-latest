"""
Centralized logging configuration for AI Paint Visualizer.
Provides structured logging with different levels for development and production.
"""

import logging
import sys
from functools import wraps
import time


# Create loggers
logger = logging.getLogger('paint_visualizer')

def setup_logging(level=logging.INFO, log_file=None):
    """
    Configure logging for the application.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional file to write logs to (in addition to console)
    """
    # Clear existing handlers
    logger.handlers = []
    logger.setLevel(level)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def log_exceptions(func):
    """
    Decorator to automatically log exceptions from functions.
    
    Usage:
        @log_exceptions
        def my_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Exception in {func.__name__}: {str(e)}", exc_info=True)
            raise
    return wrapper


def log_performance(func):
    """
    Decorator to log function execution time.
    
    Usage:
        @log_performance
        def slow_function():
            ...
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            elapsed = time.time() - start_time
            logger.info(f"{func.__name__} completed in {elapsed:.3f}s")
            return result
        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(f"{func.__name__} failed after {elapsed:.3f}s: {str(e)}")
            raise
    return wrapper


# Initialize with default settings
setup_logging(level=logging.INFO)
