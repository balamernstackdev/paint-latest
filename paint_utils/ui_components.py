import streamlit as st
import os
import cv2
import numpy as np
import torch
import streamlit.components.v1 as components
from scipy import sparse

import logging
import time
import io
import requests
import textwrap
from PIL import Image
from streamlit_drawable_canvas import st_canvas as raw_st_canvas
from streamlit_image_comparison import image_comparison
from .encoding import image_to_url_patch
from .state_manager import cb_undo, cb_redo, cb_clear_all, cb_delete_layer, cb_apply_pending, cb_cancel_pending, preserve_sidebar_state
from .image_processing import (
    get_crop_params, composite_image, process_lasso_path,
    get_display_base_image, to_grayscale_rgb
)
from .sam_loader import get_sam_engine, CHECKPOINT_PATH, MODEL_TYPE
from .performance import cleanup_session_caches

# --- UI CONSTANTS ---
TOOL_MAPPING = {
    "👆": "👆 AI Click (Point)",
    "✨": "✨ AI Object (Box)",
    "🕸️": "🕸️ Polygonal Lasso",
    "✏️": "✏️ Paint Brush",
    "🧹": "🧹 Eraser Tool",
    "🪄": "🪄 Magic Wand"
}

# --- HELPERS ---
def safe_rerun(scope="fragment"):
    """Prevents StreamlitAPIException during full-rerun transitions."""
    preserve_sidebar_state()
    try:
        st.rerun(scope=scope)
    except:
        st.rerun()

def cb_top_tool_sync_v2():
    """Sync top icons to master selection_tool with canvas reset."""
    new_icon = st.session_state.get("top_tool_switcher_control")
    if new_icon and new_icon in TOOL_MAPPING:
        st.session_state["selection_tool"] = TOOL_MAPPING[new_icon]
        st.session_state["sidebar_tool_radio"] = TOOL_MAPPING[new_icon]
        st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
        st.session_state["canvas_raw"] = {}
        st.session_state["pending_selection"] = None
    # No rerun needed here as on_change triggers it automatically

def cb_top_wall_sync_v2():
    """Sync top toggle to master is_wall_only."""
    st.session_state["is_wall_only"] = st.session_state.get("top_wall_control", True)
    st.session_state["sidebar_wall_toggle"] = st.session_state["is_wall_only"]

def cb_sidebar_tool_sync(widget_key=None):
    """Sync sidebar radio to master selection_tool and top ICON switcher."""
    # Use stable static key to prevent 'ping-pong' switching
    widget_key = "sidebar_tool_radio"
    
    new_tool = st.session_state.get(widget_key)
    print(f"DEBUG: CALLBACK sidebar_tool_radio -> {new_tool} (Current: {st.session_state.get('selection_tool')})")
    
    if new_tool is None: return

    # --- 🛠️ CLEAN TOOL SWITCH ---
    last_tool = st.session_state.get("selection_tool")
    if last_tool != new_tool:
        # Tool changed! Wipe all volatile interaction signals
        for pk in ["tap", "poly_pts", "pan_update", "zoom_update", "force_finish"]:

            if pk in st.query_params: st.query_params.pop(pk, None)
        # Also clear internal state
        st.session_state["force_finish_poly"] = False
        st.session_state["loop_guarded"] = False
        st.session_state["force_finish_poly"] = False
        st.session_state["loop_guarded"] = False
        
        # Reset operation based on tool (Eraser defaults to Subtract)
        if "Eraser" in new_tool:
            st.session_state["selection_op"] = "Subtract"
            st.session_state["sidebar_op_radio"] = "Subtract"
        else:
            st.session_state["selection_op"] = "Add"
            st.session_state["sidebar_op_radio"] = "Add"
        
        # FIX: Defer JS clearing to the render loop to avoid callback reruns
        st.session_state["tool_switched_reset"] = True
        st.session_state["fill_selection"] = False
        print(f"DEBUG: Tool Switched -> {last_tool} -> {new_tool}. Signals wiped.")

    st.session_state["selection_tool"] = new_tool
    st.session_state["sidebar_tool_radio"] = new_tool
    for icon, label in TOOL_MAPPING.items():
        if label == new_tool:
            st.session_state["top_tool_switcher_control"] = icon
            break
    st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
    st.session_state["canvas_raw"] = {}
    st.session_state["pending_selection"] = None

def cb_sidebar_wall_sync():
    """Sync sidebar toggle to master is_wall_only."""
    st.session_state["is_wall_only"] = st.session_state.get("sidebar_wall_toggle")
    st.session_state["top_wall_control"] = st.session_state["is_wall_only"]

def cb_sidebar_op_sync():
    """Sync sidebar radio to master selection_op."""
    st.session_state["selection_op"] = st.session_state.get("sidebar_op_radio", "Add")
    st.session_state["top_op_control"] = "➕" if st.session_state["selection_op"] == "Add" else "➖"

def cb_top_op_sync():
    """Sync top op segmented control to master selection_op."""
    icon = st.session_state.get("top_op_control")
    st.session_state["selection_op"] = "Add" if icon == "➕" else "Subtract"
    st.session_state["sidebar_op_radio"] = st.session_state["selection_op"]

def sort_points_clockwise(pts):
    """Sorts a list of (x, y) points in clockwise order around their centroid."""
    if not pts or len(pts) < 3: return pts
    
    # Calculate centroid
    center_x = sum(p[0] for p in pts) / len(pts)
    center_y = sum(p[1] for p in pts) / len(pts)
    
    # Sort by angle from centroid
    import math
    def get_angle(point):
        return math.atan2(point[1] - center_y, point[0] - center_x)
    
    return sorted(pts, key=get_angle)
def snap_box_to_edges(image, box, margin=15):
    """Refines box coordinates to align with strong architectural edges using Sobel gradients."""
    if image is None: return box
    h, w = image.shape[:2]
    x1, y1, x2, y2 = box
    
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    # Use Sobel to find gradients
    grad_x = cv2.convertScaleAbs(cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3))
    grad_y = cv2.convertScaleAbs(cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3))
    
    def refine_coord(coord, is_x):
        search_range = range(max(0, coord - margin), min((w if is_x else h), coord + margin))
        best_coord = coord
        max_grad = 0
        target_grad = grad_x if is_x else grad_y
        
        for i in search_range:
            if is_x:
                # Vertical edge: sum gradients along the vertical line at x=i
                g_sum = np.sum(target_grad[max(0, y1-margin):min(h, y2+margin), i])
            else:
                # Horizontal edge: sum gradients along the horizontal line at y=i
                g_sum = np.sum(target_grad[i, max(0, x1-margin):min(w, x2+margin)])
            
            if g_sum >= max_grad:
                max_grad = g_sum
                best_coord = i
        return best_coord

    nx1 = refine_coord(x1, True)
    ny1 = refine_coord(y1, False)
    nx2 = refine_coord(x2, True)
    ny2 = refine_coord(y2, False)
    
    return [nx1, ny1, nx2, ny2]

# --- CANVAS WRAPPER ---
def st_canvas(*args, **kwargs):
    """Wrapper to handle background image conversion to data URLs."""
    kwargs["background_color"] = "rgba(0,0,0,0)"
    bg_img = kwargs.get("background_image")
    
    if bg_img is not None:
        width, height = kwargs.get("width"), kwargs.get("height")
        # PERFORMANCE: Cache key MUST include render_hash and comparison state to detect changes
        comp_flag = str(st.session_state.get("show_comparison", False))
        r_hash = str(st.session_state.get("render_id", 0))
        cache_key = f"bg_url_cache_{r_hash}_{comp_flag}"
        
        if cache_key in st.session_state:
            url = st.session_state[cache_key]
        else:
            url = image_to_url_patch(bg_img, width, True, "RGB", "JPEG", r_hash)
            st.session_state[cache_key] = url
        
        if not kwargs.get("initial_drawing"):
            kwargs["initial_drawing"] = {"version": "4.4.0", "objects": []}
            
        kwargs["initial_drawing"]["background"] = "rgba(0,0,0,0)"
        kwargs["initial_drawing"]["backgroundImage"] = {
            "type": "image", "version": "4.4.0", "originX": "left", "originY": "top",
            "left": 0, "top": 0, "width": width, "height": height, "scaleX": 1, "scaleY": 1,
            "visible": True, "src": url
        }
        if "background_image" in kwargs:
             del kwargs["background_image"]
            
    return raw_st_canvas(*args, **kwargs)

# --- STYLES ---
def setup_styles():
    css_path = os.path.join(os.path.dirname(__file__), "..", "assets", "style.css")
    style_content = ""
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            style_content = f.read()
            
    # Combined static and dynamic CSS
    pass
    
    full_css = textwrap.dedent(f"""
        <style>
        {style_content}
        
        /* Force Light Theme */
        :root {{
            --primary-color: #ff4b4b;
            --background-color: #ffffff;
            --secondary-background-color: #f0f2f6;
            --text-color: #31333F;
            --font: "Segoe UI", sans-serif;
        }}
        

        /* 📱 MOBILE PINCH-ZOOM LOCKDOWN */
        html, body, .stApp {{
            overflow: hidden !important;
            touch-action: none !important;
            overscroll-behavior: none !important;
            height: 100% !important;
            width: 100% !important;
            position: fixed !important;
        }}
        
        /* 🔓 Allow Sidebar Scrolling */
        [data-testid="stSidebar"] {{
            touch-action: pan-y !important;
        }}

        iframe[title="streamlit_drawable_canvas.st_canvas"], 
        .element-container iframe,
        [id$="-overlay"] {{
            touch-action: none !important;
            -webkit-touch-callout: none !important;
            -webkit-user-select: none !important;
            user-select: none !important;
            -webkit-user-drag: none !important;
            user-drag: none !important;
            pointer-events: auto !important;
        }}

        /* 🛑 GLOBAL CONTEXT MENU KILLER */
        html, body, .stApp {{
            -webkit-touch-callout: none !important;
        }}
        
        [data-testid="stSidebar"] {{
            background-color: #f8f9fa !important; 
            border-right: 1px solid #e6e6e6;
            width: 350px !important;
        }}

        @media (min-width: 769px) {{
            .m-open-container, .desktop-only {{ display: none !important; }}
        }}

        /* 🔓 GLOBAL TOGGLE PERSISTENCE (Clean Icon-Only) */
        header[data-testid="stSidebarHeader"] {{
            visibility: visible !important;
            display: flex !important;
            justify-content: space-between !important;
            align-items: center !important;
            padding: 10px 15px !important;
            background: transparent !important;
        }}

        [data-testid="stSidebarCollapseButton"] {{
            visibility: visible !important;
            display: flex !important;
            opacity: 1 !important;
        }}

        [data-testid="stSidebarCollapseButton"] button {{
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
            color: #31333F !important;
            padding: 0 !important;
            width: auto !important;
            height: auto !important;
        }}

        [data-testid="stSidebarCollapseButton"] button:hover {{
            background: rgba(0,0,0,0.05) !important;
            border-radius: 4px !important;
        }}

        /* Clean positioning for the bare icons */
        [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {{
            position: absolute !important;
            top: 15px !important;
            right: 15px !important;
            z-index: 10000 !important;
        }}

        section[data-testid="stMain"] [data-testid="stSidebarCollapseButton"] {{
            position: fixed !important;
            top: 15px !important;
            left: 15px !important;
            z-index: 10000 !important;
        }}

        /* Icon Styling */
        [data-testid="stSidebarHeader"] svg {{
            fill: #31333F !important;
            width: 22px !important;
            height: 22px !important;
        }}

        @media (max-width: 768px) {{
            .desktop-only {{ display: none !important; }}
            
            /* 📱 MOBILE PINCH-ZOOM LOCKDOWN */
        html, body, .stApp {{
            touch-action: manipulation !important;
            overscroll-behavior-y: none;
        }}

        iframe[title="streamlit_drawable_canvas.st_canvas"], 
        .element-container iframe,
        [id$="-overlay"] {{
            touch-action: none !important;
            -webkit-touch-callout: none !important;
            -webkit-user-select: none !important;
            user-select: none !important;
            -webkit-user-drag: none !important;
            user-drag: none !important;
            pointer-events: auto !important;
        }}

        /* 🛑 GLOBAL CONTEXT MENU KILLER */
        html, body, .stApp {{
            -webkit-touch-callout: none !important;
        }}

        [data-testid="stSidebar"] {{
                transition: transform 0.3s cubic-bezier(0, 0, 0.2, 1) !important;
                /* Base state: constrained but not forced width (allows collapsing) */
                max-width: 85vw !important; 
                padding: 0 !important; /* KILL PARENT PADDING (Fixes Red Ghost) */
                overflow-x: hidden !important; 
            }}
            
            /* FORCE WIDTH ONLY WHEN OPEN */
            [data-testid="stSidebar"][aria-expanded="true"] {{
                width: 85vw !important;
                min-width: 85vw !important;
            }}
            
            /* FORCE COLLAPSE WHEN CLOSED */
            [data-testid="stSidebar"][aria-expanded="false"] {{
                width: 0 !important;
                min-width: 0 !important;
                margin-left: 0 !important;
                padding: 0 !important;
                overflow: hidden !important;
                transform: translateX(-100%) !important;
            }}

            /* Ensure main content expands fully */
            section.main {{
                margin-left: 0 !important;
                width: 100% !important;
                max-width: 100vw !important; /* Safety */
            }}
            
            /* Restore padding on inner content container */
            [data-testid="stSidebar"] > div:first-child {{
                width: 100% !important;
                min-width: 100% !important;
                padding-top: 50px !important; /* Space for close button */
                padding-left: 20px !important;
                padding-right: 20px !important;
                padding-bottom: 50px !important;
            }}

            /* DO NOT HIDE [data-testid="stSidebar"] + div as it is the main workspace */
            /* 🚫 Instead, just neutralize the overlay via JS only */

            .mobile-bottom-actions {{
                position: fixed;
                bottom: 20px;
                left: 10px;
                right: 10px;
                background: rgba(255, 255, 255, 0.95);
                backdrop-filter: blur(15px);
                padding: 12px;
                border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.2);
                z-index: 1000;
                border: 1px solid rgba(255,255,255,0.3);
            }}
            
            .main .block-container {{
                padding-bottom: 140px !important;
                padding-top: 1rem !important;
            }}
        }}

        /* 💎 Ultra-Compact Sidebar */
        .sidebar-divider {{
            height: 1px;
            background: rgba(0,0,0,0.05);
            margin: 5px 0 !important;
            width: 100%;
        }}

        .sidebar-card {{
            padding: 2px 0 !important;
            margin-bottom: 2px !important;
            background: transparent !important;
            border: none !important;
            box-shadow: none !important;
        }}

        .sidebar-header-text {{
            font-size: 0.8rem !important;
            font-weight: 700;
            color: #666;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 5px !important;
            display: flex;
            align-items: center;
            gap: 6px;
        }}


        /* Restored native overlay behavior */

        /* Hide Ghost Sync Button */
        div[data-testid="stButton"]:has(button p:contains("GHOST")) {{ display: none !important; }}
        div[data-testid="stButton"]:has(button:contains("GHOST")) {{ display: none !important; }}
        div[data-testid="stButton"]:has(button p:contains("GLOBAL SYNC")) {{ display: none !important; }}
        div[data-testid="stButton"]:has(button:contains("GLOBAL SYNC")) {{ display: none !important; }}

        /* Fully restored native layout behavior */
        
        div.element-container:has(#global-sync-anchor),
        div.element-container:has(.global-sync-marker),
        div.element-container:has(.sync-ghost-marker) {{
            display: none !important;
            height: 0 !important;
            margin: 0 !important;
            padding: 0 !important;
            position: fixed !important;
            top: -10000px !important;
        }}

        .element-container:has(.sync-ghost-marker)+.element-container,
        .element-container:has(.global-sync-marker)+.element-container,
        div.element-container:has(#global-sync-anchor)+div.element-container,
        div.element-container:has(button[key="global_sync_btn"]) {{
            display: none !important;
            position: fixed !important;
            top: -10000px !important;
            width: 0 !important;
        }}
        
        /* Buttons Styling */
        .stButton>button {{
            border-radius: 8px !important;
            font-weight: 600 !important;
            transition: all 0.2s !important;
        }}

        /* Landing Page Centering */
        .landing-container {{
            text-align: center !important;
            padding: 4rem 1rem !important;
            max-width: 800px !important;
            margin: 0 auto !important;
        }}

        .landing-header h1 {{
            font-size: 2.8rem !important;
            font-weight: 800 !important;
            color: #111827 !important;
            margin-bottom: 1rem !important;
        }}

        .landing-sub p {{
            font-size: 1.2rem !important;
            color: #4b5563 !important;
            margin-bottom: 2rem !important;
        }}
        </style>
    """).strip()
    
    st.markdown(full_css, unsafe_allow_html=True)

    # --- SILENCE CONSOLE WARNINGS & LOCK VIEWPORT ---
    st.markdown("""
        <script>
        (function() {
            // 🔒 LOCK VIEWPORT (Prevent Page Zoom)
            const meta = window.parent.document.createElement('meta');
            meta.name = 'viewport';
            meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover';
            
            // Check if meta exists, replace if so, else append
            const existing = window.parent.document.querySelector('meta[name="viewport"]');
            if (existing) {
                existing.content = meta.content;
            } else {
                window.parent.document.getElementsByTagName('head')[0].appendChild(meta);
            }

            const _backupWarn = console.warn;
            const _backupError = console.error;
            
            console.warn = function() {
                if (arguments[0] && typeof arguments[0] === 'string' && arguments[0].includes('Streamlit')) return;
                _backupWarn.apply(console, arguments);
            };
            console.error = function() {
                if (arguments[0] && typeof arguments[0] === 'string' && arguments[0].includes('Streamlit')) return;
                _backupError.apply(console, arguments);
            };

            // 📏 CONTAINER WIDTH REPORTER
            // Measures the actual available main content area width and reports
            // back to Python via ?container_w= query param so display_width is
            // accurate on any environment (Local, Cloud, narrow screens).
            const _reportContainerWidth = () => {
                try {
                    const doc = window.parent.document;
                    // Try to find the main block container
                    const mainBlock = doc.querySelector('.main .block-container');
                    if (!mainBlock) return;
                    const rect = mainBlock.getBoundingClientRect();
                    const availW = Math.floor(rect.width);
                    if (!availW || availW < 200) return;

                    // Only report if changed significantly (>10px drift)
                    const lastReported = parseInt(window.parent._lastReportedContainerW || '0');
                    if (Math.abs(availW - lastReported) < 10) return;

                    window.parent._lastReportedContainerW = availW;

                    // Report via query param (same mechanism as tap/box/pan)
                    const url = new URL(window.parent.location.href);
                    url.searchParams.set('container_w', availW);
                    // Use replaceState to avoid navigation/history pollution
                    window.parent.history.replaceState(null, '', url.toString());
                    // Also trigger a Streamlit query_params update by setting via
                    // the parent's Streamlit object if available
                    if (window.parent.streamlitApi) {
                        try { window.parent.streamlitApi.setComponentValue(availW); } catch(e) {}
                    }
                } catch(e) {}
            };

            // Report once on load and again after 500ms (layout settle)
            setTimeout(_reportContainerWidth, 300);
            setTimeout(_reportContainerWidth, 1000);
            // Also report on resize
            window.parent.addEventListener('resize', _reportContainerWidth);

            // 📱 SIDEBAR BUTTON PERMANENCE (No-Hover Fix)
            const ensureUI = () => {
                try {
                    const doc = window.parent.document;
                    // Neutralize the background overlay that closes the sidebar on random taps
                    const overlayers = doc.querySelectorAll('[data-testid="stSidebar"] + div');
                    overlayers.forEach(ov => {
                        if (!ov.id && !ov.classList.contains('stMain')) {
                             ov.style.pointerEvents = 'none';
                             ov.style.opacity = '0';
                        }
                    });
                } catch(e) {}
            };
            
            setInterval(ensureUI, 500); 
            window.parent.addEventListener('mouseup', ensureUI);
            window.parent.addEventListener('touchend', ensureUI);
        })();
        </script>
    """, unsafe_allow_html=True)


# --- FRAGMENTS ---
def sidebar_paint_fragment():
    """Isolates the color picker to prevent full app reruns on color change."""
    st.subheader("🖌️ Paint Mode")
    active_color = st.session_state.get("picked_color", "#8FBC8F")
    
    with st.container(border=True):
        col_p, col_t = st.columns([0.3, 0.7])
        active_color = st.session_state.get("picked_color", "#8FBC8F")
        with col_p:
            new_color = st.color_picker("Color", active_color, label_visibility="collapsed", key="sidebar_paint_cp")
        with col_t:
             st.markdown(f"""
             <div style="display: flex; flex-direction: column; justify-content: center; height: 35px;">
                <span style="font-family: 'Segoe UI', sans-serif; font-weight: 700; color: #31333F; font-size: 14px; line-height: 1.2;">Active Paint</span>
                <span style="color: #666; font-size: 11px; font-family: monospace;">{new_color}</span>
             </div>
             """, unsafe_allow_html=True)
    
    if new_color != active_color:
        st.session_state["picked_color"] = new_color
        # No rerun needed here as fragment handles local update


def render_zoom_controls(key_suffix="", context_class=""):
    """Render touch-only zoom controls.

    Zoom is handled entirely by pinch-to-zoom gestures (canvas_touch_handler.js).
    This function only shows a Reset View button when the user is currently zoomed
    in, so they can snap back to the default view.

    Args:
        key_suffix: Unique suffix for widget keys to prevent duplicates.
        context_class: CSS class for responsive hiding.
    """
    import streamlit.components.v1 as _components

    if context_class:
        st.markdown(f'<div class="{context_class}">', unsafe_allow_html=True)

    # Only show Reset View when user has zoomed/panned via pinch gesture.
    # We check JS-side state via a small script to keep the button visible
    # even though session_state["zoom_level"] may not reflect client-side zoom.
    reset_html = """
    <script>
    (function() {
        const _findCanvas = () => {
            const doc = window.parent ? window.parent.document : document;
            for (const f of doc.querySelectorAll('iframe')) {
                try {
                    const w = f.contentWindow;
                    if (w && typeof w.applyResponsiveScale === 'function') return w;
                } catch(e) {}
            }
            return null;
        };

        const btn = document.getElementById('ag-reset-only-btn');
        if (btn) {
            // Show/hide based on actual JS zoom state (not server state)
            const cw = _findCanvas();
            if (cw) {
                const isZoomed = (cw.userZoomLevel || 1.0) > 1.02
                              || Math.abs(cw.panX || 0) > 2
                              || Math.abs(cw.panY || 0) > 2;
                btn.style.display = isZoomed ? 'block' : 'none';
            }

            btn.onclick = () => {
                const cw2 = _findCanvas();
                if (!cw2) return;
                cw2.userZoomLevel = 1.0;
                cw2.panX = 0;
                cw2.panY = 0;
                if (cw2._pinch) cw2._pinch.active = false;
                cw2.applyResponsiveScale();
                btn.style.display = 'none';
            };
        }

        // Re-check every second so button appears after a pinch gesture
        setInterval(() => {
            const b = document.getElementById('ag-reset-only-btn');
            if (!b) return;
            const cw = _findCanvas();
            if (!cw) return;
            const isZoomed = (cw.userZoomLevel || 1.0) > 1.02
                          || Math.abs(cw.panX || 0) > 2
                          || Math.abs(cw.panY || 0) > 2;
            b.style.display = isZoomed ? 'block' : 'none';
        }, 1000);
    })();
    </script>
    <style>
    #ag-reset-only-btn {
        display: none;
        width: 100%; height: 38px;
        border: 1px solid rgba(49,51,63,0.2);
        background: #fff; color: #31333F;
        border-radius: 6px; font-size: 14px; font-weight: 600;
        cursor: pointer; touch-action: manipulation;
        box-shadow: 0 1px 3px rgba(0,0,0,0.07);
        -webkit-tap-highlight-color: transparent;
    }
    #ag-reset-only-btn:active { background: #f0f2f6; }
    </style>
    <button id="ag-reset-only-btn" aria-label="Reset View">🎯 Reset View</button>
    """
    _components.html(reset_html, height=50, scrolling=False)

    if context_class:
        st.markdown('</div>', unsafe_allow_html=True)




@st.fragment
def render_visualizer_canvas_fragment_v11(display_width, start_x, start_y, view_w, view_h, scale_factor, h, w, drawing_mode):
    """Isolated heavy-lifting fragment for canvas and backend mask generation."""
    # --- 1. CAPTURE & CLEAR INTERACTION PARAMS ---
    query_params = st.query_params
    mobile_tap = query_params.get("tap", "")
    mobile_box = query_params.get("box", "")
    mobile_pan = query_params.get("pan_update", "")
    mobile_zoom = query_params.get("zoom_update", "")
    url_pts_raw = query_params.get("poly_pts", "")
    force_finish_raw = query_params.get("force_finish", "")
    
    # 🧼 TOOL SWITCH CLEANUP (Silent)
    if st.session_state.get("tool_switched_reset", False):
        st.session_state["tool_switched_reset"] = False
        components.html("<script>if(window.parent.STREAMLIT_POLY_POINTS) window.parent.STREAMLIT_POLY_POINTS = [];</script>", height=0)

    # Signal ID Handling: Normalize signals to extract timestamp if present
    def extract_signal(raw_str):
        if not raw_str or (isinstance(raw_str, str) and raw_str.strip() == ""): return None, None
        if isinstance(raw_str, list): raw_str = raw_str[0]
        parts = raw_str.split(",")
        
        # If the last part looks like a timestamp (lengthy digit string)
        if len(parts) >= 2:
            last_part = parts[-1].strip()
            if len(last_part) >= 10 and last_part.isdigit():
                return ",".join(parts[:-1]), last_part
        return raw_str, None

    mobile_tap, tap_sid = extract_signal(mobile_tap)
    mobile_box, box_sid = extract_signal(mobile_box)
    mobile_pan, pan_sid = extract_signal(mobile_pan)
    force_finish, finish_sid = extract_signal(force_finish_raw)
    is_finish = (force_finish == "true") or st.session_state.get("force_finish_poly", False)

    # SILENT LOOP BREAKER: Guard against rapid successive fragment reruns
    is_guarded = st.session_state.get("loop_guarded", False)
    has_interaction = any([mobile_tap, mobile_box, mobile_pan, mobile_zoom, url_pts_raw])
    
    # Skip heavy signal processing if guarded, but DO NOT return (renders canvas)
    # UNLESS it is a finish command which is high priority
    skip_processing = has_interaction and is_guarded and not is_finish
    
    if skip_processing:
        # Clear signals immediately to break potential loop
        for pk in ["tap", "box", "pan_update", "zoom_update", "poly_pts"]:
            if pk in st.query_params: st.query_params.pop(pk, None)
    
    if has_interaction and not skip_processing:
        st.session_state["loop_guarded"] = True
        print(f"DEBUG: Processing Interaction -> Tool:{drawing_mode}, Tap:{bool(mobile_tap)}, Box:{bool(mobile_box)}, Finish:{is_finish}")

    # --- 🔔 TOP ACTION BAR (Immediate Visibility) ---
    # Render Apply/Cancel buttons at the TOP for mobile accessibility
    if st.session_state.get("pending_selection") is not None:
        op_label = "Add"
        if st.session_state.get("selection_op") == "Subtract":
            op_label = "Subtract"
            btn_label = "🧹 ERASE PAINT"
            btn_type = "secondary" # Use secondary color for erase/destructive action? OR stick with primary. Let's stick with primary but change label.
        else:
            btn_label = "✨ APPLY PAINT"
            btn_type = "primary"
            
        st.info(f"✨ Selection Active ({op_label})! Confirm below.", icon="👇")
        
        with st.container(border=True):
            cols = st.columns([1, 1], gap="small")
            with cols[0]: 
                # DYNAMIC LABEL BASED ON OP
                if st.button(btn_label, use_container_width=True, key="top_frag_apply", type="primary"):
                    print(f"DEBUG: PROCEEDING WITH OP: {op_label}")
                    cb_apply_pending(); safe_rerun()
            with cols[1]: 
                if st.button("🗑️ CANCEL", use_container_width=True, key="top_frag_cancel"):
                    cb_cancel_pending(); safe_rerun()

    # 1️⃣ Enforce Mode-First Rendering (BEFORE any paint logic)
    gray_mode = st.session_state.get("grayscale_mode", False)
    if gray_mode:
        if "image_gray" not in st.session_state or st.session_state["image_gray"] is None:
            from paint_utils.image_processing import to_grayscale_rgb
            st.session_state["image_gray"] = to_grayscale_rgb(st.session_state["image"])
        base_image = st.session_state["image_gray"]
    else:
        base_image = st.session_state["image"]

    original_img = st.session_state["image"]   # always the color original
    
    # 🛑 OVERRIDE: Enforce Full-Image Rendering to support smooth Client-Side Zoom
    # display_width is passed in from render_visualizer_engine_v11 — it is already
    # capped at 800 (the intrinsic canvas resolution) and respects container width.
    # Do NOT re-hardcode to 800 here.
    pass
    start_x, start_y = 0, 0
    view_w, view_h = w, h
    # scale_factor maps canvas pixels → image pixels. Since display_width == canvas intrinsic
    # width (both capped at 800), this is always w/display_width (usually 1.0 when image
    # was resized to 800 on upload).  The JS CSS transform (baseScale) does NOT affect this
    # because clicks are already decoded in canvas-pixel space by the JS before sending.
    scale_factor = display_width / w if w > 0 else 1.0
    
    # 3️⃣ Apply paint layers onto the strictly selected base_image
    # The native ColorTransferEngine correctly maps color over grayscale.
    from paint_utils.image_processing import composite_image
    painted_img = composite_image(base_image, st.session_state["masks"])
    show_comp = st.session_state.get("show_comparison", False)
    
    # In compare mode show base (gray or color), else painted
    if show_comp:
        display_img = base_image
    else:
        display_img = painted_img
    # Use full image (no cropping)
    cropped_view = display_img
    new_h = int(h * (display_width / w))
    final_display_image = cv2.resize(cropped_view, (display_width, new_h), interpolation=cv2.INTER_LINEAR)
    


    display_height = final_display_image.shape[0]
    sam = get_sam_engine(CHECKPOINT_PATH, MODEL_TYPE)

    # --- 🎯 MOBILE TAP HANDLED AT TOP LEVEL in app.py ---

    if mobile_box and mobile_box.strip() != "" and not skip_processing:
        # SIGNAL GUARD: Ensure we only process this specific box ONCE
        if box_sid and box_sid == st.session_state.get("last_box_sid"):
            mobile_box = None
        else:
            if box_sid: st.session_state["last_box_sid"] = box_sid

        if mobile_box:
            try:
                print(f"DEBUG: Msg received -> {mobile_box}")
                # Support multiple boxes separated by '|'
                box_strs = mobile_box.split("|")
                accumulated_mask = None
                last_box_coords = None

                for b_str in box_strs:
                    print(f"DEBUG: Processing box token -> {b_str}")
                    parts = b_str.split(",")
                    if len(parts) < 4: 
                        print("DEBUG: Invalid parts length")
                        continue
                    
                    # Extract coords (ignore timestamp)
                    x1, y1, x2, y2 = float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])
                    print(f"DEBUG: Parsed Coords -> {x1}, {y1}, {x2}, {y2}")
                    
                    # Convert to real image coordinates
                    bx1 = int(x1 / scale_factor) + start_x
                    by1 = int(y1 / scale_factor) + start_y
                    bx2 = int(x2 / scale_factor) + start_x
                    by2 = int(y2 / scale_factor) + start_y
                    
                    # Ensure properly ordered coordinates
                    final_box = [min(bx1, bx2), min(by1, by2), max(bx1, bx2), max(by1, by2)]
                    last_box_coords = final_box

                    # Validate size
                    if abs(final_box[2] - final_box[0]) > 5 and abs(final_box[3] - final_box[1]) > 5:
                        with st.spinner("🧠 AI is analyzing image..."):
                            sam.set_image(st.session_state["image"])
                            
                        mask = sam.generate_mask(
                            box_coords=final_box, 
                            level=st.session_state.get("mask_level", 0), 
                            is_wall_only=st.session_state.get("is_wall_only", False)
                        )
                        
                        if mask is not None:
                             if accumulated_mask is None: accumulated_mask = mask
                             else: accumulated_mask = np.logical_or(accumulated_mask, mask)

                if accumulated_mask is not None:
                    st.session_state["pending_selection"] = {'mask': accumulated_mask}
                    st.session_state["pending_box_coords"] = last_box_coords 
                    
                    # ⚡ AUTO-APPLY
                    cb_apply_pending()

                    st.session_state["render_id"] += 1
                    st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                    
                    safe_rerun()
                
                st.query_params.pop("box", None)
            except Exception as e:
                print(f"ERROR in mobile box logic: {e}")
                import traceback
                traceback.print_exc()
                
    if mobile_pan and mobile_pan.strip() != "":
        # SIGNAL GUARD: Ensure we only process this specific pan ONCE
        if pan_sid and pan_sid == st.session_state.get("last_pan_sid"):
            mobile_pan = None # Already processed
        else:
            if pan_sid: st.session_state["last_pan_sid"] = pan_sid

        if mobile_pan:
            try:
                parts = mobile_pan.split(",")
                if len(parts) >= 2:
                    px, py = float(parts[0]), float(parts[1])
                    st.session_state["pan_x"], st.session_state["pan_y"] = max(0.0, min(1.0, px)), max(0.0, min(1.0, py))
                    st.session_state["render_id"] += 1
                
                st.query_params.pop("pan_update", None)
            except: pass

    if mobile_zoom and mobile_zoom.strip() != "":
        try:
            new_zoom = float(mobile_zoom)
            st.session_state["zoom_level"] = max(1.0, min(4.0, new_zoom))
            st.session_state["render_id"] += 1
            
            st.query_params.pop("zoom_update", None)
        except: pass

    # --- 3. PERSIST DRAWING & UNFINISHED POLYGON ---
    initial_drawing = {"version": "4.4.0", "objects": []}
    
    # Check if we just finished a polygon (to prevent ghost persistence)
    was_just_finished = st.session_state.get("just_finished_poly", False)
    # Reset for next run
    st.session_state["just_finished_poly"] = False

    if st.session_state.get("canvas_raw") and not was_just_finished:
        for obj in (st.session_state.get("canvas_raw") or {}).get("objects", []):
            obj_type = obj.get("type")
            # --- 🛠️ STRICT TOOL FILTERING ---
            # Only persist objects that belong to the CURRENT tool
            is_valid = False
            if drawing_mode == "point" and obj_type == "circle": is_valid = True
            elif drawing_mode == "rect" and obj_type == "rect": is_valid = True
            elif drawing_mode == "freedraw" and obj_type == "path": is_valid = True
            elif drawing_mode == "polygon" and obj_type == "polygon": is_valid = True
            elif drawing_mode == "transform": is_valid = True # Show all in move mode
            
            if is_valid:
                initial_drawing["objects"].append(obj)

    url_pts_raw = st.query_params.get("poly_pts", url_pts_raw)
    if url_pts_raw:
        try:
            pts = []
            for p in str(url_pts_raw).split(";"):
                if "," in p:
                    px, py = p.split(",")
                    pts.append({"x": float(px), "y": float(py)})
            if pts:
                initial_drawing["objects"].append({
                    "type": "polygon", "points": pts,
                    "left": 0, "top": 0, "width": display_width, "height": display_height,
                    "fill": "rgba(255, 75, 75, 0.2)", "stroke": "#FF4B4B", "strokeWidth": 3,
                    "selectable": False, "evented": False
                })
        except: pass

    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)", 
        stroke_width=st.session_state.get("lasso_thickness", 6), 
        stroke_color="#FF4B4B",
        background_image=final_display_image, update_streamlit=True, height=display_height, width=display_width,
        drawing_mode=drawing_mode, initial_drawing=initial_drawing, 
        point_display_radius=20 if drawing_mode in ["point", "freedraw", "polygon"] else 0,
        key=f"canvas_main_{st.session_state.get('canvas_id', 0)}", 
        display_toolbar=True
    )

    # 📱 JS Handler (Silent, no elements)
    js_file_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "js", "canvas_touch_handler.js")
    if os.path.exists(js_file_path):
        with open(js_file_path, 'r', encoding='utf-8') as f: js_template = f.read()
        if not st.session_state.get("pending_selection"): st.session_state["pending_box_coords"] = None

        # Prepare pending box for JS re-hydration (Editable Box UI)
        p_box = st.session_state.get("pending_box_coords", None)
        p_box_json = str(p_box) if p_box else "null"
        
        js_config = f"<script>const cfg={{ CANVAS_WIDTH: {display_width}, CANVAS_HEIGHT: {display_height}, CUR_PAN_X: {st.session_state['pan_x']}, CUR_PAN_Y: {st.session_state['pan_y']}, ZOOM_LEVEL: {st.session_state.get('zoom_level', 1.0)}, VIEW_W: {view_w}, IMAGE_W: {w}, VIEW_H: {view_h}, IMAGE_H: {h}, DRAWING_MODE: '{drawing_mode}', PENDING_BOX: {p_box_json} }}; window.CANVAS_CONFIG=cfg; if(window.parent) window.parent.CANVAS_CONFIG=cfg;</script><script>{js_template}</script>"
        components.html(js_config, height=0)

    # 🔄 SYNC & PROCESS (Silent)
    # DEBUG: Force log raw canvas return
    print(f"DEBUG: Canvas Render -> Tool: {drawing_mode}, Return: {canvas_result.json_data is not None}, Object Count: {len(canvas_result.json_data.get('objects', [])) if canvas_result.json_data else 0}")
    
    if canvas_result.json_data:
        json_data = canvas_result.json_data
        st.session_state["canvas_raw"] = json_data
        objects = json_data.get("objects", [])
        
        if st.session_state.get("just_applied", False):
            st.session_state["just_applied"] = False
            if objects:
                # Force clear persistence if st_canvas refused to reset
                objects = []
                st.session_state["canvas_raw"] = {}
                st.session_state["pending_boxes"] = []
                # Force another rerun to clear the UI ghost
                safe_rerun()

        tool_mode = st.session_state.get("selection_tool", "✨ AI Object (Box)")
        
        if objects:
            print(f"DEBUG: Canvas Process -> Mode: {tool_mode}, Objects: {len(objects)} Types: {[o.get('type') for o in objects]}")
            if "AI Click" in tool_mode:
                for obj in reversed(objects):
                    if obj["type"] in ["circle", "path"]:
                        rel_x, rel_y = obj["left"], obj["top"]
                        real_x, real_y = int(rel_x / scale_factor) + start_x, int(rel_y / scale_factor) + start_y
                        click_key = f"{real_x}_{real_y}_{st.session_state['picked_color']}"
                        if click_key != st.session_state.get("last_click_global"):
                            st.session_state["last_click_global"] = click_key
                            sam.set_image(st.session_state["image"])
                            current_tool = st.session_state.get("selection_tool", "")
                            is_wall_click_mode = "Wall Click" in current_tool
                            mask = sam.generate_mask(
                                point_coords=[real_x, real_y], 
                                level=st.session_state.get("mask_level", 0), 
                                is_wall_only=st.session_state.get("is_wall_only", False),
                                is_wall_click=is_wall_click_mode
                            )
                            if mask is not None:
                                st.session_state["pending_selection"] = {'mask': mask, 'point': (real_x, real_y)}
                                # ⚡ SMOOTH APPLY: Don't increment canvas_id to prevent flicker, silent mode
                                if st.session_state.get("ai_click_instant_apply", True): 
                                    cb_apply_pending(increment_canvas=False, silent=True)
                                
                                st.session_state["render_id"] += 1
                                # NO EXPLICIT RERUN - Let Streamlit auto-detect state changes
                                # safe_rerun(scope="fragment")
                        break 
            
            elif "Lasso" in tool_mode and "Polygonal" not in tool_mode:
                for obj in reversed(objects):
                    if obj["type"] == "path":
                        path_data = obj.get("path", [])
                        if path_data:
                            scaled_path = []
                            for cmd in path_data:
                                if len(cmd) > 1:
                                    scaled_cmd = [cmd[0]]
                                    for i in range(1, len(cmd), 2):
                                        scaled_cmd.append(int(cmd[i] / scale_factor) + start_x)
                                        scaled_cmd.append(int(cmd[i+1] / scale_factor) + start_y)
                                    scaled_path.append(scaled_cmd)
                            # 🎨 FILL SELECTION MODE vs 🧠 AI LASSO MODE
                            is_fill_mode = st.session_state.get("fill_selection", False)
                            
                            if is_fill_mode:
                                mask = process_lasso_path(scaled_path, w, h, thickness=st.session_state.get("lasso_thickness", 6), fill=True)
                            else:
                                # 🧠 AI LASSO MODE (Box Prompt from Lasso)
                                x_coords = [c[i] for c in scaled_path for i in range(1, len(c), 2)]
                                y_coords = [c[i+1] for c in scaled_path for i in range(1, len(c), 2)]
                                
                                if x_coords:
                                    box = [min(x_coords), min(y_coords), max(x_coords), max(y_coords)]
                                    # Ensure minimal box size
                                    if (box[2]-box[0]) > 5 and (box[3]-box[1]) > 5:
                                        sam.set_image(st.session_state["image"])
                                        current_tool = st.session_state.get("selection_tool", "")
                                        is_wall_click_mode = "Wall Click" in current_tool
                                        mask = sam.generate_mask(
                                            box_coords=box, 
                                            level=st.session_state.get("mask_level", 0), 
                                            is_wall_only=st.session_state.get("is_wall_only", False),
                                            is_wall_click=is_wall_click_mode
                                        )
                                    else:
                                        mask = np.zeros((h, w), dtype=bool)
                                else:
                                    mask = np.zeros((h, w), dtype=bool)
                                
                                # Fallback to brush if AI returns nothing (optional, but let's stick to AI-only for now to match behavior)
                                if mask is None: mask = np.zeros((h, w), dtype=bool)
                            
                            if mask.any():
                                # DEBUG: Log operation mode before applying
                                current_op = st.session_state.get("selection_op", "Unknown")
                                print(f"DEBUG: FREEHAND LASSO APPLY -> Operation: {current_op}, Mask pixels: {np.sum(mask)}, Fill: {is_fill_mode}")
                                
                                st.session_state["pending_selection"] = {'mask': mask}
                                cb_apply_pending()
                                st.session_state["render_id"] += 1
                                safe_rerun()
                        break

            elif "AI Object" in tool_mode:
                current_boxes = []
                combined_mask = None
                for obj in objects:
                    if "width" in obj and "height" in obj and obj.get("type") not in ["circle"]:
                        left, top = obj["left"], obj["top"]
                        width, height = obj["width"] * obj.get("scaleX", 1.0), obj["height"] * obj.get("scaleY", 1.0)
                        bx1, by1 = int(left / scale_factor) + start_x, int(top / scale_factor) + start_y
                        bx2, by2 = int((left + width) / scale_factor) + start_x, int((top + height) / scale_factor) + start_y
                        current_boxes.append([bx1, by1, bx2, by2])
                
                if current_boxes != st.session_state.get("pending_boxes") and current_boxes:
                    st.session_state["pending_boxes"] = current_boxes
                    for box in current_boxes:
                        # 🛡️ INVALID BOX GUARD: Ignore empty or tech signals at 0,0
                        box_w, box_h = abs(box[2] - box[0]), abs(box[3] - box[1])
                        if box_w < 5 or box_h < 5: continue 
                        if box[0] == 0 and box[1] == 0: continue

                        final_box = box
                        if st.session_state.get("snap_to_edges", False): final_box = snap_box_to_edges(st.session_state["image"], box)
                        h_img, w_img = st.session_state["image"].shape[:2]
                        final_box = [max(0, min(w_img, final_box[0])), max(0, min(h_img, final_box[1])), max(0, min(w_img, final_box[2])), max(0, min(h_img, final_box[3]))]
                        
                        # 🎨 FILL SELECTION MODE (Non-AI)
                        if st.session_state.get("fill_selection", False):
                            # Create a simple rectangular mask
                            mask = np.zeros((h_img, w_img), dtype=np.bool_)
                            mask[final_box[1]:final_box[3], final_box[0]:final_box[2]] = True
                        else:
                            # Standard AI Mode
                            sam.set_image(st.session_state["image"])
                            mask = sam.generate_mask(box_coords=final_box, level=st.session_state.get("mask_level", 0), is_wall_only=st.session_state.get("is_wall_only", False))
                        
                        if mask is not None: combined_mask = mask.copy() if combined_mask is None else combined_mask | mask
                    
                    if combined_mask is not None:
                         st.session_state["pending_selection"] = {'mask': combined_mask}
                         st.session_state["render_id"] += 1
                         safe_rerun()

            elif "Polygonal Lasso" in tool_mode:
                try:
                    # Capture force finish from global parser (unifies signals)
                    if is_finish:
                        st.session_state["just_finished_poly"] = True
                        print(f"DEBUG: Lasso Logic -> is_finish trigger: {is_finish}")
                    
                    url_pts = []
                    if url_pts_raw:
                        try:
                            # 🧩 Robustly handle list or string from Streamlit query params
                            raw_str = url_pts_raw[0] if isinstance(url_pts_raw, (list, tuple)) else str(url_pts_raw)
                            

                            
                            for p in raw_str.split(";"):
                                if "," in p:
                                    try:
                                        parts = p.split(",")
                                        # Only take first 2 parts as coordinates (ignore timestamp if appended)
                                        px, py = parts[0], parts[1]
                                        url_pts.append([int(float(px) / scale_factor) + start_x, int(float(py) / scale_factor) + start_y])
                                    except: pass
                            if is_finish: print(f"DEBUG: Parsed URL Pts: {len(url_pts)}")
                        except Exception as pe: print(f"DEBUG: Poly Parse Err: {pe}")

                    target_obj = None
                    for obj in reversed(objects):
                        if obj.get("type") in ["polygon", "path"]:
                            target_obj = obj
                            break
                    
                    if force_finish:
                        print(f"DEBUG: POLY FINISH -> target_obj: {target_obj.get('type') if target_obj else 'None'}, objects_count: {len(objects)}")
                        if not target_obj and not url_pts:
                             # Print objects for deep introspection if nothing found
                             print(f"DEBUG: Canvas Objects Sample: {str(objects)[:300]}")
                    
                    if force_finish: print(f"DEBUG: Lasso Logic -> force_finish: {force_finish}, target_obj: {target_obj.get('type') if target_obj else 'None'}")
                    
                    # 🏁 FINISH TRIGGER - Only trigger on explicit FINISH button click
                    if force_finish:
                        # SIGNAL GUARD: Ensure we only process this specific finish ONCE
                        if finish_sid and finish_sid == st.session_state.get("last_finish_sid"):
                            force_finish = False # Already processed
                        else:
                            if finish_sid: st.session_state["last_finish_sid"] = finish_sid

                    if force_finish:
                        # ALWAYS clear the session state signal immediately to prevent loops
                        st.session_state["force_finish_poly"] = False 
                        pts = []
                        
                        # DEBUG: Log extraction sources
                        print(f"DEBUG: Point Extraction -> url_pts count: {len(url_pts) if url_pts else 0}, target_obj: {target_obj.get('type') if target_obj else 'None'}")
                        
                        # Priority 1: URL Points (Most stable for mobile)
                        if url_pts and len(url_pts) > 2:
                            pts = url_pts
                            print(f"DEBUG: Using URL points: {len(pts)}")
                        # Priority 2: Native Canvas Object
                        elif target_obj:
                             obj_left, obj_top = target_obj.get("left", 0), target_obj.get("top", 0)
                             if target_obj["type"] == "polygon":
                                 canvas_points = target_obj.get("points", [])
                                 print(f"DEBUG: Canvas polygon points count: {len(canvas_points)}")
                                 for p in canvas_points:
                                     pts.append([int((p["x"] + obj_left) / scale_factor) + start_x, int((p["y"] + obj_top) / scale_factor) + start_y])
                             elif target_obj["type"] == "path":
                                 # 🧩 IMPROVED PATH PARSING (Handle unclosed shapes)
                                 for cmd in target_obj.get("path", []):
                                     # Supports MoveTo (M), LineTo (L), etc.
                                     if len(cmd) >= 3:
                                         pts.append([int(cmd[1] / scale_factor) + start_x, int(cmd[2] / scale_factor) + start_y])
                                     elif len(cmd) == 2 and isinstance(cmd[1], (list, tuple)): # Some versions nested
                                         pts.append([int(cmd[1][0] / scale_factor) + start_x, int(cmd[1][1] / scale_factor) + start_y])
                        
                        if len(pts) > 2:
                            is_fill_mode = st.session_state.get("fill_selection", False)
                            print(f"DEBUG: APPLY POLYGON -> Points: {len(pts)}, Finish: {is_finish}, Fill: {is_fill_mode}")
                            
                            if is_fill_mode or "Polygonal" in tool_mode:
                                # 🎨 EXACT SHAPE (Manual Fill)
                                # Default for Polygonal Lasso to ensure precision
                                mask = np.zeros((h, w), dtype=np.uint8)
                                cv2.fillPoly(mask, [np.array(pts, np.int32)], 255)
                                final_mask = mask > 0
                                print(f"DEBUG: Exact Shape Applied (Points: {len(pts)})")
                            else:
                                # 🧠 AI SAM MASK (Using lasso as box hint)
                                sam.set_image(st.session_state["image"])
                                pts_arr = np.array(pts)
                                box = [np.min(pts_arr[:,0]), np.min(pts_arr[:,1]), np.max(pts_arr[:,0]), np.max(pts_arr[:,1])]
                                final_mask = sam.generate_mask(box_coords=box, level=st.session_state.get("mask_level", 1), is_wall_only=st.session_state.get("is_wall_only", False))

                            if final_mask is not None and final_mask.any():
                                st.session_state["pending_selection"] = {'mask': final_mask}
                                cb_apply_pending() 
                                st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                                st.session_state["render_id"] += 1
                                for pk in ["poly_pts", "force_finish", "tap"]:
                                    if pk in st.query_params: st.query_params.pop(pk, None)
                                components.html("<script>window.parent.STREAMLIT_POLY_POINTS = [];</script>", height=0)
                                safe_rerun()
                            else:
                                if force_finish: print(f"DEBUG: Skipping Poly Apply - Empty Mask")
                                for pk in ["poly_pts", "force_finish", "tap"]:
                                    if pk in st.query_params: st.query_params.pop(pk, None)
                                safe_rerun()
                        else:
                            if force_finish: 
                                print(f"DEBUG: Ignoring FINISH signal - Not enough points ({len(pts)})")
                                for pk in ["poly_pts", "force_finish", "tap"]:
                                    if pk in st.query_params: st.query_params.pop(pk, None)
                                safe_rerun()
                except Exception as e: logging.error(f"Poly Error: {e}")
                

            
            # --- 🪄 BRUSH & ERASER TOOLS ---
            elif "Paint Brush" in tool_mode or "Eraser" in tool_mode:
                for obj in reversed(objects):
                    if obj["type"] == "path":
                        # Convert canvas path to mask
                        # Assuming freehand paths have command format
                        path_data = obj.get("path", [])
                        if path_data:
                            # Parse complex path command list
                            scaled_path = []
                            for cmd in path_data:
                                if len(cmd) > 1:
                                    scaled_cmd = [cmd[0]]
                                    # Scale coordinates
                                    for i in range(1, len(cmd), 2):
                                        scaled_cmd.append(int(cmd[i] / scale_factor) + start_x)
                                        scaled_cmd.append(int(cmd[i+1] / scale_factor) + start_y)
                                    scaled_path.append(scaled_cmd)
                            
                            # Use existing path processor but enforce STROKE rendering
                            from .image_processing import process_lasso_path
                            stroke_width = st.session_state.get("lasso_thickness", 20)
                            
                            # Render the stroke into a mask
                            mask = process_lasso_path(scaled_path, w, h, thickness=stroke_width, fill=False)
                            
                            print(f"DEBUG: Found Path - Cmds:{len(scaled_path)} Thickness:{stroke_width} MaskSum:{mask.sum()}")
                           
                            if mask.any():
                                # ⚡ BRUSH MERGING LOGIC:
                                # Try to merge with the last layer if it's also a brush layer of the same color
                                color = st.session_state.get("picked_color", "#8FBC8F")
                                op = st.session_state.get("selection_op", "Add")
                                
                                merged = False
                                if st.session_state["masks"]:
                                    last_layer = st.session_state["masks"][-1]
                                    # Check if compatible for merging
                                    is_brush_layer = last_layer.get("type") == "brush"
                                    is_same_color = last_layer.get("color") == color
                                    # We didn't store op specifically before, but brush layers are usually additive unless labeled
                                    # Let's start storing 'op' in layer metadata for robust merging
                                    is_same_op = last_layer.get("op", "Add") == op 
                                    
                                    if is_brush_layer and is_same_color and is_same_op:
                                        # Merge mask
                                        target_mask = last_layer['mask']
                                        if sparse.issparse(target_mask): target_mask = target_mask.toarray()
                                        
                                        if op == "Add":
                                            last_layer['mask'] = target_mask | mask
                                        else:
                                            # For subtract, we are likely erasing from previous layers.
                                            # However, if we are in 'Eraser Mode' and just did a stroke, 
                                            # and now do another stroke, we probably want to combine these 
                                            # two 'Eraser Strokes' into one big 'Eraser Action'?
                                            # Actually, 'Subtract' operation usually applies immediately to ALL layers in cb_apply_pending.
                                            # So merging 'Subtract' strokes doesn't make sense the same way 'Add' does 
                                            # because 'Subtract' is destructive and doesn't create a new layer to merge into.
                                            # It modifies existing layers.
                                            pass 
                                        
                                        # ONLY Merge 'Add' operations. 'Subtract' operations are applied destructively to all layers instantly.
                                        if op == "Add":
                                            # Invalidate cache for this layer
                                            if "flattened_cache" in st.session_state:
                                                st.session_state["flattened_cache"] = st.session_state["flattened_cache"][:-1]
                                                
                                            merged = True
                                            print(f"DEBUG: Merged brush stroke into Layer {len(st.session_state['masks'])}")

                                if not merged:
                                    # Standard new layer if no merge possible
                                    st.session_state["pending_selection"] = {'mask': mask}
                                    
                                    # Respect global operation mode (Add/Subtract)
                                    cb_apply_pending(increment_canvas=True)
                                    
                                    # Tag as brush layer for future merges (Only if it was an ADD operation that created a layer)
                                    if st.session_state["masks"] and op == "Add":
                                        st.session_state["masks"][-1]["type"] = "brush"
                                        st.session_state["masks"][-1]["op"] = op
                                else:
                                     # Manually increment if we skipped cb_apply_pending
                                    st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                                    st.session_state["render_id"] += 1
                                
                                safe_rerun()
                        break 

            # --- 🪄 MAGIC WAND TOOL ---
            elif "Magic Wand" in tool_mode:
                 for obj in reversed(objects):
                    if obj["type"] in ["circle", "path"]: # Handle click as circle
                         rel_x, rel_y = obj["left"], obj["top"]
                         real_x, real_y = int(rel_x / scale_factor) + start_x, int(rel_y / scale_factor) + start_y
                         
                         click_key = f"{real_x}_{real_y}_wand"
                         if click_key != st.session_state.get("last_click_global"):
                             st.session_state["last_click_global"] = click_key
                             
                             from .image_processing import magic_wand_selection
                             mask = magic_wand_selection(st.session_state["image"], (real_x, real_y), tolerance=20)
                             
                             if mask is not None and mask.any():
                                 st.session_state["pending_selection"] = {'mask': mask}
                                 # Respect global operation mode (Add/Subtract)
                                 
                                 cb_apply_pending()
                                 st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                                 st.session_state["render_id"] += 1
                                 safe_rerun()
                         break

            # --- PENDING SELECTION ACTIONS (Inside Fragment) ---
            if st.session_state.get("pending_selection") is not None:
                st.toast("✨ Selection Ready! Apply or Cancel below 👇", icon="🎨")
                st.markdown("### ✨ Confirm Selection")
                with st.container(border=True):
                    b_col1, b_col2, b_col3 = st.columns([1, 0.4, 1], gap="small", vertical_alignment="center")
                    with b_col1: 
                        if st.button("✨ APPLY", use_container_width=True, key="frag_apply", type="primary"):
                            cb_apply_pending(); safe_rerun() # Fragment scope default
                    with b_col2: 
                        new_chosen = st.color_picker("Color", st.session_state.get("picked_color", "#8FBC8F"), label_visibility="collapsed", key="frag_pending_color")
                        if new_chosen != st.session_state.get("picked_color"):
                            st.session_state["picked_color"] = new_chosen
                    with b_col3: 
                        if st.button("🗑️ CANCEL", use_container_width=True, key="frag_cancel"):
                            cb_cancel_pending(); safe_rerun() # Fragment scope default

            # --- FINAL SIGNAL CLEANUP ---
            # Release guard if no interaction is currently being processed
            if not has_interaction:
                st.session_state["loop_guarded"] = False

    # --- MOBILE SYNC MARKER (Silent) ---
    st.markdown('<div class="sync-ghost-marker" style="display:none;" data-sync-id="mobile_ghost"></div>', unsafe_allow_html=True)
    
    # 5. BOTTOM NAV (Inside Fragment)
    st.markdown('<div class="mobile-zoom-wrapper" style="margin-top: 10px;"></div>', unsafe_allow_html=True)
    render_zoom_controls(key_suffix="frag", context_class="mobile-zoom-wrapper")
    
    # 6. UNDO/REDO (Inside Fragment)

    if st.session_state["masks"] or st.session_state.get("masks_redo"):
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 1])
        with btn_col1:
            if st.button("⏪ Undo", use_container_width=True, key="frag_undo_btn", disabled=not st.session_state["masks"]):
                cb_undo(); safe_rerun()
        with btn_col2:
            if st.button("⏩ Redo", use_container_width=True, key="frag_redo_btn", disabled=not st.session_state.get("masks_redo")):
                cb_redo(); safe_rerun()
        with btn_col3:
             if st.button("🗑️ Clear", use_container_width=True, key="frag_clear_btn"):
                cb_clear_all(); safe_rerun()

def render_visualizer_engine_v11(display_width):
    """De-fragmented wrapper for the canvas and external UI controls."""
    h, w, _ = st.session_state["image"].shape
    start_x, start_y, view_w, view_h = get_crop_params(w, h, st.session_state["zoom_level"], st.session_state["pan_x"], st.session_state["pan_y"])
    scale_factor = display_width / view_w
    tool_mode = st.session_state.get("selection_tool", TOOL_MAPPING["👆"])
    
    # 1. TOP TOOLBAR (Outside fragment) - HIDDEN
    # st.markdown('<div class="top-quick-toolbar" style="margin-bottom: 15px;">', unsafe_allow_html=True)
    # m_col1, m_col2, m_col3, m_col4 = st.columns([0.4, 0.2, 0.2, 0.2], gap="small", vertical_alignment="center")
    # with m_col1:
    #     # 🎯 SYNC FIX: Ensure top control follows session_state master
    #     current_icon = next((icon for icon, label in TOOL_MAPPING.items() if label == tool_mode), "👆")
    #     st.segmented_control("Tool", list(TOOL_MAPPING.keys()), default=current_icon, key="top_tool_switcher_control", label_visibility="collapsed", on_change=cb_top_tool_sync_v2)
    # with m_col2:
    #     st.toggle("Wall 🧱", value=st.session_state.get("is_wall_only", True), key="top_wall_control", label_visibility="collapsed", on_change=cb_top_wall_sync_v2)
    # with m_col3:
    #     st.segmented_control("Op", ["➕", "➖"], default="➕" if st.session_state.get("selection_op") == "Add" else "➖", key="top_op_control", label_visibility="collapsed", on_change=cb_top_op_sync)
    # with m_col4:
    #     if "Polygonal" in tool_mode:
    #         if st.button("🏁 FINISH", use_container_width=True, key="top_poly_finish", type="primary", help="Finish the polygon and apply paint."):
    #             st.session_state["force_finish_poly"] = True
    #             safe_rerun()
    #     elif st.session_state.get("pending_selection") is not None:
    #          if st.button("✨ APPLY", use_container_width=True, key="top_apply", type="primary"):
    #              cb_apply_pending()
    #              safe_rerun(scope="app")
    # st.markdown('</div>', unsafe_allow_html=True)

    # 2. COMPARISON (Outside fragment)
    if st.session_state.get("show_comparison", False):
        st.markdown("### 👁️ Comparison: Before vs After")
        c1, c2 = st.columns(2)
        
        # Mode-First Check
        gray_mode = st.session_state.get("grayscale_mode", False)
        if gray_mode:
            if "image_gray" not in st.session_state or st.session_state["image_gray"] is None:
                from paint_utils.image_processing import to_grayscale_rgb
                st.session_state["image_gray"] = to_grayscale_rgb(st.session_state["image"])
            base_image = st.session_state["image_gray"]
        else:
            base_image = st.session_state["image"]

        from paint_utils.image_processing import composite_image
        with c1: st.image(base_image, caption="Original", use_container_width=True)
        with c2: st.image(composite_image(base_image, st.session_state["masks"]), caption="Painted", use_container_width=True)
        st.divider()

    # 3. THE CANVAS (Isolated fragment)
    if "AI Click" in tool_mode or "Wall Click" in tool_mode: drawing_mode = "point"
    elif "AI Object" in tool_mode: drawing_mode = "rect" if st.session_state.get("ai_drag_sub_tool") == "🆕 Draw New" else "transform"
    elif "Lasso" in tool_mode and "Polygonal" not in tool_mode: drawing_mode = "freedraw"
    elif "Paint Brush" in tool_mode or "Eraser" in tool_mode: drawing_mode = "freedraw"
    elif "Polygonal" in tool_mode: drawing_mode = "polygon"
    elif "Magic Wand" in tool_mode: drawing_mode = "point"
    else: drawing_mode = "transform"
    
    # Calculate height based on image aspect ratio and chosen display width
    display_height = int(h * (display_width / w))
    
    render_visualizer_canvas_fragment_v11(display_width, start_x, start_y, view_w, view_h, scale_factor, h, w, drawing_mode)

    # UI Controls (Zoom, Undo, etc.) have been moved INSIDE the fragment
    pass

    # Removed tuning_container from top - moved to bottom



def render_sidebar(sam, device_str):
    # --- 🌐 EXTRACT TRACKED POINTS (FOR DEBUG) ---
    url_pts_count = 0
    raw_param = st.query_params.get("poly_pts")
    if raw_param:
        try:
            if isinstance(raw_param, (list, tuple)): raw_pts_str = raw_param[0]
            else: raw_pts_str = str(raw_param)
            url_pts_count = len(raw_pts_str.split(";")) if raw_pts_str else 0
        except: pass



    with st.sidebar:
        # --- Native Sidebar Logic handles close ---
        pass

        st.markdown("""
            <div style='display:flex; align-items:center; gap:8px; margin-bottom: 10px; padding-bottom: 5px; border-bottom: 1px solid #eee;'>
                <div style='background: #FF4B4B; width: 28px; height: 28px; border-radius: 6px; display:flex; align-items:center; justify-content:center; color:white; font-size:16px;'>🖌️</div>
                <h3 style='margin:0; padding:0; color:#1f2937; font-size: 1rem; font-weight: 700;'>Visualizer Studio</h3>
            </div>
        """, unsafe_allow_html=True)
        
        # Reset button removed as per user request (Option 1)

        if "uploader_id" not in st.session_state:
            st.session_state["uploader_id"] = 0

        uploader_key = f"uploader_{st.session_state.get('uploader_id', 0)}"
        
        # HIDE UPLOADER IF IMAGE EXISTS (Expanded=False)
        is_image_loaded = st.session_state.get("image") is not None
        expander_label = "📂 Change Image" if is_image_loaded else "📂 Upload Image"
        
        with st.expander(expander_label, expanded=not is_image_loaded):
             uploaded_file = st.file_uploader("Start Project", type=["jpg", "png", "jpeg", "webp", "bmp", "tiff"], label_visibility="collapsed", key=uploader_key)
             
             # RESET BUTTON NOW INSIDE EXPANDER
             if is_image_loaded:
                  if st.button("️ Reset Project / Clear All", use_container_width=True):
                    st.session_state["image"] = None
                    st.session_state["image_gray"] = None
                    st.session_state["image_path"] = None
                    st.session_state["masks"] = []
                    for k in list(st.session_state.keys()):
                        if any(k.startswith(p) for p in ["bg_url_cache_", "base_l_", "comp_cache_"]):
                            del st.session_state[k]
                    st.session_state["render_cache"] = None
                    st.session_state["composited_cache"] = None
                    st.cache_data.clear()
                    st.session_state["uploader_id"] += 1 
                    preserve_sidebar_state()
                    safe_rerun()
        
        if uploaded_file is not None:
            import hashlib
            uploaded_file.seek(0)
            file_bytes_raw = uploaded_file.read()
            file_hash = hashlib.sha256(file_bytes_raw).hexdigest()
            
            # We enforce reprocessing if the file_hash changes OR if `image` state is None 
            # (which happens if they wiped out state but Streamlit kept the uploaded_file instance natively)
            if st.session_state.get("image_path") != file_hash or st.session_state.get("image") is None:
                st.toast(f"📸 Loading New Image: {uploaded_file.name}", icon="🔄")
                file_bytes = np.asarray(bytearray(file_bytes_raw), dtype=np.uint8)
                image = cv2.cvtColor(cv2.imdecode(file_bytes, 1), cv2.COLOR_BGR2RGB)
                st.session_state["image_original"] = image.copy()
                from app_config.constants import PerformanceConfig
                max_dim = PerformanceConfig.MAX_IMAGE_DIMENSION
                h, w = image.shape[:2]
                if max(h, w) > max_dim:
                    scale = max_dim / max(h, w)
                    image = cv2.resize(image, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
                st.session_state["image"] = image
                st.session_state["image_gray"] = None
                st.session_state["image_path"] = file_hash
                st.session_state["masks"] = []
                st.session_state["pending_selection"] = None
                st.session_state["pending_boxes"] = []
                st.session_state["last_click_global"] = None
                st.session_state["zoom_level"] = 1.0
                st.session_state["pan_x"] = 0.5
                st.session_state["pan_y"] = 0.5
                st.session_state["render_id"] = 0
                st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                
                # Force invalidate SAM Engine states to prevent phantom "old image" masks
                sam.is_image_set = False
                
                # 🧹 Targeted cache cleanup
                from paint_utils.performance import cleanup_session_caches
                cleanup_session_caches(aggressive=True)
                
                preserve_sidebar_state()
                st.rerun()
        
        # Auto-reset logic REMOVED to prevent accidental clearing during reruns.
        # Users must use the "Reset Project / Clear All" button inside the expander.
        elif uploaded_file is None and st.session_state.get("image") is not None:
            pass 

        if st.session_state.get("image") is None:
             st.markdown("<div style='background:#f3f4f6; padding:15px; border-radius:10px; border:1px dashed #d1d5db; margin:10px 0;'><p style='margin:0; font-size:0.85rem; color:#4b5563; line-height:1.4;'><b>Ready to paint?</b><br>Upload a photo of your wall or room to begin.</p></div>", unsafe_allow_html=True)
             st.caption("Supported: JPG, PNG, JPEG, WEBP, BMP, TIFF")
             return

        if st.session_state.get("image") is not None:
            if st.session_state["masks"]:
                _gray_mode = st.session_state.get("grayscale_mode", False)
                _dl_label = "💎 PREPARE HIGH-RES DOWNLOAD" + (" (Grayscale)" if _gray_mode else "")
                _dl_filename = "visualizer_grayscale_design.png" if _gray_mode else "pro_visualizer_design.png"
                if st.button(_dl_label, use_container_width=True, type="primary"):
                    st.toast("🎨 Professional Rendering in Progress...", icon="💎")
                    try:
                        original_img = st.session_state["image_original"]
                        oh, ow = original_img.shape[:2]
                        high_res_masks = []
                        total = len(st.session_state["masks"])
                        progress_bar = st.progress(0)
                        for i, m_data in enumerate(st.session_state["masks"]):
                            progress_bar.progress((i + 1) / total)
                            # 1. Prepare Mask
                            raw_mask = m_data['mask']
                            from scipy import sparse
                            if sparse.issparse(raw_mask):
                                raw_mask = raw_mask.toarray()
                            
                            # 2. Resize to full resolution with SMOOTHING
                            mask_f32 = raw_mask.astype(np.float32)
                            hr_mask_f32 = cv2.resize(mask_f32, (ow, oh), interpolation=cv2.INTER_LINEAR)
                            
                            # Apply smoothing to upscaled mask to prevent blockiness
                            blur_k = max(1, int(ow / 800)) * 2 + 1
                            hr_mask_smooth = cv2.GaussianBlur(hr_mask_f32, (blur_k, blur_k), 0)
                            
                            # 3. Create high-res layer obj
                            hr_m = m_data.copy()
                            hr_m['mask'] = hr_mask_smooth > 0.4 
                            high_res_masks.append(hr_m)
                        progress_bar.empty()
                        from paint_core.colorizer import ColorTransferEngine
                        
                        if st.session_state.get("grayscale_mode", False):
                            from paint_utils.image_processing import to_grayscale_rgb
                            base_dl_img = to_grayscale_rgb(original_img)
                        else:
                            base_dl_img = original_img

                        from paint_utils.image_processing import composite_image
                        dl_comp = composite_image(base_dl_img, high_res_masks)
                        dl_pil = Image.fromarray(dl_comp)
                        dl_buf = io.BytesIO()
                        dl_pil.save(dl_buf, format="PNG")
                        st.session_state["last_export"] = dl_buf.getvalue()
                        st.success("✅ Download Ready!")
                    except Exception as e:
                        st.error(f"Export failed: {e}")
                        import logging
                        logging.error(f"High-res export failed: {e}", exc_info=True)

                if st.session_state.get("last_export"):
                    _dl_fn = "visualizer_grayscale_design.png" if st.session_state.get("grayscale_mode") else "pro_visualizer_design.png"
                    st.download_button(label="📥 Save Final Image", data=st.session_state["last_export"], file_name=_dl_fn, mime="image/png", use_container_width=True)
            
            
            st.markdown('<div class="sidebar-header-text">🛠️ Selection Tool</div>', unsafe_allow_html=True)
            
            # Use standardized tool options
            tool_options = list(TOOL_MAPPING.values())
            current_tool = st.session_state.get("selection_tool", TOOL_MAPPING["👆"])
            
            radio_key = "sidebar_tool_radio"
            if radio_key not in st.session_state:
                st.session_state[radio_key] = current_tool if current_tool in tool_options else tool_options[0]

            st.radio("Method", tool_options, 
                                    horizontal=False, 
                                    key=radio_key,
                                    on_change=cb_sidebar_tool_sync,
                                    args=(radio_key,))
            
            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            
            if "sidebar_op_radio" not in st.session_state:
                st.session_state["sidebar_op_radio"] = st.session_state.get("selection_op", "Add")
                
            st.radio("Operation", ["Add", "Subtract"], 
                                    horizontal=True, 
                                    key="sidebar_op_radio",
                                    on_change=cb_sidebar_op_sync)
            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            
            # --- Tool Specific Controls (Full Width) ---
            # 🎯 HIDE LAYER SCOPE FOR POLYGONAL LASSO AND FREEHAND LASSO AND AI OBJECT (As Requested)
            # Only show scope for AI Click (Point)
            if "AI Click" in current_tool:
                st.markdown('<div class="sidebar-header-text">🎯 Layer Scope</div>', unsafe_allow_html=True)
                prec_options = ["Standard Walls", "Small Details", "Whole Object"]
                current_idx = min(st.session_state.get("mask_level", 0), 2)
                prec_mode = st.radio("Segmentation Mode", prec_options, index=current_idx, key="sidebar_prec_mode_radio", label_visibility="collapsed")
                new_level = prec_options.index(prec_mode)
                if new_level != st.session_state.get("mask_level", 0):
                    st.session_state["mask_level"] = new_level
                    safe_rerun()
                # ⚡ Always Instant Apply
                st.session_state["ai_click_instant_apply"] = True
                st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            
            # --- 🎨 BRUSH & ERASER CONTROLS ---
            elif "Paint Brush" in current_tool or "Eraser" in current_tool:
                st.markdown('<div class="sidebar-header-text">🖌️ Brush Settings</div>', unsafe_allow_html=True)
                st.slider("Brush Size", 5, 200, 40, key="lasso_thickness", help="Adjust the thickness of your brush.")
                st.caption("Draw freely on the image.")
                st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            
            # --- 🪄 MAGIC WAND CONTROLS ---
            elif "Magic Wand" in current_tool:
                st.markdown('<div class="sidebar-header-text">🪄 Wand Settings</div>', unsafe_allow_html=True)
                st.slider("Wand Tolerance", 1, 100, 25, key="wand_tolerance", help="Higher values include more similar colors.")
                st.caption("Click on a colored area to flood-fill it.")
                st.markdown('</div>', unsafe_allow_html=True)

            # 🎯 HIDE ACTION OPTIONS FOR AI OBJECT (BOX)
            # Force "Draw New" mode silently if AI Object is selected, but do not show the UI.
            if "AI Object" in current_tool:
                st.session_state["ai_drag_sub_tool"] = "🆕 Draw New"
                # st.caption("Draw a box around the object.")
            
            # 🎯 HIDE FINISH/CLEAR BUTTONS FOR POLYGONAL LASSO (Requested)
            if "Polygonal" in current_tool:
                # p_colA, p_colB = st.columns(2)
                # with p_colA:
                #     if st.button("✅ FINISH", use_container_width=True, type="primary", key="side_poly_finish", help="Complete the shape (or triple-click last point)"):
                #         st.session_state["force_finish_poly"] = True
                #         safe_rerun()
                # with p_colB:
                #     if st.button("🧹 CLEAR", use_container_width=True, key="side_poly_clear", help="Clear drawing"):
                #         st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                #         st.session_state["force_finish_poly"] = False
                #         st.query_params.pop("poly_pts", None)
                #         import streamlit.components.v1 as components
                #         components.html("<script>window.parent.STREAMLIT_POLY_POINTS = [];</script>", height=0)
                if "Polygonal Lasso" in current_tool:
                    pass
                elif "Lasso (Freehand)" in current_tool:
                    st.caption("Instructions: Draw your area. Paint applies when you release.")
            
            # 🛠️ LOGIC: If "Fill Selection" (Manual) is ON, "Wall Priority" (AI) is irrelevant
            is_fill_active = st.session_state.get("fill_selection", False)

            if "Lasso (Freehand)" in current_tool:
                st.toggle("Apply Paint Fully Inside 🎨", 
                      value=is_fill_active, 
                      key="fill_selection_toggle",
                      on_change=lambda: st.session_state.update({"fill_selection": st.session_state.fill_selection_toggle}),
                      help="**ON:** Paints the *entire* inside of your Lasso selection (Manual Mode).\n\n**OFF (AI Mode):** Uses AI to intelligently detect objects within your lasso.")

            # HIDDEN: User requested to remove this to avoid confusion. Default remains ON for accuracy.
            # st.toggle("Wall Priority Mode 🧱", 
            #           value=st.session_state.get("is_wall_only", True), 
            #           key="wall_priority_toggle",
            #           disabled=(is_fill_active and "Lasso (Freehand)" in current_tool), 
            #           on_change=lambda: st.session_state.update({"is_wall_only": st.session_state.wall_priority_toggle}),
            #           help="**ON (Default):** Stricter borders. Keeps paint on the specific wall face you clicked.\n\n**OFF:** Relaxes borders. Use this if paint is leaving gaps or for furniture/small objects.")

            # HIDDEN: User requested to remove this to avoid confusion
            # st.toggle("Fill Entire Selection (Non-AI) 🎨", 
            #           value=is_fill_active, 
            #           key="fill_selection_toggle",
            #           on_change=lambda: st.session_state.update({"fill_selection": st.session_state.fill_selection_toggle}),
            #           help="**ON:** Paints the *entire* inside of your Box or Lasso selection. Best for simple walls or when AI misses details.\n\n**OFF (AI Mode):** Uses AI to intelligently find objects within your marked area.")

            if st.session_state.get("pending_selection") is not None or st.session_state.get("pending_boxes"):
                if st.button("🚫 Clear Selection Draft", use_container_width=True, help="Reset the current selection without applying it."):
                    st.session_state["pending_selection"] = None
                    st.session_state["pending_boxes"] = []
                    st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                    safe_rerun()

            # --- Selection Layer Tuning ---
            if st.session_state.get("pending_selection") is not None:
                with st.expander("✨ Selection Layer Tuning", expanded=True):
                    # Local selection opacity (visual only for the highlight)
                    st.slider("Selection Visibility", 0.1, 1.0, 0.5, key="selection_highlight_opacity")
                    # Edge Feathering (applied before final apply)
                    st.slider("Edge Softness", 0, 5, 0, key="selection_softness", help="Feather the edges of the selection before applying paint.")
                    # Mask Expansion/Contraction
                    st.slider("Edge Refinement (Expand/Contract)", -10, 10, 0, key="selection_refinement", help="Fine-tune the mask boundary. Negative shrinks it, Positive grows it.")
                    # Finish Selection
                    st.radio("Paint Finish", ["Standard", "Matte", "Satin", "Gloss", "Texture"], horizontal=True, key="selection_finish")
                st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            
            st.markdown('<div class="sidebar-header-text">👁️ View Settings</div>', unsafe_allow_html=True)
            st.toggle("Compare Before/After", key="show_comparison")

            # ── Grayscale Preview Mode ──────────────────────────────────────
            def _on_gray_toggle():
                """Invalidate compositor cache so canvas re-renders in new mode."""
                st.session_state["comp_cache_state"] = None
                st.session_state["comp_cache_len"] = 0
                st.session_state["render_id"] += 1

            st.toggle(
                "🎨 Grayscale Preview Mode",
                key="grayscale_mode",
                on_change=_on_gray_toggle,
                help=(
                    "**ON:** Display image in grayscale. Paint colors appear only "
                    "on the areas you have painted — the rest stays gray. Download "
                    "also exports a grayscale + color result.\n\n"
                    "**OFF:** Normal colour mode."
                ),
            )

            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)


            sidebar_paint_fragment()
            st.markdown('<div class="sidebar-divider"></div>', unsafe_allow_html=True)
            st.markdown('<div class="sidebar-header-text">📚 Activity Layers</div>', unsafe_allow_html=True)
            if st.session_state["masks"] or st.session_state.get("masks_redo"):
                col_u1, col_u2, col_u3 = st.columns(3)
                with col_u1: st.button("⏪ Undo", use_container_width=True, on_click=cb_undo, key="sidebar_undo", disabled=not st.session_state["masks"])
                with col_u2: st.button("⏩ Redo", use_container_width=True, on_click=cb_redo, key="sidebar_redo", disabled=not st.session_state.get("masks_redo"))
                with col_u3: st.button("🗑️ Clear", use_container_width=True, on_click=cb_clear_all, key="sidebar_clear")
                # Removed height spacer
                for i in range(len(st.session_state["masks"]) - 1, -1, -1):
                    mask_data = st.session_state["masks"][i]
                    with st.container(border=True):
                        try: r1, r2, r3, r4 = st.columns([0.45, 0.15, 0.25, 0.15], vertical_alignment="center")
                        except: r1, r2, r3, r4 = st.columns([0.45, 0.15, 0.25, 0.15])
                        cur_c = mask_data.get('color', '#FFFFFF')
                        with r1: st.markdown(f"**Layer {i+1}**")
                        with r2: st.markdown(f"<div style='width:24px;height:24px;background:{cur_c};border-radius:4px;border:1px solid #ddd;'></div>", unsafe_allow_html=True)
                        with r3: st.markdown(f"`{cur_c}`")
                        with r4: st.button("🗑️", key=f"sidebar_del_{i}", on_click=cb_delete_layer, args=(i,))
            else: 
                st.caption("No active layers.")
                st.info("Paint something to see layers here!")


def render_comparison_slider():
    
    st.subheader('?? Compare Before / After')
    
    if st.session_state.get('image') is None:
        return

    gray_mode = st.session_state.get("grayscale_mode", False)
    if gray_mode:
        if "image_gray" not in st.session_state or st.session_state["image_gray"] is None:
            from paint_utils.image_processing import to_grayscale_rgb
            st.session_state["image_gray"] = to_grayscale_rgb(st.session_state["image"])
        base_image = st.session_state["image_gray"]
    else:
        base_image = st.session_state["image"]

    original_img = base_image
    painted_img = composite_image(original_img, st.session_state['masks'])
    
    # Convert RGB to BGR for comparison component (if needed) or keep RGB
    # image_comparison expects PIL or arrays
    
    image_comparison(
        img1=original_img,
        img2=painted_img,
        label1='Original',
        label2='Painted',
        width=700,
        starting_position=50,
        show_labels=True,
        make_responsive=True,
        in_memory=True
    )

