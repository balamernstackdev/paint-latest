"""
Adaptive image processing utilities for object classification and parameter selection.

This module provides intelligent analysis of masked regions to detect object types
(walls, floors, ceilings, furniture) and select optimal processing parameters.
"""

import cv2
import numpy as np
from enum import Enum
from typing import Tuple, Dict, Any
from app_config.constants import AdaptiveProcessingConfig


class ObjectType(Enum):
    """Classification of objects for adaptive processing."""
    WALL_SMOOTH = "wall_smooth"
    WALL_TEXTURED = "wall_textured"
    FLOOR = "floor"
    CEILING = "ceiling"
    FURNITURE = "furniture"
    SMALL_OBJECT = "small_object"


def detect_edge_density(image_region: np.ndarray) -> float:
    """
    Calculate edge density in an image region.
    
    Higher density indicates sharp objects (furniture, doors).
    Lower density indicates smooth surfaces (walls, floors).
    
    Args:
        image_region: RGB image region (H, W, 3)
        
    Returns:
        float: Edge density (0.0-1.0), proportion of edge pixels
        
    Example:
        >>> region = image[mask]
        >>> density = detect_edge_density(region)
        >>> if density > 0.3:
        >>>     print("Sharp object detected")
    """
    if image_region.size == 0:
        return 0.0
    
    # Convert to grayscale
    gray = cv2.cvtColor(image_region, cv2.COLOR_RGB2GRAY)
    
    # Detect edges using Canny
    edges = cv2.Canny(gray, 50, 150)
    
    # Calculate density
    edge_density = np.sum(edges > 0) / edges.size
    
    return float(edge_density)


def detect_texture(image_region: np.ndarray) -> bool:
    """
    Detect if region has significant texture (brick, stucco, fabric).
    
    Uses Laplacian variance to detect high-frequency details.
    
    Args:
        image_region: RGB image region (H, W, 3)
        
    Returns:
        bool: True if textured, False if smooth
    """
    if image_region.size == 0:
        return False
    
    gray = cv2.cvtColor(image_region, cv2.COLOR_RGB2GRAY)
    laplacian_var = cv2.Laplacian(gray, cv2.CV_64F).var()
    
    return laplacian_var > AdaptiveProcessingConfig.TEXTURE_VARIANCE_THRESHOLD


def classify_object(
    mask: np.ndarray,
    image: np.ndarray,
    seed_point: Tuple[int, int]
) -> ObjectType:
    """
    Classify object type based on mask characteristics and position.
    
    Uses area, texture, and vertical position to determine object type.
    This enables type-specific processing parameters.
    
    Args:
        mask: Boolean mask (H, W)
        image: Full RGB image (H, W, 3)
        seed_point: Click coordinates (x, y)
        
    Returns:
        ObjectType: Classified object type
        
    Example:
        >>> obj_type = classify_object(mask, image, (150, 300))
        >>> params = get_object_params(obj_type)
    """
    h, w = mask.shape
    mask_area = np.sum(mask) / (h * w)
    
    # Extract masked region for analysis
    mask_bool = mask.astype(bool)
    if not np.any(mask_bool):
        return ObjectType.SMALL_OBJECT
    
    # Create bounding box to extract region efficiently
    rows = np.any(mask_bool, axis=1)
    cols = np.any(mask_bool, axis=0)
    if not np.any(rows) or not np.any(cols):
        return ObjectType.SMALL_OBJECT
    
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    region = image[rmin:rmax+1, cmin:cmax+1]
    
    # Detect texture
    is_textured = detect_texture(region)
    
    # Classify based on area and position
    if mask_area < AdaptiveProcessingConfig.SMALL_OBJECT_AREA_THRESHOLD:
        return ObjectType.SMALL_OBJECT
    
    elif mask_area > AdaptiveProcessingConfig.LARGE_OBJECT_AREA_THRESHOLD:
        # Large area - likely floor or ceiling
        seed_y = seed_point[1]
        
        if seed_y < h * AdaptiveProcessingConfig.CEILING_Y_THRESHOLD:
            return ObjectType.CEILING
        elif seed_y > h * AdaptiveProcessingConfig.FLOOR_Y_THRESHOLD:
            return ObjectType.FLOOR
        else:
            # Large wall
            return ObjectType.WALL_TEXTURED if is_textured else ObjectType.WALL_SMOOTH
    
    else:
        # Medium area - wall or furniture
        edge_density = detect_edge_density(region)
        
        if edge_density > AdaptiveProcessingConfig.EDGE_DENSITY_SHARP_THRESHOLD:
            return ObjectType.FURNITURE
        else:
            return ObjectType.WALL_TEXTURED if is_textured else ObjectType.WALL_SMOOTH


def get_object_params(obj_type: ObjectType) -> Dict[str, Any]:
    """
    Get processing parameters for specific object type.
    
    Returns optimized blur kernels, tolerances, and thresholds
    for each object category.
    
    Args:
        obj_type: Classified object type
        
    Returns:
        dict: Processing parameters with keys:
            - blur_kernel: Tuple (width, height)
            - dilation_iterations: int
            - color_tolerance: float
            - edge_threshold: int
            - use_bilateral: bool
            
    Example:
        >>> params = get_object_params(ObjectType.WALL_TEXTURED)
        >>> blur_kernel = params['blur_kernel']  # (3, 3)
        >>> use_bilateral = params['use_bilateral']  # True
    """
    params_map = {
        ObjectType.WALL_SMOOTH: {
            'blur_kernel': AdaptiveProcessingConfig.MEDIUM_BLUR,
            'dilation_iterations': 2,
            'color_tolerance': AdaptiveProcessingConfig.WALL_SMOOTH_COLOR_TOL,
            'edge_threshold': AdaptiveProcessingConfig.WALL_SMOOTH_EDGE_THRESH,
            'use_bilateral': False
        },
        ObjectType.WALL_TEXTURED: {
            'blur_kernel': AdaptiveProcessingConfig.SHARP_EDGE_BLUR,
            'dilation_iterations': 1,
            'color_tolerance': AdaptiveProcessingConfig.WALL_TEXTURED_COLOR_TOL,
            'edge_threshold': AdaptiveProcessingConfig.WALL_TEXTURED_EDGE_THRESH,
            'use_bilateral': True  # Preserve texture details
        },
        ObjectType.FLOOR: {
            'blur_kernel': AdaptiveProcessingConfig.SOFT_BLUR,
            'dilation_iterations': 3,
            'color_tolerance': AdaptiveProcessingConfig.FLOOR_COLOR_TOL,
            'edge_threshold': AdaptiveProcessingConfig.FLOOR_EDGE_THRESH,
            'use_bilateral': False
        },
        ObjectType.CEILING: {
            'blur_kernel': AdaptiveProcessingConfig.SOFT_BLUR,
            'dilation_iterations': 3,
            'color_tolerance': AdaptiveProcessingConfig.FLOOR_COLOR_TOL,
            'edge_threshold': AdaptiveProcessingConfig.FLOOR_EDGE_THRESH,
            'use_bilateral': False
        },
        ObjectType.SMALL_OBJECT: {
            'blur_kernel': AdaptiveProcessingConfig.SHARP_EDGE_BLUR,
            'dilation_iterations': 0,
            'color_tolerance': AdaptiveProcessingConfig.SMALL_OBJECT_COLOR_TOL,
            'edge_threshold': AdaptiveProcessingConfig.SMALL_OBJECT_EDGE_THRESH,
            'use_bilateral': False
        },
        ObjectType.FURNITURE: {
            'blur_kernel': AdaptiveProcessingConfig.SHARP_EDGE_BLUR,
            'dilation_iterations': 1,
            'color_tolerance': AdaptiveProcessingConfig.FURNITURE_COLOR_TOL,
            'edge_threshold': AdaptiveProcessingConfig.FURNITURE_EDGE_THRESH,
            'use_bilateral': False
        }
    }
    
    return params_map.get(obj_type, params_map[ObjectType.WALL_SMOOTH])


def get_adaptive_blur_kernel(mask: np.ndarray, image: np.ndarray) -> Tuple[int, int]:
    """
    Determine optimal blur kernel size based on edge density.
    
    Fast alternative to full object classification when only blur is needed.
    
    Args:
        mask: Boolean mask (H, W)
        image: Full RGB image (H, W, 3)
        
    Returns:
        tuple: Blur kernel size (width, height)
        
    Example:
        >>> kernel = get_adaptive_blur_kernel(mask, image)
        >>> blurred = cv2.GaussianBlur(mask_float, kernel, 0)
    """
    mask_bool = mask.astype(bool)
    if not np.any(mask_bool):
        return AdaptiveProcessingConfig.MEDIUM_BLUR
    
    # Extract region and detect edges
    rows = np.any(mask_bool, axis=1)
    cols = np.any(mask_bool, axis=0)
    
    if not np.any(rows) or not np.any(cols):
        return AdaptiveProcessingConfig.MEDIUM_BLUR
    
    rmin, rmax = np.where(rows)[0][[0, -1]]
    cmin, cmax = np.where(cols)[0][[0, -1]]
    region = image[rmin:rmax+1, cmin:cmax+1]
    
    edge_density = detect_edge_density(region)
    
    # Select kernel based on edge density
    if edge_density > AdaptiveProcessingConfig.EDGE_DENSITY_SHARP_THRESHOLD:
        return AdaptiveProcessingConfig.SHARP_EDGE_BLUR
    elif edge_density > AdaptiveProcessingConfig.EDGE_DENSITY_MEDIUM_THRESHOLD:
        return AdaptiveProcessingConfig.MEDIUM_BLUR
    else:
        return AdaptiveProcessingConfig.SOFT_BLUR


def apply_bilateral_blur(mask: np.ndarray, preserve_edges: bool = True) -> np.ndarray:
    """
    Apply edge-preserving bilateral filter to mask.
    
    Used for textured surfaces to maintain detail while smoothing.
    
    Args:
        mask: Input mask (float32)
        preserve_edges: If True, uses bilateral filter; else Gaussian
        
    Returns:
        np.ndarray: Blurred mask (float32)
    """
    if not preserve_edges:
        # Fallback to Gaussian
        return cv2.GaussianBlur(mask, AdaptiveProcessingConfig.MEDIUM_BLUR, 0)
    
    # Ensure float32 in range [0, 1]
    mask_normalized = mask.astype(np.float32)
    if mask_normalized.max() > 1.0:
        mask_normalized /= 255.0
    
    # Scale to [0, 255] for bilateral filter
    mask_uint8 = (mask_normalized * 255).astype(np.uint8)
    
    # Apply bilateral filter
    blurred_uint8 = cv2.bilateralFilter(
        mask_uint8,
        d=AdaptiveProcessingConfig.BILATERAL_DIAMETER,
        sigmaColor=AdaptiveProcessingConfig.BILATERAL_SIGMA_COLOR,
        sigmaSpace=AdaptiveProcessingConfig.BILATERAL_SIGMA_SPACE
    )
    
    # Convert back to float32 [0, 1]
    return blurred_uint8.astype(np.float32) / 255.0
