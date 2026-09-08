"""
Configuration package for AI Paint Visualizer.
Centralizes all tunable parameters and constants.
"""

from .constants import (
    SegmentationConfig,
    ColorizerConfig,
    UIConfig,
    PerformanceConfig
)

__all__ = [
    'SegmentationConfig',
    'ColorizerConfig',
    'UIConfig',
    'PerformanceConfig'
]
