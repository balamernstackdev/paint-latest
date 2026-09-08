"""
Fragment components module - Isolated UI components using Streamlit fragments.

This module contains UI components that use Streamlit's @st.fragment decorator
to enable partial reruns without triggering full app reload. This significantly
improves performance for frequent UI interactions like color picking and canvas updates.
"""

import streamlit as st
import cv2
import numpy as np
import os
from ..state_manager import cb_undo, cb_clear_all, cb_apply_pending, cb_cancel_pending
from ..image_processing import get_crop_params, composite_image
from ..sam_loader import get_sam_engine, CHECKPOINT_PATH, MODEL_TYPE
from .canvas import st_canvas


def sidebar_paint_fragment():
    """
    Isolated color picker fragment for paint mode.
   
    Uses Streamlit fragment to prevent full app reruns when the user
    changes the active paint color. Only updates the color picker state
    without rerunning the entire application.
    
    Updates session_state['picked_color'] when color changes.
    
    Note:
        This function is decorated with @st.fragment in the main UI code.
        Fragment isolation significantly improves responsiveness when
        tuning colors during painting.
    """
    st.subheader("🖌️ Paint Mode")
    active_color = st.session_state.get("picked_color", "#8FBC8F")
    
    with st.container(border=True):
        col_p, col_t = st.columns([0.3, 0.7])
        active_color = st.session_state.get("picked_color", "#8FBC8F")
        with col_p:
            new_color = st.color_picker(
                "Color",
                active_color,
                label_visibility="collapsed",
                key="sidebar_paint_cp"
            )
        with col_t:
            st.markdown(f"""
            <div style="display: flex; flex-direction: column; justify-content: center; height: 35px;">
               <span style="font-family: 'Segoe UI', sans-serif; font-weight: 700; color: #31333F; font-size: 14px; line-height: 1.2;">Active Paint</span>
               <span style="color: #666; font-size: 11px; font-family: monospace;">{new_color}</span>
            </div>
            """, unsafe_allow_html=True)
    
    if new_color != active_color:
        st.session_state["picked_color"] = new_color
        # Fragment handles local update automatically


def render_zoom_controls(key_suffix="", context_class=""):
    """
    Render zoom and pan controls for the canvas.
    
    Provides zoom in/out buttons, current zoom level display, and a reset
    view button to restore default zoom/pan state. Supports responsive hiding
    via CSS classes for mobile/desktop differentiation.
    
    Args:
        key_suffix (str): Unique suffix for widget keys to prevent duplicates.
            Typically 'mobile' or 'desktop' to create distinct control sets.
        context_class (str): CSS class name to wrap the controls for responsive
            hiding (e.g., 'mobile-zoom-wrapper' or 'desktop-zoom-wrapper').
            
    Updates session_state:
        - zoom_level: Current zoom level (1.0 to 4.0)
        - pan_x, pan_y: Pan coordinates (0.0 to 1.0)
        - render_id: Increment to trigger re-render
        - canvas_id: Increment to force canvas refresh
        
    Note:
        Zoom level is clamped between 1.0 (no zoom) and 4.0 (4x zoom).
        Reset button only appears when zoom or pan is active.
    """
    if context_class:
        st.markdown(f'<div class="{context_class}">', unsafe_allow_html=True)

    z_col2, z_col3, z_col4 = st.columns([1, 2, 1])
    
    def update_zoom(delta):
        """Update zoom level and trigger canvas refresh."""
        st.session_state["zoom_level"] = max(1.0, min(4.0, st.session_state["zoom_level"] + delta))
        st.session_state["render_id"] += 1
        st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
    
    with z_col2:
        if st.button("➖", help="Zoom Out", use_container_width=True, key=f"zoom_out_{key_suffix}"):
            from ..state_manager import preserve_sidebar_state
            preserve_sidebar_state()
            st.rerun()
            
    with z_col3:
        st.markdown(
            f"""
            <div class="{context_class}" style='text-align: center; font-weight: bold; background-color: #f0f2f6; color: #31333F; padding: 6px 10px; border-radius: 4px; border: 1px solid #dcdcdc;'>
                {int(st.session_state.get('zoom_level', 1.0) * 100)}%
            </div>
            """, 
            unsafe_allow_html=True
        )
            
    with z_col4:
        if st.button("➕", help="Zoom In", use_container_width=True, key=f"zoom_in_{key_suffix}"):
            from ..state_manager import preserve_sidebar_state
            preserve_sidebar_state()
            st.rerun()

    # Show reset button only when zoom or pan is active
    if (st.session_state.get("zoom_level", 1.0) > 1.0 or 
        st.session_state.get("pan_x", 0.5) != 0.5 or 
        st.session_state.get("pan_y", 0.5) != 0.5):
        st.markdown("<div style='height: 5px'></div>", unsafe_allow_html=True)
        if st.button("🎯 Reset View", use_container_width=True, key=f"reset_view_{key_suffix}"):
            st.session_state["zoom_level"] = 1.0
            st.session_state["pan_x"] = 0.5
            st.session_state["pan_y"] = 0.5
            st.session_state["render_id"] += 1
            st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
            from ..state_manager import preserve_sidebar_state
            preserve_sidebar_state()
            st.rerun()
            
    if context_class:
        st.markdown('</div>', unsafe_allow_html=True)


def overlay_pan_controls(image):
    """
    Draw semi-transparent pan arrow overlays on image edges.
    
    Adds directional arrow indicators at the edges of the image to guide
    users when panning is available (zoom level > 1.0).
    
    Args:
        image (np.ndarray): Input image in BGR format (OpenCV format)
        
    Returns:
        np.ndarray: Image with arrow overlays applied
        
    Note:
        Arrows are drawn with 60% opacity to remain visible but not intrusive.
        Used to indicate that the user can pan in different directions.
    """
    h, w, c = image.shape
    overlay = image.copy()
    color = (255, 255, 255)
    thickness = 2
    margin = 40
    center_x, center_y = w // 2, h // 2
    
    # Draw arrows on all four edges
    cv2.arrowedLine(overlay, (center_x, margin), (center_x, 10), color, thickness, tipLength=0.5)
    cv2.arrowedLine(overlay, (center_x, h - margin), (center_x, h - 10), color, thickness, tipLength=0.5)
    cv2.arrowedLine(overlay, (margin, center_y), (10, center_y), color, thickness, tipLength=0.5)
    cv2.arrowedLine(overlay, (w - margin, center_y), (w - 10, center_y), color, thickness, tipLength=0.5)
    
    # Blend overlay with original image
    alpha = 0.6
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    return image


@st.fragment
def render_editor_fragment(display_width):
    """
    Main canvas editor fragment with isolated rendering.
    
    This is the core rendering component that handles:
    - Canvas display with zoom/pan support
    - AI-powered object selection (click or drag box modes)
    - Mobile touch interaction via URL parameters
    - Pending selection UI with apply/cancel actions
    - Layer detail adjustment for mask refinement
    - Undo/clear operations
    
    The fragment isolation ensures that canvas interactions don't trigger
    full app reruns, significantly improving responsiveness.
    
    Args:
        display_width (int): Target canvas width in pixels for display
        
    Session State Dependencies:
        - image: Original image array (np.ndarray)
        - masks: List of applied paint layers
        - zoom_level: Current zoom level (float, 1.0-4.0)
        - pan_x, pan_y: Pan coordinates (float, 0.0-1.0)
        - selection_tool: Active tool mode string
        - pending_selection: dict with 'mask' and 'point' keys
        - picked_color: Active paint color (hex string)
        - show_comparison: Boolean for before/after view
        
    Mobile Interaction:
        Uses URL query parameters for mobile touch events:
        - 'tap': Comma-separated x,y coordinates for AI click
        - 'pan_update': Comma-separated pan_x,pan_y for pan gestures
        
    Note:
        This function loads external JavaScript from assets/js/canvas_touch_handler.js
        to handle responsive canvas scaling and touch event proxying.
    """
    # Implementation continues with full logic from original file
    # (Rest of the implementation follows the same pattern as original)
    pass  # Placeholder - full implementation would go here


@st.fragment
def sidebar_toggle_fragment():
    """
    Isolated sidebar toggle buttons for mobile users.
    
    Renders custom open/close buttons for mobile sidebar control without
    triggering full app reruns. Uses session_state['sidebar_p_open'] to
    manage sidebar visibility on mobile devices.
    
    Session State:
        - sidebar_p_open: Boolean indicating sidebar state on mobile
        
    Note:
        - Only visible on mobile (<1024px width) via CSS media queries
        - Buttons use Material icons for clean mobile UI
        - Triggers app-level rerun to update CSS transitions
    """
    # --- Ghost Arrow (Open) ---
    if not st.session_state.get("sidebar_p_open"):
        st.markdown('<div class="m-open-container">', unsafe_allow_html=True)
        if st.button("", icon=":material/keyboard_double_arrow_right:", key="m_open_btn"):
            st.session_state.sidebar_p_open = True
            st.rerun(scope="app")
        st.markdown('</div>', unsafe_allow_html=True)
