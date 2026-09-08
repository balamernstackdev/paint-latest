"""
Performance optimization utilities for image processing and caching.

This module provides optimized operations for memory management,
cache cleanup, and performance-critical image processing.
"""

import streamlit as st
import numpy as np
import gc
from typing import Optional, List, Dict, Any
from app_config.constants import MAX_IMAGE_DIMENSION


def cleanup_session_caches(aggressive: bool = False):
    """
    Clean up session state caches to free memory.
    
    Removes cached data URLs, LAB conversions, and composited images
    that are no longer needed. Called automatically on image changes
    and can be manually triggered for memory optimization.
    
    Args:
        aggressive (bool): If True, clears all caches including base images.
            If False, only clears derived caches (safer for active sessions).
            
    Returns:
        int: Number of cache entries cleared
        
    Example:
        >>> cleanup_session_caches(aggressive=False)  # Safe cleanup
        >>> cleanup_session_caches(aggressive=True)   # Deep cleanup
    """
    cleared_count = 0
    
    # Cache key prefixes to clean
    cache_prefixes = ["bg_url_cache_", "comp_cache_"]
    
    if aggressive:
        cache_prefixes.extend(["base_l_", "lab_cache_"])
    
    # Remove matching cache keys
    keys_to_delete = []
    for key in list(st.session_state.keys()):
        if any(key.startswith(prefix) for prefix in cache_prefixes):
            keys_to_delete.append(key)
    
    for key in keys_to_delete:
        del st.session_state[key]
        cleared_count += 1
    
    # Clear specific cache keys
    cache_keys = ["render_cache", "composited_cache"]
    if aggressive:
        cache_keys.extend(["global_base_lab", "lab_cache_id", "lab_cache_dim"])
    
    for key in cache_keys:
        if key in st.session_state:
            del st.session_state[key]
            cleared_count += 1
    
    # Force Python garbage collection
    gc.collect()
    
    return cleared_count


def optimize_mask_storage(masks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Optimize mask storage by compressing sparse masks.
    
    Converts dense boolean masks to sparse representation when beneficial
    (>90% zeros). Can significantly reduce memory for small painted areas.
    
    Args:
        masks: List of mask dictionaries with 'mask' key
        
    Returns:
        List of optimized mask dictionaries
        
    Note:
        This is a future optimization - currently returns masks unchanged.
        Full implementation would use scipy.sparse or RLE encoding.
    """
    # Future optimization: convert sparse masks to compressed format
    # For now, return as-is to maintain compatibility
    return masks


def estimate_memory_usage() -> Dict[str, float]:
    """
    Estimate current memory usage of session state.
    
    Calculates approximate memory consumption of images, masks,
    and cached data to help identify memory leaks.
    
    Returns:
        dict: Memory usage in MB for each category:
            - images: Original and working images
            - masks: All layer masks
            - caches: Data URL and processing caches
            - total: Sum of all categories
            
    Example:
        >>> mem = estimate_memory_usage()
        >>> print(f"Total memory: {mem['total']:.1f} MB")
    """
    usage = {"images": 0.0, "masks": 0.0, "caches": 0.0, "total": 0.0}
    
    # Estimate image memory
    for key in ["image", "image_original"]:
        if key in st.session_state and st.session_state[key] is not None:
            img = st.session_state[key]
            usage["images"] += img.nbytes / (1024 * 1024)  # Convert to MB
    
    # Estimate mask memory
    if "masks" in st.session_state:
        from scipy import sparse
        for mask_data in st.session_state["masks"]:
            if "mask" in mask_data and mask_data["mask"] is not None:
                m = mask_data["mask"]
                if sparse.issparse(m):
                    # Sparse matrix size is data + indices + pointers
                    size = (m.data.nbytes + m.indices.nbytes + m.indptr.nbytes)
                    usage["masks"] += size / (1024 * 1024)
                else:
                    usage["masks"] += m.nbytes / (1024 * 1024)
    
    # Estimate cache memory (approximation)
    cache_count = sum(
        1 for key in st.session_state.keys()
        if any(key.startswith(p) for p in ["bg_url_cache_", "comp_cache_", "base_l_"])
    )
    usage["caches"] = cache_count * 0.5  # Rough estimate: 0.5MB per cache entry
    
    usage["total"] = sum(usage.values())
    return usage


def should_trigger_cleanup() -> bool:
    """
    Determine if memory cleanup should be triggered.
    
    Checks if total estimated memory usage exceeds threshold
    (1.5GB) or if cache count is excessive (>20 entries).
    
    Returns:
        bool: True if cleanup recommended
    """
    mem_usage = estimate_memory_usage()
    cache_count = sum(
        1 for key in st.session_state.keys()
        if "cache" in key.lower()
    )
    
    # Trigger cleanup if memory > 1.5GB or cache count > 20
    return mem_usage["total"] > 1500 or cache_count > 20


def resize_image_smart(image: np.ndarray, max_dim: int = MAX_IMAGE_DIMENSION) -> np.ndarray:
    """
    Intelligently resize image with aspect ratio preservation.
    
    Only resizes if image exceeds max dimension. Uses high-quality
    interpolation (INTER_AREA for downscaling, INTER_LINEAR for upscaling).
    
    Args:
        image: Input image array (RGB)
        max_dim: Maximum dimension (width or height) in pixels
        
    Returns:
        np.ndarray: Resized image maintaining aspect ratio
        
    Example:
        >>> large_img = np.zeros((2000, 1500, 3), dtype=np.uint8)
        >>> resized = resize_image_smart(large_img, max_dim=1100)
        >>> max(resized.shape[:2])
        1100
    """
    import cv2
    
    h, w = image.shape[:2]
    
    # No resize needed
    if max(h, w) <= max_dim:
        return image
    
    # Calculate new dimensions
    if h > w:
        new_h = max_dim
        new_w = int(w * (max_dim / h))
    else:
        new_w = max_dim
        new_h = int(h * (max_dim / w))
    
    # Use appropriate interpolation
    interpolation = cv2.INTER_AREA  # Best for downscaling
    
    return cv2.resize(image, (new_w, new_h), interpolation=interpolation)
