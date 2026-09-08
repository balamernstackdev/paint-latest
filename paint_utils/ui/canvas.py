"""
Canvas wrapper module - Handles background image conversion for streamlit-drawable-canvas.

This module provides a wrapper around the streamlit_drawable_canvas component
to handle background image conversion to data URLs with caching for performance.
"""

import streamlit as st
from streamlit_drawable_canvas import st_canvas as raw_st_canvas
from ..encoding import image_to_url_patch


def st_canvas(*args, **kwargs):
    """
    Wrapper for streamlit_drawable_canvas with cached background image handling.
    
    Converts PIL Image backgrounds to data URLs with intelligent caching based on
    render state to avoid redundant encoding operations.
    
    Args:
        *args: Positional arguments passed to st_canvas
        **kwargs: Keyword arguments, including:
            - background_image: PIL Image to display as background
            - width: Canvas width in pixels
            - height: Canvas height in pixels
            - fill_color: Canvas fill color
            - stroke_width: Drawing stroke width
            - drawing_mode: 'point', 'freedraw', 'rect', etc.
            - initial_drawing: Optional initial drawing state
            - Other st_canvas parameters
    
    Returns:
        Canvas result object with json_data and image_data
        
    Note:
        - Background images are cached using render_id and comparison state
        - Cache keys include render_hash to detect image changes
        - JPEG encoding used for performance with large images
    """
    kwargs["background_color"] = "rgba(0,0,0,0)"
    bg_img = kwargs.get("background_image")
    
    if bg_img is not None:
        width, height = kwargs.get("width"), kwargs.get("height")
        
        # Performance: Cache key includes render_hash and comparison state
        comp_flag = str(st.session_state.get("show_comparison", False))
        r_hash = str(st.session_state.get("render_id", 0))
        cache_key = f"bg_url_cache_{r_hash}_{comp_flag}"
        
        # Check cache first
        if cache_key in st.session_state:
            url = st.session_state[cache_key]
        else:
            # Generate data URL with render hash for cache busting
            url = image_to_url_patch(bg_img, width, True, "RGB", "JPEG", r_hash)
            st.session_state[cache_key] = url
        
        # Initialize drawing structure if not provided
        if not kwargs.get("initial_drawing"):
            kwargs["initial_drawing"] = {"version": "4.4.0", "objects": []}
            
        kwargs["initial_drawing"]["background"] = "rgba(0,0,0,0)"
        kwargs["initial_drawing"]["backgroundImage"] = {
            "type": "image",
            "version": "4.4.0",
            "originX": "left",
            "originY": "top",
            "left": 0,
            "top": 0,
            "width": width,
            "height": height,
            "scaleX": 1,
            "scaleY": 1,
            "visible": True,
            "src": url
        }
        
        # Remove background_image from kwargs to avoid conflicts
        if "background_image" in kwargs:
            del kwargs["background_image"]
            
    return raw_st_canvas(*args, **kwargs)
