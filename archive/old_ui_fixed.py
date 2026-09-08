import streamlit as st
import os
import cv2
import numpy as np
import torch
import time
import io
import requests
from PIL import Image
from streamlit_drawable_canvas import st_canvas as _st_canvas_original
from .encoding import image_to_url_patch
from .state_manager import cb_undo, cb_clear_all, cb_delete_layer, cb_apply_pending, cb_cancel_pending
from .image_processing import get_crop_params, composite_image
from .sam_loader import get_sam_engine, CHECKPOINT_PATH, MODEL_TYPE

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
            
    return _st_canvas_original(*args, **kwargs)

# --- STYLES ---
def setup_styles():
    css_path = os.path.join(os.path.dirname(__file__), "..", "assets", "style.css")
    if os.path.exists(css_path):
        with open(css_path, "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    st.markdown("""
        <style>
        /* Force Light Theme */
        :root {
            --primary-color: #ff4b4b;
            --background-color: #ffffff;
            --secondary-background-color: #f0f2f6;
            --text-color: #31333F;
            --font: "Segoe UI", sans-serif;
        }
        
        /* Main App Background */
        .stApp {
            background-color: #ffffff;
        }
        
        /* Sidebar Background & Text */
        /* Sidebar - Professional Light */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa !important; 
            border-right: 1px solid #e6e6e6;
            width: 350px !important;
        }

        @media (min-width: 769px) {
            .m-open-container { display: none !important; }
        }

        /* ≡ƒ¢í∩╕Å DISABLE CLICK-OUTSIDE-TO-CLOSE */
        [data-testid="stSidebarOverlay"] {
            pointer-events: none !important;
            cursor: default !important;
        }

        .stMarkdown h3 {
            font-size: 1.1rem !important;
            font-weight: 700 !important;
            color: #1f2937 !important;
            margin-bottom: 0.5rem !important;
        }
        
        @media (max-width: 640px) {
            .stMarkdown h3 {
                font-size: 1rem !important;
            }
        }
        
        .stMarkdown h2 {
            font-size: 1.3rem !important;
            font-weight: 800 !important;
            color: #111827 !important;
        }

        /* Enhanced Card Look */
        div[data-testid="stVerticalBlockBordered"] {
            border: 1px solid #e5e7eb !important;
            border-radius: 10px !important;
            background-color: #ffffff !important;
            box-shadow: 0 1px 2px rgba(0,0,0,0.05) !important;
        }
        
        /* Sidebar collapse adjustment for the main content area */
        [data-testid="stSidebarNav"] {
            width: 350px !important;
        }
        
        /* Sidebar Text Color */
        [data-testid="stSidebar"] h1, 
        [data-testid="stSidebar"] h2, 
        [data-testid="stSidebar"] h3, 
        [data-testid="stSidebar"] p, 
        [data-testid="stSidebar"] span, 
        [data-testid="stSidebar"] div,
        [data-testid="stSidebar"] label {
            color: #31333F !important;
        }

        /* Sidebar Inputs - Standardize */
        [data-testid="stSidebar"] .stSelectbox > div > div {
            background-color: #ffffff;
            color: #31333F;
            border-color: #dcdcdc;
        }

        /* ≡ƒÜÇ SIDEBAR LAYOUT (Compressed Top) */
        [data-testid="stSidebarContent"] {
            padding-top: 0.5rem !important;
        }

        @media (max-width: 640px) {
            [data-testid="stSidebarContent"] {
                padding-top: 0.25rem !important;
                padding-left: 0.5rem !important;
                padding-right: 0.5rem !important;
            }
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: 1.25rem !important;
            margin-top: 0rem !important;
        }
        
        @media (max-width: 640px) {
            [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
                gap: 0.75rem !important;
            }
        }

        /* Ensure the first element (header) has no extra internal margin */
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div:first-child {
            margin-top: 0rem !important;
            padding-top: 0rem !important;
        }
        
        /* Ensure no bottom margin for markdown blocks */
        [data-testid="stSidebar"] .stMarkdown {
            margin-bottom: 0px !important;
        }
        
        [data-testid="stSidebar"] .stMarkdown div[data-testid="stMarkdownContainer"] p {
            margin-bottom: 0px !important;
        }

        /* Tighten Radio buttons */
        [data-testid="stSidebar"] .stRadio > div {
            gap: 2px !important;
            margin-top: 0px !important;
        }

        /* Minimize Dividers */
        [data-testid="stSidebar"] hr {
            margin-top: 0.25rem !important;
            margin-bottom: 0.25rem !important;
        }

        /* Compact File Uploader - Sane padding */
        [data-testid="stSidebar"] [data-testid="stFileUploader"] {
            padding: 5px !important;
            margin-top: 5px !important;
        }
        
        /* Adjust Active Paint Card internal spacing */
        [data-testid="stSidebar"] div[data-testid="stVerticalBlockBordered"] {
            padding: 0.75rem !important;
        }
        
        /* Sidebar container vertical gap fix */
        [data-testid="stSidebar"] .stVerticalBlock {
            gap: 1rem !important;
        }
        
        /* Reset Global Text to Dark for Main Area Only */
        .main .block-container h1, 
        .main .block-container h2, 
        .main .block-container h3, 
        .main .block-container p, 
        .main .block-container span, 
        .main .block-container div {
            color: #333333 !important;
        }
    
        /* Buttons */
        .stButton>button {
            background-color: #ffffff;
            color: #333333; /* Default button text dark */
            border: 1px solid #dcdcdc;
            border-radius: 8px;
            transition: all 0.2s;
        }
        
        /* Sidebar Buttons Specifics */
        [data-testid="stSidebar"] .stButton>button {
            background-color: #ffffff;
            color: #333333;
            border: 1px solid #dcdcdc;
        }
        [data-testid="stSidebar"] .stButton>button:hover {
            background-color: #f0f0f0;
            border-color: #bbbbbb;
        }
        
        /* File Uploader */
        [data-testid="stFileUploader"] {
            padding: 20px;
            border: 2px dashed #cccccc;
            border-radius: 10px;
            background-color: #ffffff;
            text-align: center;
        }
        
        /* Center align main landing text */
        .landing-header {
            text-align: center;
            # padding-top: 50px;
            # padding-bottom: 20px;
        }
        .landing-header h1 {
            color: #333333 !important;
        }
        .landing-sub {
            text-align: center;
            color: #666666 !important;
            font-size: 1.1rem;
            margin-bottom: 40px;
        }
        /* Force main container to use full width and ABSOLUTELY NO TOP SPACE */
        .main .block-container {
            max-width: 98% !important;
            padding-top: 0px !important;
            padding-right: 1rem !important;
            padding-left: 1rem !important;
            padding-bottom: 3rem !important;
            margin-top: 0px !important; /* Removed negative margin to prevent overlap */
        }
        
        @media (max-width: 1024px) {
            /* Aggressively allow mobile overflow and prevent right-side cut off */
            .main .block-container {
                overflow-x: auto !important;
                display: block !important;
                max-width: 100% !important;
                padding-left: 0.1rem !important;
                padding-right: 0.1rem !important;
                /* FIX: Increased top padding for clear button separation */
                padding-top: 6rem !important; 
            }
            .stApp, [data-testid="stAppViewContainer"] {
                overflow-x: auto !important;
            }
            
            /* Align to left on mobile to prevent centering-induced overflow */
            [data-testid="stVerticalBlock"] {
                align-items: flex-start !important;
                justify-content: flex-start !important;
            }
        }

        /* Sidebar content should stay left-aligned */
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            align-items: flex-start !important;
        }

        /* ≡ƒÜÇ CENTER MAIN AREA CONTENT (Desktop only) */
        @media (min-width: 769px) {
            .main [data-testid="stVerticalBlock"] {
                align-items: center !important;
            }
            
            .main [data-testid="stVerticalBlock"] > div {
                display: flex !important;
                justify-content: center !important;
                width: 100% !important;
            }
            .main .block-container {
                padding-left: 2rem !important;
                padding-right: 2rem !important;
            }
        }

        /* ≡ƒÜÇ HIDE UI NOISE (Keep Toggle Buttons) */
        [data-testid="stDecoration"],
        .stDeployButton {
            display: none !important;
        }
        
        /* Make Header Transparent but allow children (Toggle Button) */
        header {
            background-color: transparent !important;
            border-bottom: none !important;
            z-index: 999999 !important;
        }
        
        /* ≡ƒÜÇ REFINED SIDEBAR TOGGLES */
        [data-testid="stSidebarCollapseButton"] {
            display: flex !important;
            visibility: visible !important;
            opacity: 1 !important;
            z-index: 9999999 !important;
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 5px !important;
        }
        
        @media (max-width: 640px) {
            [data-testid="stSidebarCollapseButton"] {
                padding: 8px !important; /* Larger touch target for mobile */
            }
        }

        [data-testid="stSidebarCollapseButton"] svg {
            fill: #31333F !important;
            color: #31333F !important;
            width: 20px !important;
            height: 20px !important;
        }

        /* Position the 'Open' button (when sidebar closed) */
        header [data-testid="stSidebarCollapseButton"] {
            top: 5px !important;
            left: 5px !important;
        }

        /* Position the 'Close' button (when sidebar open) */
        [data-testid="stSidebar"] [data-testid="stSidebarCollapseButton"] {
            top: 5px !important;
            right: 5px !important;
            left: auto !important;
        }

        /* Sidebar Padding override - Remove top gap */
        section[data-testid="stSidebarContent"] > div:first-child {
            padding-top: 0rem !important;
        }

        /* Hide Streamlit elements */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* ≡ƒÜÇ SIMPLIFIED RESPONSIVE CANVAS - DISTORTION GUARD */
        iframe[title="streamlit_drawable_canvas.st_canvas"],
        .element-container iframe {
            /* Width/Height must be controlled by JS or attributes to prevent coordinate distortion */
            border: none !important;
            border-radius: 8px;
        }
        
        .editor-container {
            width: 100%;
            display: flex;
            justify-content: center;
            overflow: hidden;
        }
        /* Ghost Sync Hiding: Target the container immediately after the ghost marker */
        .sync-ghost-marker {
            display: none !important;
        }
        
        /* Hide any Streamlit element container that follows our ghost marker */
        .element-container:has(.sync-ghost-marker)+.element-container {
            display: none !important;
            position: fixed !important;
            top: -10000px !important;
            left: -10000px !important;
            width: 0 !important;
            height: 0 !important;
            opacity: 0 !important;
            pointer-events: none !important;
        }

        /* Redundant safety for the button itself if it escapes its container */
        div[data-testid="stButton"]:has(button[key="mobile_sync_btn_ghost"]),
        button[key="mobile_sync_btn_ghost"] {
            display: none !important;
            position: fixed !important;
            top: -10000px !important;
        }
    """, unsafe_allow_html=True)

    # --- ≡ƒ¢í∩╕Å MOBILE SIDEBAR STATE INJECTION ---
    st.markdown(f"""
        <style>
        @media (max-width: 1024px) {{
            /* 1. Hide native auto-close triggers */
            [data-testid="stSidebarCollapseButton"],
            [data-testid="stSidebarOverlay"],
            header button,
            [data-testid="stHeader"] button {{
                display: none !important;
                visibility: hidden !important;
                opacity: 0 !important;
            }}
            
            /* 2. Manual Sidebar Positioning */
            [data-testid="stSidebar"] {{
                position: fixed !important;
                top: 0 !important;
                left: 0 !important;
                height: 100vh !important;
                width: 320px !important;
                max-width: 85vw !important;
                z-index: 1000000 !important;
                background-color: #ffffff !important;
                transform: {'translateX(0)' if st.session_state.get("sidebar_p_open") else 'translateX(-100%)'} !important;
                transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1) !important;
                display: block !important;
                visibility: visible !important;
                border-right: 1px solid #e5e7eb !important;
            }}

            /* 3. Custom Button Styling via Key-Based Classes */
            /* Open Button (Floating) */
            .st-key-m_open_btn {{
                position: fixed;
                top: 25px;
                left: 10px;
                z-index: 999999;
                display: block;
                background: transparent !important;
                border: none !important;
            }}
            .st-key-m_open_btn button {{
                background: transparent !important;
                background-color: transparent !important;
                border: none !important;
                box-shadow: none !important;
                color: #31333F !important;
                padding: 0 !important;
                margin: 0 !important;
                min-height: 0px !important;
                min-width: 0px !important;
                line-height: 1 !important;
                transform: scale(1.3); /* INCREASED SIZE */
            }}
            /* Hover/Active States */
            .st-key-m_open_btn button:hover,
            .st-key-m_open_btn button:active,
            .st-key-m_open_btn button:focus {{
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                color: #31333F !important;
            }}

            /* Close Button (Inside Sidebar) */
            .st-key-m_close_btn {{
                position: absolute;
                top: 25px;
                right: 15px;
                z-index: 1000002;
                background: transparent !important;
                border: none !important;
            }}
            .st-key-m_close_btn button {{
                background: transparent !important;
                background-color: transparent !important;
                border: none !important;
                box-shadow: none !important;
                color: #31333F !important;
                padding: 0 !important;
                margin: 0 !important;
                min-height: 0px !important;
                min-width: 0px !important;
                line-height: 1 !important;
                transform: scale(1.3); /* INCREASED SIZE */
            }}
            /* Hover/Active States */
            .st-key-m_close_btn button:hover,
            .st-key-m_close_btn button:active,
            .st-key-m_close_btn button:focus {{
                background: transparent !important;
                border: none !important;
                box-shadow: none !important;
                color: #31333F !important;
            }}
        }}
        /* STRICT DESKTOP CLEANUP (> 1024px) */
        @media (min-width: 1025px) {{
            /* Hide the wrappers if they exist, but more importantly hide the keyed elements */
            .st-key-m_open_btn,
            .st-key-m_close_btn,
            div.element-container:has(.st-key-m_open_btn),
            div.element-container:has(.st-key-m_close_btn) {{
                display: none !important;
            }}
        }}
        </style>
    """, unsafe_allow_html=True)

    # # Mobile: Aggressive sidebar protection
    # st.markdown("""
    # <script>
    # (function() {
    #     if (window.innerWidth > 1024) return; // Desktop - skip
        
    #     let allowClose = false;
        
    #     // Detect when user EXPLICITLY clicks the toggle button to close
    #     parent.document.addEventListener('mousedown', (e) => {
    #         const toggleBtn = e.target.closest('[data-testid="stSidebarCollapseButton"]');
    #         if (toggleBtn) {
    #             const sidebar = parent.document.querySelector('[data-testid="stSidebar"]');
    #             if (sidebar) {
    #                 const isCurrentlyOpen = sidebar.getBoundingClientRect().width > 50;
    #                 // If sidebar is open and user clicks toggle, they want to close it
    #                 if (isCurrentlyOpen) {
    #                     allowClose = true;
    #                     setTimeout(() => { allowClose = false; }, 500);
    #                 }
    #             }
    #         }
    #     }, true);
        
    #     // AGGRESSIVE: Monitor every 50ms and force reopen unless user explicitly closed
    #     setInterval(() => {
    #         if (allowClose) return;
            
    #         const sidebar = parent.document.querySelector('[data-testid="stSidebar"]');
    #         const toggleBtn = parent.document.querySelector('header [data-testid="stSidebarCollapseButton"]');
            
    #         if (sidebar && toggleBtn) {
    #             const isOpen = sidebar.getBoundingClientRect().width > 50;
    #             if (!isOpen) {
    #                 toggleBtn.click(); // Force reopen
    #             }
    #         }
    #     }, 50); // Check every 50ms for instant response
    # })();
    # </script>
    # """, unsafe_allow_html=True)


# --- FRAGMENTS ---
def sidebar_paint_fragment():
    """Isolates the color picker to prevent full app reruns on color change."""
    st.subheader("≡ƒûî∩╕Å Paint Mode")
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


def render_zoom_controls():
    """Render zoom and pan controls below the image."""
    z_col2, z_col3, z_col4 = st.columns([1, 2, 1])
    
    def update_zoom(delta):
        st.session_state["zoom_level"] = max(1.0, min(4.0, st.session_state["zoom_level"] + delta))
        st.session_state["render_id"] += 1
        st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
    
    with z_col2:
        if st.button("Γ₧û", help="Zoom Out", use_container_width=True):
            update_zoom(-0.2)
            st.rerun()
            
    with z_col3:
        st.markdown(
            f"""
            <div style='text-align: center; font-weight: bold; background-color: #f0f2f6; color: #31333F; padding: 6px 10px; border-radius: 4px; border: 1px solid #dcdcdc;'>
                {int(st.session_state['zoom_level'] * 100)}%
            </div>
            """, 
            unsafe_allow_html=True
        )
            
    with z_col4:
        if st.button("Γ₧ò", help="Zoom In", use_container_width=True):
            update_zoom(0.2)
            st.rerun()

    if st.session_state["zoom_level"] > 1.0 or st.session_state["pan_x"] != 0.5 or st.session_state["pan_y"] != 0.5:
        st.markdown("<div style='height: 5px'></div>", unsafe_allow_html=True)
        if st.button("≡ƒÄ» Reset View", use_container_width=True):
            st.session_state["zoom_level"] = 1.0
            st.session_state["pan_x"] = 0.5
            st.session_state["pan_y"] = 0.5
            st.session_state["render_id"] += 1
            st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
            st.rerun()

def overlay_pan_controls(image):
    """Draws semi-transparent pan arrows on the image edges."""
    h, w, c = image.shape
    overlay = image.copy()
    color = (255, 255, 255)
    thickness = 2
    margin = 40
    center_x, center_y = w // 2, h // 2
    cv2.arrowedLine(overlay, (center_x, margin), (center_x, 10), color, thickness, tipLength=0.5)
    cv2.arrowedLine(overlay, (center_x, h - margin), (center_x, h - 10), color, thickness, tipLength=0.5)
    cv2.arrowedLine(overlay, (margin, center_y), (10, center_y), color, thickness, tipLength=0.5)
    cv2.arrowedLine(overlay, (w - margin, center_y), (w - 10, center_y), color, thickness, tipLength=0.5)
    alpha = 0.6
    cv2.addWeighted(overlay, alpha, image, 1 - alpha, 0, image)
    return image

@st.fragment
def render_editor_fragment(display_width):
    """Truly isolates the canvas, composition, and selection bar."""
    # --- Debug banners removed ---
    h, w, _ = st.session_state["image"].shape
    start_x, start_y, view_w, view_h = get_crop_params(
        w, h, 
        st.session_state["zoom_level"], 
        st.session_state["pan_x"], 
        st.session_state["pan_y"]
    )
    scale_factor = display_width / view_w

    sam = get_sam_engine(CHECKPOINT_PATH, MODEL_TYPE)
    if not sam:
        st.error("AI Engine lost inside fragment.")
        return

    original_img = st.session_state["image"]
    painted_img = composite_image(original_img, st.session_state["masks"])
    show_comp = st.session_state.get("show_comparison", False)
    
    display_img = original_img if show_comp else painted_img
    cropped_view = display_img[start_y:start_y+view_h, start_x:start_x+view_w]
    new_h = int(view_h * (display_width / view_w))
    final_display_image = cv2.resize(cropped_view, (display_width, new_h), interpolation=cv2.INTER_LINEAR)
    
    if st.session_state.get("zoom_level", 1.0) > 1.0:
        final_display_image = overlay_pan_controls(final_display_image)

    display_height = final_display_image.shape[0]
    
    if show_comp:
        st.markdown("### ≡ƒæü∩╕Å Comparison: Before vs After")
        c1, c2 = st.columns(2)
        with c1: st.image(original_img, caption="Original / Before", use_container_width=True)
        with c2: st.image(painted_img, caption="Painted / After", use_container_width=True)
        st.divider()
    
    tool_mode = st.session_state.get("selection_tool", "Γ£¿ AI Object (Drag Box)")
    if "AI Click" in tool_mode: drawing_mode = "point"
    elif "AI Object" in tool_mode:
        drawing_mode = "rect" if st.session_state.get("ai_drag_sub_tool") == "≡ƒåò Draw New" else "transform"

    if st.session_state.get("pending_selection") is not None:
        st.markdown('<div style="margin-top: 10px; margin-bottom: 10px;"></div>', unsafe_allow_html=True)
        ac_col1, ac_col2, ac_col3 = st.columns([1.2, 0.8, 1.0], gap="small")
        with ac_col1: st.button("Γ£¿ APPLY PAINT", use_container_width=True, key="frag_apply", on_click=cb_apply_pending, type="primary")
        with ac_col2:
            pc = st.session_state.get("picked_color", "#8FBC8F")
            html_content = f'<div style="text-align:center; background:#FFF; padding:6px 5px; border-radius:30px; border:1px solid #E5E7EB; display:flex; align-items:center; justify-content:center; gap:4px; box-shadow:0 1px 2px rgba(0,0,0,0.05); height: 38px;"><div style="width:12px; height:12px; background-color:{pc}; border-radius:50%; border:1px solid #E5E7EB;"></div><span style="color:#1F2937; font-weight:700; font-size:0.7rem; white-space:nowrap;">{pc}</span></div>'
            st.markdown(html_content, unsafe_allow_html=True)
        with ac_col3: st.button("≡ƒùæ∩╕Å CANCEL", use_container_width=True, key="frag_cancel", on_click=cb_cancel_pending)

    with st.container():
        # --- ≡ƒöì INTERACTION MONITOR PLACEHOLDER ---
        # monitor_placeholder removed
        
        # GHOST MARKER: Used as a CSS anchor to hide the following button container
        st.markdown('<div class="sync-ghost-marker" style="display:none;"></div>', unsafe_allow_html=True)
        st.button("", key="mobile_sync_btn_ghost")
        
        # --- ≡ƒô▓ MOBILE COORDINATE FALLBACK (via URL params) ---
        query_params = st.query_params
        mobile_tap = query_params.get("tap", "")
        
        if mobile_tap and mobile_tap.strip() != "":
            # Clear the param immediately to prevent re-processing
            st.query_params.clear()
            
            try:
                parts = mobile_tap.split(",")
                if len(parts) >= 2:
                    x, y = int(parts[0].strip()), int(parts[1].strip())
                    
                    if "AI Click" in tool_mode:
                        real_x = int(x / scale_factor) + start_x
                        real_y = int(y / scale_factor) + start_y
                        
                        click_key = f"{real_x}_{real_y}_{st.session_state['picked_color']}"
                        if click_key != st.session_state.get("last_click_global"):
                            st.session_state["last_click_global"] = click_key
                            with st.spinner("Γ£¿ Analyzing Object..."):
                                if not getattr(sam, "is_image_set", False):
                                    sam.set_image(st.session_state["image"])
                                mask = sam.generate_mask(point_coords=[real_x, real_y], level=st.session_state.get("mask_level", 0))
                                if mask is not None:
                                    st.session_state["pending_selection"] = {'mask': mask, 'point': (real_x, real_y)}
                                    cb_apply_pending()
                                    
                                    st.session_state["render_id"] += 1
                                    st.session_state["canvas_id"] += 1
                                    st.rerun(scope="fragment")
            except Exception as e:
                pass
        
        initial_drawing = {"version": "4.4.0", "objects": []}
        for box in st.session_state.get("pending_boxes", []):
            p_left = (box[0] - start_x) * scale_factor
            p_top = (box[1] - start_y) * scale_factor
            p_width = (box[2] - box[0]) * scale_factor
            p_height = (box[3] - box[1]) * scale_factor
            initial_drawing["objects"].append({
                "type": "rect", "left": p_left, "top": p_top, "width": p_width, "height": p_height,
                "fill": "rgba(255, 165, 0, 0.3)", "stroke": "orange", "strokeWidth": 2
            })
        
        canvas_result = st_canvas(
            fill_color="rgba(255, 165, 0, 0.3)", stroke_width=3, stroke_color="#FF4B4B",
            background_image=final_display_image, update_streamlit=True, height=display_height, width=display_width,
            drawing_mode=drawing_mode, initial_drawing=initial_drawing, point_display_radius=20 if drawing_mode == "point" else 0,
            key=f"canvas_{st.session_state.get('canvas_id', 0)}", display_toolbar=False
        )

        # Interaction Monitor removed
        
        html_code = f"""
<script>
(function() {{
    const CANVAS_WIDTH = {display_width};
    const CANVAS_HEIGHT = {display_height};
    let lastWidth = 0;
    
    const getActiveIframe = () => {{
        const all = parent.document.querySelectorAll('iframe[title="streamlit_drawable_canvas.st_canvas"]');
        for (let i = all.length - 1; i >= 0; i--) {{
            const f = all[i];
            if (!f.closest('[data-stale="true"]')) return f;
        }}
        return all[all.length - 1]; 
    }};

    function applyResponsiveScale() {{
        try {{
            const iframe = getActiveIframe();
            if (!iframe) return;
            const wrapper = iframe.parentElement;
            if (!wrapper) return;
            
            // Go up to find the element container which has the true width
            const container = wrapper.closest('.element-container') || wrapper.parentElement;
            if (!container) return;
            
            let containerWidth = container.getBoundingClientRect().width;
            
            // On mobile, force full available width regardless of container quirks
            if (parent.window.innerWidth < 1024) {{
                containerWidth = parent.window.innerWidth - 24; 
            }}
            
            if (containerWidth <= 0) return;
            
            // Remove the throttle for mobile to ensure quick snapping
            if (parent.window.innerWidth < 1024) {{
                 // Always proceed
            }} else if (Math.abs(containerWidth - lastWidth) < 1 && lastWidth > 0) {{
                 return;
            }}
            lastWidth = containerWidth;
            
            const scale = Math.min(1.0, (containerWidth - 2) / CANVAS_WIDTH);
            
            wrapper.style.width = (CANVAS_WIDTH * scale) + "px";
            wrapper.style.height = (CANVAS_HEIGHT * scale) + "px";
            wrapper.style.overflow = "hidden";
            wrapper.style.touchAction = "none";
            wrapper.style.position = "relative";
            wrapper.style.margin = "0 auto";
            
            iframe.style.width = CANVAS_WIDTH + "px";
            iframe.style.height = CANVAS_HEIGHT + "px";
            iframe.style.transformOrigin = "0 0";
            iframe.style.transform = "scale(" + scale + ")";
            iframe.style.border = "none";
            iframe.style.display = "block";
            iframe.style.position = "absolute";
            iframe.style.top = "0";
            iframe.style.left = "0";
            iframe.style.zIndex = "100";
            iframe.style.pointerEvents = "auto";
            iframe.style.touchAction = "none";

            // Definitive Ghost Hider: Find the ghost marker and hide the button container
            try {{
                const marker = parent.document.querySelector('.sync-ghost-marker');
                if (marker) {{
                    const container = marker.closest('.element-container') || marker.parentElement;
                    if (container) {{
                        const nextBtn = container.nextElementSibling;
                        if (nextBtn && nextBtn.querySelector('button')) {{
                            nextBtn.style.display = 'none';
                            nextBtn.style.position = 'fixed';
                            nextBtn.style.top = '-9999px';
                        }}
                    }}
                }}
            }} catch(e) {{}}
        }} catch (e) {{}}
    }}

    try {{
        const iframe = getActiveIframe();
        if (iframe && iframe.parentElement && iframe.parentElement.parentElement) {{
            const observer = new ResizeObserver(() => applyResponsiveScale());
            observer.observe(iframe.parentElement.parentElement);
        }}
    }} catch(e) {{}}

    function setupTouchPrecision() {{
        try {{
            const iframe = getActiveIframe();
            if (!iframe || !iframe.contentDocument) return;
            const canvasElements = iframe.contentDocument.querySelectorAll('canvas');
            canvasElements.forEach(canvas => {{
                if (canvas.dataset.hasProxy === "true") return; 

                canvas.style.touchAction = "none";
                canvas.style.userSelect = "none";
                canvas.style.webkitUserSelect = "none";
                canvas.style.webkitTapHighlightColor = "transparent";
                
                const sendEvent = (type, touch) => {{
                    const rect = canvas.getBoundingClientRect();
                    const scaleX = rect.width > 0 ? (CANVAS_WIDTH / rect.width) : 1;
                    const scaleY = rect.height > 0 ? (CANVAS_HEIGHT / rect.height) : 1;

                    const visualX = touch.clientX - rect.left;
                    const visualY = touch.clientY - rect.top;
                    
                    const offX = visualX * scaleX;
                    const offY = visualY * scaleY;
                    
                    canvas.dispatchEvent(new PointerEvent(type, {{
                        bubbles: true, cancelable: true, isPrimary: true, pointerId: 1, pointerType: 'touch',
                        clientX: rect.left + offX, 
                        clientY: rect.top + offY,
                        offsetX: offX, offsetY: offY,
                        button: 0, buttons: 1, view: window
                    }}));
                }};

                canvas.addEventListener('touchstart', (e) => {{
                    if (e.touches.length === 1) {{
                        e.preventDefault();
                        
                        const rect = canvas.getBoundingClientRect();
                        const scaleX = rect.width > 0 ? (CANVAS_WIDTH / rect.width) : 1;
                        const scaleY = rect.height > 0 ? (CANVAS_HEIGHT / rect.height) : 1;
                        
                        const visualX = e.touches[0].clientX - rect.left;
                        const visualY = e.touches[0].clientY - rect.top;
                        
                        const x = Math.round(visualX * scaleX);
                        const y = Math.round(visualY * scaleY);

                        // Update URL with coordinates + timestamp to force reactivity
                        const currentUrl = new URL(parent.location.href);
                        currentUrl.searchParams.set('tap', x + ',' + y + ',' + Date.now());
                        parent.history.pushState({{}}, '', currentUrl.toString());

                        // Visual feedback and trigger rerun
                        iframe.style.boxShadow = "inset 0 0 30px #00ff00";
                        setTimeout(() => iframe.style.boxShadow = "none", 300);

                        // Proxy standard pointer event for component internal state
                        sendEvent('pointerdown', e.touches[0]);

                        // Click the hidden trigger reliably
                        setTimeout(() => {{
                             const allBtns = Array.from(parent.document.querySelectorAll('div[data-testid="stButton"] button'));
                             const ghostBtn = allBtns.find(b => b.parentElement.parentElement.innerHTML.includes("mobile_sync_btn_ghost"));
                             if (ghostBtn) ghostBtn.click();
                        }}, 50);
                    }}
                }}, {{passive: false}});

                canvas.addEventListener('touchmove', (e) => {{
                    if (e.touches.length === 1) {{
                        e.preventDefault();
                        sendEvent('pointermove', e.touches[0]);
                    }}
                }}, {{passive: false}});

                canvas.addEventListener('touchend', (e) => {{
                    if (e.changedTouches.length === 1) {{
                        sendEvent('pointerup', e.changedTouches[0]);
                        sendEvent('click', e.changedTouches[0]);
                    }}
                }}, {{passive: false}});
                
                canvas.dataset.hasProxy = "true";
            }});
        }} catch(e) {{}}
    }}

    applyResponsiveScale();
    setupTouchPrecision();
    window.addEventListener("resize", applyResponsiveScale);
    // Faster interval for mobile responsiveness
    setInterval(() => {{
        applyResponsiveScale();
        setupTouchPrecision();
    }}, 500); 
}})();
</script>
"""
        st.components.v1.html(html_code, height=0)

        if st.session_state["masks"]:
            st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
            btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
            with btn_col1:
                if st.button("ΓÅ¬ Undo Last", use_container_width=True, key="main_undo_btn", type="primary"):
                    cb_undo()
                    st.rerun(scope="fragment")
            with btn_col2:
                 if st.button("≡ƒùæ∩╕Å Clear All", use_container_width=True, key="main_clear_btn"):
                    cb_clear_all()
                    st.rerun() # Full rerun to prevent fragment state desync (white screen)

        if canvas_result.json_data:
            objects = canvas_result.json_data.get("objects", [])
            if objects:
                last_type = objects[-1].get("type", "unknown")
                if "AI Click" in tool_mode:
                    try:
                        for obj in objects:
                            if obj["type"] in ["circle", "path"]:
                                rel_x, rel_y = obj["left"], obj["top"]
                                real_x = int(rel_x / scale_factor) + start_x
                                real_y = int(rel_y / scale_factor) + start_y
                                click_key = f"{real_x}_{real_y}_{st.session_state['picked_color']}"
                                if click_key != st.session_state.get("last_click_global"):
                                    st.session_state["last_click_global"] = click_key
                                    with st.spinner("Γ£¿ Analyzing Object..."):
                                        if not getattr(sam, "is_image_set", False):
                                            sam.set_image(st.session_state["image"])
                                        mask = sam.generate_mask(point_coords=[real_x, real_y], level=st.session_state.get("mask_level", 0))
                                        if mask is not None:
                                            # --- INSTANT APPLY LOGIC ---
                                            st.session_state["pending_selection"] = {'mask': mask, 'point': (real_x, real_y)}
                                            
                                            # --- INSTANT APPLY (Always on for AI Click) ---
                                            cb_apply_pending()
                                            
                                            st.session_state["render_id"] += 1
                                            st.rerun(scope="fragment") 
                                        else: pass
                    except Exception as e:
                        st.error(f"Canvas Processing Error: {e}")

                elif "AI Object" in tool_mode:
                    current_boxes = []
                    combined_mask = None
                    for obj in objects:
                        if obj["type"] in ["rect", "transform"]:
                            left, top = obj["left"], obj["top"]
                            width, height = obj["width"] * obj.get("scaleX", 1.0), obj["height"] * obj.get("scaleY", 1.0)
                            bx1, by1 = int(left / scale_factor) + start_x, int(top / scale_factor) + start_y
                            bx2, by2 = int((left + width) / scale_factor) + start_x, int((top + height) / scale_factor) + start_y
                            current_boxes.append([bx1, by1, bx2, by2])
                    
                    if current_boxes != st.session_state.get("pending_boxes"):
                        st.session_state["pending_boxes"] = current_boxes
                        for box in current_boxes:
                            try:
                                sam.set_image(st.session_state["image"])
                                mask = sam.generate_mask(box_coords=box, level=st.session_state.get("mask_level", 0))
                                if mask is not None:
                                    combined_mask = mask.copy() if combined_mask is None else combined_mask | mask
                            except: continue
                        if combined_mask is not None:
                            img_h, img_w = st.session_state["image"].shape[:2]
                            if combined_mask.shape != (img_h, img_w):
                                combined_mask = cv2.resize(combined_mask.astype(np.uint8), (img_w, img_h), interpolation=cv2.INTER_NEAREST) > 0
                            ref_p = (int((current_boxes[0][0]+current_boxes[0][2])/2), int((current_boxes[0][1]+current_boxes[0][3])/2))
                            st.session_state["pending_selection"] = {'mask': combined_mask, 'point': ref_p}
                            st.session_state["render_id"] += 1
                            st.rerun(scope="fragment") 

@st.fragment
def sidebar_toggle_fragment():
    """Isolates the sidebar toggle buttons and custom CSS to prevent full reruns."""
    # --- ≡ƒ¢í∩╕Å GHOST ARROW (Open) ---
    if not st.session_state.get("sidebar_p_open"):
        st.markdown('<div class="m-open-container">', unsafe_allow_html=True)
        if st.button("", icon=":material/keyboard_double_arrow_right:", key="m_open_btn"):
            st.session_state.sidebar_p_open = True
            st.rerun(scope="app") 
        st.markdown('</div>', unsafe_allow_html=True)

def render_sidebar(sam, device_str):
    # --- ≡ƒ¢í∩╕Å GHOST ARROW (Open) ---
    sidebar_toggle_fragment()

    with st.sidebar:
        # --- ≡ƒ¢í∩╕Å GHOST ARROW (Close) ---
        if st.session_state.get("sidebar_p_open"):
            st.markdown('<div class="m-close-inner">', unsafe_allow_html=True)
            if st.button("", icon=":material/keyboard_double_arrow_left:", help="Close Menu", key="m_close_btn"):
                st.session_state.sidebar_p_open = False
                st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("<h3 style='margin:0 0 15px 35px; padding:0; color:#31333F;'>Visualizer Studio</h3>", unsafe_allow_html=True)
        
        if st.session_state.get("image") is not None:
            if st.button("≡ƒöä Reset Project / Clear All", use_container_width=True):
                st.session_state["image"] = None
                st.session_state["image_path"] = None
                st.session_state["masks"] = []
                for k in list(st.session_state.keys()):
                    if any(k.startswith(p) for p in ["bg_url_cache_", "base_l_", "comp_cache_"]):
                        del st.session_state[k]
                st.session_state["render_cache"] = None
                st.session_state["composited_cache"] = None
                st.cache_data.clear()
                st.session_state["uploader_id"] += 1 
                st.rerun()
            st.divider()

        uploader_key = f"uploader_{st.session_state.get('uploader_id', 0)}"
        uploaded_file = st.file_uploader("Start Project", type=["jpg", "png", "jpeg"], label_visibility="collapsed", key=uploader_key)
        
        if uploaded_file is not None:
            file_key = getattr(uploaded_file, "file_id", f"{uploaded_file.name}_{uploaded_file.size}")
            if st.session_state.get("image_path") != file_key:
                st.toast(f"≡ƒô╕ Loading New Image: {uploaded_file.name}", icon="≡ƒöä")
                uploaded_file.seek(0)
                file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
                image = cv2.cvtColor(cv2.imdecode(file_bytes, 1), cv2.COLOR_BGR2RGB)
                st.session_state["image_original"] = image.copy()
                max_dim = 1100
                h, w = image.shape[:2]
                if max(h, w) > max_dim:
                    scale = max_dim / max(h, w)
                    image = cv2.resize(image, (int(w*scale), int(h*scale)), interpolation=cv2.INTER_AREA)
                st.session_state["image"] = image
                st.session_state["image_path"] = file_key
                st.session_state["masks"] = []
                st.session_state["zoom_level"] = 1.0
                st.session_state["pan_x"] = 0.5
                st.session_state["pan_y"] = 0.5
                st.session_state["render_id"] = 0
                st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
                for k in list(st.session_state.keys()):
                    if any(k.startswith(p) for p in ["bg_url_cache_", "base_l_", "comp_cache_"]):
                        del st.session_state[k]
                st.session_state["render_cache"] = None
                st.session_state["composited_cache"] = None
                st.cache_data.clear()
                sam.is_image_set = False
                st.rerun() 

        if st.session_state.get("image") is None:
             st.markdown("<div style='background:#f3f4f6; padding:15px; border-radius:10px; border:1px dashed #d1d5db; margin:10px 0;'><p style='margin:0; font-size:0.85rem; color:#4b5563; line-height:1.4;'><b>Ready to paint?</b><br>Upload a photo of your wall or room to begin.</p></div>", unsafe_allow_html=True)
             st.caption("Supported formats: JPG, PNG, JPEG")
             return

        if st.session_state.get("image") is not None:
            if st.session_state["masks"]:
                if st.button("≡ƒÆÄ Prepare High-Res Download", use_container_width=True):
                    st.toast("Processing 4K Export...", icon="≡ƒÆÄ")
                    try:
                        original_img = st.session_state["image_original"]
                        oh, ow = original_img.shape[:2]
                        high_res_masks = []
                        for m_data in st.session_state["masks"]:
                            hr_m = m_data.copy()
                            mask_uint8 = (m_data['mask'] * 255).astype(np.uint8)
                            hr_mask_uint8 = cv2.resize(mask_uint8, (ow, oh), interpolation=cv2.INTER_LINEAR)
                            hr_m['mask'] = hr_mask_uint8 > 127
                            hr_m['mask_soft'] = None 
                            high_res_masks.append(hr_m)
                        from core.colorizer import ColorTransferEngine
                        dl_comp = ColorTransferEngine.composite_multiple_layers(original_img, high_res_masks)
                        dl_pil = Image.fromarray(dl_comp)
                        dl_buf = io.BytesIO()
                        dl_pil.save(dl_buf, format="PNG")
                        st.session_state["last_export"] = dl_buf.getvalue()
                        st.success("Γ£à Download Ready!")
                    except Exception as e: st.error(f"Export failed: {e}")

                if st.session_state.get("last_export"):
                    st.download_button(label="≡ƒôÑ Save Final Image", data=st.session_state["last_export"], file_name="pro_visualizer_design.png", mime="image/png", use_container_width=True)
            
            st.divider()
            st.subheader("≡ƒ¢á∩╕Å Selection Tool")
            selection_tool = st.radio("Method", ["≡ƒæå AI Click Object (Point)", "Γ£¿ AI Object (Drag Box)"], index=0 if st.session_state.get("selection_tool") == "≡ƒæå AI Click Object (Point)" else 1, horizontal=True, key="sidebar_selection_tool_radio")
            st.session_state["selection_tool"] = selection_tool
            if "AI Object" in selection_tool:
                st.session_state["ai_drag_sub_tool"] = st.radio("Action", ["≡ƒåò Draw New", "≡ƒû▒∩╕Å Move / Resize"], index=0 if st.session_state.get("ai_drag_sub_tool") == "≡ƒåò Draw New" else 1, horizontal=True, key="sidebar_ai_drag_sub_tool_radio")
            
            st.divider()
            st.subheader("≡ƒæü∩╕Å View Settings")
            st.toggle("Compare Before/After", key="show_comparison")

            if "AI Click" in st.session_state.get("selection_tool", ""):
                with st.expander("ΓÜÖ∩╕Å Advanced Precision (Optional)", expanded=True):
                     prec_options = ["Walls (Default)", "Small Objects", "Floors/Whole"]
                     prec_mode = st.radio("Segmentation Mode", prec_options, index=max(0, min(int(st.session_state.get("mask_level", 0) or 0), len(prec_options)-1)), key="sidebar_prec_mode_radio")
                     target_level = prec_options.index(prec_mode)
                     if target_level != st.session_state.get("mask_level", 0):
                         st.session_state["mask_level"] = target_level
                         st.rerun()

            render_zoom_controls()
            st.divider()
            sidebar_paint_fragment()
            st.divider()
            if st.session_state["masks"]:
                col_u1, col_u2 = st.columns(2)
                with col_u1: st.button("ΓÅ¬ Undo", use_container_width=True, on_click=cb_undo, key="sidebar_undo")
                with col_u2: st.button("≡ƒùæ∩╕Å Clear All", use_container_width=True, on_click=cb_clear_all, key="sidebar_clear")
                st.write("---")
                for i in range(len(st.session_state["masks"]) - 1, -1, -1):
                    mask_data = st.session_state["masks"][i]
                    with st.container(border=True):
                        try: r1, r2, r3, r4 = st.columns([0.45, 0.15, 0.25, 0.15], vertical_alignment="center")
                        except: r1, r2, r3, r4 = st.columns([0.45, 0.15, 0.25, 0.15])
                        cur_c = mask_data.get('color', '#FFFFFF')
                        with r1: st.markdown(f"**Layer {i+1}**")
                        with r2: st.markdown(f"<div style='width:24px;height:24px;background:{cur_c};border-radius:4px;border:1px solid #ddd;'></div>", unsafe_allow_html=True)
                        with r3: st.markdown(f"`{cur_c}`")
                        with r4: st.button("≡ƒùæ∩╕Å", key=f"sidebar_del_{i}", on_click=cb_delete_layer, args=(i,))
            else: st.caption("No active layers.")
