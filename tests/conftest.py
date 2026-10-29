"""
Pytest configuration and shared fixtures for AI Paint Visualizer tests.

This module provides shared fixtures and configuration for all test modules.
"""

import pytest
import numpy as np
import cv2
from PIL import Image


@pytest.fixture
def sample_image():
    """
    Create a simple test image (RGB).
    
    Returns:
        np.ndarray: 100x100 RGB image with simple color pattern
    """
    # Create a simple gradient image for testing
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    img[:, :50] = [255, 0, 0]  # Red left half
    img[:, 50:] = [0, 0, 255]  # Blue right half
    return img


@pytest.fixture
def sample_mask():
    """
    Create a simple boolean mask.
    
    Returns:
        np.ndarray: 100x100 boolean mask with left half True
    """
    mask = np.zeros((100, 100), dtype=bool)
    mask[:, :50] = True
    return mask


@pytest.fixture
def sample_color():
    """
    Sample hex color for testing.
    
    Returns:
        str: Hex color code
    """
    return "#8FBC8F"


@pytest.fixture
def sample_large_image():
    """
    Create a larger test image for performance testing.
    
    Returns:
        np.ndarray: 1024x768 RGB image
    """
    return np.random.randint(0, 255, (768, 1024, 3), dtype=np.uint8)


@pytest.fixture
def mock_sam_predictor(mocker):
    """
    Mock SAM predictor for testing segmentation without loading model.
    
    Args:
        mocker: pytest-mock mocker fixture
        
    Returns:
        Mock SAM predictor object
    """
    mock_predictor = mocker.Mock()
    mock_predictor.set_image = mocker.Mock()
    mock_predictor.predict = mocker.Mock(return_value=(
        np.ones((100, 100), dtype=bool),  # mask
        np.array([0.9, 0.8, 0.7]),  # scores
        np.zeros((3, 100, 100), dtype=bool)  # logits
    ))
    return mock_predictor


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')"
    )
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests"
    )
    config.addinivalue_line(
        "markers", "unit: marks tests as unit tests"
    )
