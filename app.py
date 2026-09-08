import sys
import types
from io import BytesIO
import base64
import streamlit as st
import os
import torch
import warnings
import logging

# --- SILENCE DEPRECATION WARNINGS ---
warnings.filterwarnings("ignore", category=FutureWarning, module="timm")
warnings.filterwarnings("ignore", category=UserWarning, module="mobile_sam")

import numpy as np
import cv2
from scipy import sparse

# 🎯 CRITICAL: Must be the VERY FIRST Streamlit command
st.set_page_config(
    page_title="Paint Visualizer",
    page_icon="🎨",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- UTILITIES IMPORT ---
from paint_utils.encoding import image_to_url_patch
from paint_utils.sam_loader import get_sam_engine, ensure_model_exists, CHECKPOINT_PATH, MODEL_TYPE
from paint_utils.state_manager import initialize_session_state, cb_apply_pending
from paint_utils.ui_components import setup_styles, render_sidebar, render_visualizer_engine_v11, TOOL_MAPPING
from paint_utils.image_processing import get_crop_params, magic_wand_selection
from paint_core.segmentation import SegmentationEngine, sam_model_registry
from app_config.constants import PerformanceConfig

# --- 1️⃣ SESSION INITIALIZATION (VERY TOP)
initialize_session_state()

# --- WARNING SHIELD: Titanium Silence v4 ---
st.components.v1.html("""
    <!-- 📱 MOBILE OPTIMIZATION -->
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes">
    <script>
        (function() {
            const silence = (w) => {
                try {
                    if (!w || !w.console || w.console.__isMuted) return;
                    ['warn', 'error', 'log'].forEach(m => {
                        const original = w.console[m];
                        if (!original) return;
                        w.console[m] = function(...args) {
                            try {
                                const msg = String(args[0] || "");
                                if (/Invalid color|theme\\.sidebar|widgetBackground|skeletonBackground|Unrecognized feature|ambient-light|battery|wake-lock|sandbox|document-domain|oversized-images|vr|fragment rerun/i.test(msg)) return;
                            } catch(e) {}
                            original.apply(this, args);
                        };
                    });
                    w.console.__isMuted = true;
                } catch(e) {}
            };
            const run = () => {
                silence(window);
                try { if (window.parent && window.parent !== window) silence(window.parent); } catch(e) {}
            };
            run();
            setInterval(run, 500);
        })();
    </script>
""", height=0)

def main():
    setup_styles()
    
    # Reset loop guard for the new app cycle
    st.session_state["loop_guarded"] = False
    ensure_model_exists()
    
    # Identify device for engine optimization
    device_str = "cpu"
    if torch.cuda.is_available(): device_str = "cuda"
    elif torch.backends.mps.is_available(): device_str = "mps"

    # Load SAM early
    sam = get_sam_engine(CHECKPOINT_PATH, MODEL_TYPE)

    # --- 2️⃣ CAPTURE BOX PARAM IMMEDIATELY (BEFORE SIDEBAR) ---
    q_params = st.query_params
    box_param = q_params.get("box", None)

    # --- 📐 RESOLVE DISPLAY WIDTH (Dynamic, Cloud-safe) ---
    # JS reports actual container width via ?container_w= param or session_state.
    # This prevents hardcoded 800px from overflowing narrower Cloud containers.
    import time
    container_w_param = q_params.get("container_w", None)
    if container_w_param:
        try:
            reported_w = int(float(container_w_param))
            if 400 <= reported_w <= 2000:
                st.session_state["canvas_container_width"] = reported_w
                if "container_w" in st.query_params:
                    del st.query_params["container_w"]
        except Exception:
            pass
    # Always cap at 800 (the intrinsic canvas resolution) and floor at 400
    display_width = min(800, max(400, st.session_state.get("canvas_container_width", 800)))

    print(f"DEBUG: [{time.strftime('%H:%M:%S')}] ALL PARAMS AT START: {dict(st.query_params)}")
    print(f"DEBUG: display_width resolved to: {display_width}")
    if st.query_params:
        print(f"DEBUG: Active Param Keys: {list(st.query_params.keys())}")
    
    # --- 3️⃣ PROCESS BOX SEGMENTATION (ASYNC) ---
    if box_param and st.session_state.get("image") is not None:
        print(f"DEBUG: BOX PARAM DETECTED -> {box_param}")
        
        # Check if we are already processing this
        from paint_utils.async_processor import submit_sam_task, check_async_task
        async_status = check_async_task()
        
        if async_status == "running":
            with st.spinner("🧠 AI is thinking..."):
                import time
                time.sleep(0.1)
                from paint_utils.state_manager import preserve_sidebar_state
                preserve_sidebar_state()
                st.rerun()
        
        elif isinstance(async_status, dict) and async_status.get("status") == "success":
            # Task Completed!
            accumulated_mask = async_status.get("mask")
            print(f"DEBUG: Async Task Success! Mask Sum: {np.sum(accumulated_mask) if accumulated_mask is not None else 'None'}")
            
            if accumulated_mask is not None:
                operation = st.session_state.get("selection_op", "Add")
                
                if operation == "Subtract":
                     # ERASE Mode for AI Object (Box)
                     cleaned_any = False
                     if st.session_state["masks"]:
                         for layer in st.session_state["masks"]:
                             if layer.get("visible", True):
                                 target_mask = layer['mask']
                                 if sparse.issparse(target_mask):
                                     target_mask = target_mask.toarray()

                                 mask_to_subtract = accumulated_mask
                                 if target_mask.shape != mask_to_subtract.shape:
                                     mask_to_subtract = cv2.resize(mask_to_subtract.astype(np.uint8), (target_mask.shape[1], target_mask.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
                                 
                                 before_count = np.sum(target_mask)
                                 result_mask = (target_mask > 0) & ~mask_to_subtract
                                 
                                 layer['mask'] = result_mask
                                 if np.sum(layer['mask']) < before_count:
                                     cleaned_any = True
                         
                     if cleaned_any:
                         st.session_state["render_id"] += 1
                         st.toast("✅ Paint Erased!", icon="🧹")
                     else:
                         st.toast("⚠️ Nothing to erase!", icon="✨")

                else:
                    # ADD Mode
                    print("DEBUG: PAINT APPLIED (Adding to State)")
                    new_mask_entry = {
                        'mask': accumulated_mask,
                        'color': st.session_state.get("picked_color", "#8FBC8F"),
                        'visible': True,
                        'name': f"Layer {len(st.session_state['masks'])+1}",
                        'refinement': st.session_state.get("selection_refinement", 0),
                        'softness': st.session_state.get("selection_softness", 0),
                        'brightness': 0.0, 'contrast': 1.0, 'saturation': 1.0, 'hue': 0.0, 
                        'opacity': st.session_state.get("selection_highlight_opacity", 1.0), 
                        'finish': st.session_state.get("selection_finish", 'Standard')
                    }
                    st.session_state["masks"].append(new_mask_entry)
                    st.session_state["render_id"] += 1

            else:
                 st.toast("⚠️ No object detected.", icon="🤷‍♂️")
            
            # Clear Param
            if "box" in st.query_params: 
                del st.query_params["box"]

        elif isinstance(async_status, dict) and async_status.get("status") == "error":
             st.error(f"AI Error: {async_status.get('message')}")
             if "box" in st.query_params: 
                 del st.query_params["box"]
             from paint_utils.state_manager import preserve_sidebar_state
             preserve_sidebar_state()
             st.rerun()
             
        else:
            # NOT STARTED -> Prepare and Submit
            try:
                # Parse Timestamp (Suffix)
                if "," in box_param:
                    parts = box_param.split(",")
                    if len(parts[-1]) > 9 and parts[-1].isdigit(): 
                         boxes_str = box_param[:-(len(parts[-1])+1)]
                    else: 
                         boxes_str = box_param
                else:
                    boxes_str = box_param
                
                # Replicate View/Scale Logic to map Canvas -> Image
                img = st.session_state["image"]
                h, w = img.shape[:2]
                # Use dynamic display_width (resolved above) — NOT hardcoded 800
                _dw = display_width
                
                zoom = st.session_state.get("zoom_level", 1.0)
                pan_x = st.session_state.get("pan_x", 0.5)
                pan_y = st.session_state.get("pan_y", 0.5)
                
                start_x, start_y, view_w, view_h = get_crop_params(w, h, zoom, pan_x, pan_y)
                scale_factor = _dw / view_w
                
                boxes_list = []
                for b_token in boxes_str.split("|"):
                    if not b_token.strip(): continue
                    coords = list(map(float, b_token.split(",")))
                    if len(coords) == 4:
                        cx1, cy1, cx2, cy2 = coords
                        x1 = int(cx1 / scale_factor) + start_x
                        y1 = int(cy1 / scale_factor) + start_y
                        x2 = int(cx2 / scale_factor) + start_x
                        y2 = int(cy2 / scale_factor) + start_y
                        
                        final_box = [min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)]
                        boxes_list.append(final_box)
                
                if boxes_list:
                    # 🚀 FAST PATH: If embeddings are ready, run synchronously ( Instant Apply )
                    if getattr(sam, "is_image_set", False) and getattr(sam, "image_rgb", None) is not None:
                         print("DEBUG: Fast path for Box prediction")
                         current_tool = st.session_state.get("selection_tool", "")
                         is_wall_click_mode = "Wall Click" in current_tool
                         is_wall_mode = st.session_state.get("is_wall_only", False)
                         accumulated_mask = None
                         
                         for b in boxes_list:
                             m = sam.generate_mask(
                                 box_coords=b, 
                                 level=st.session_state.get("mask_level", 0), 
                                 is_wall_only=is_wall_mode,
                                 is_wall_click=is_wall_click_mode
                             )
                             if m is not None:
                                 accumulated = m if accumulated_mask is None else np.logical_or(accumulated_mask, m)
                                 accumulated_mask = accumulated
                         
                         if accumulated_mask is not None:
                              st.session_state["pending_selection"] = {'mask': accumulated_mask}
                              cb_apply_pending(increment_canvas=True)
                              st.session_state["render_id"] += 1
                              st.toast("✅ Paint Applied!", icon="🎨")
                         else:
                              st.toast("⚠️ No object detected.", icon="🤷‍♂️")
                         
                         if "box" in st.query_params: 
                              del st.query_params["box"]
                    else:
                        # FALLBACK -> Async Worker
                        submit_sam_task(
                            sam_engine=sam,
                            image=img,
                            prompt_type="multi_box",
                            prompt_data={
                                "boxes": boxes_list, 
                                "level": st.session_state.get("mask_level", 0),
                                "is_wall_only": True if "Wall Click" in st.session_state.get("selection_tool", "") else st.session_state.get("is_wall_only", False)
                            }
                        )
                        st.session_state["async_task_pending"] = True
            except Exception as e:
                print(f"DEBUG: Box Parse Error: {e}")
                if "box" in st.query_params: 
                    del st.query_params["box"]

    # --- 2c️⃣ CAPTURE & PROCESS TAP PARAM (AI / WAND) ---
    tap_param = q_params.get("tap", None)
    if tap_param and st.session_state.get("image") is not None:
        # Determine tool type for specific handling
        current_tool = st.session_state.get("selection_tool", "")
        is_wand = "Magic Wand" in current_tool
        
        if is_wand:
            print(f"DEBUG: Processing Magic Wand Tap -> {tap_param}")
            try:
                parts = tap_param.split(",")
                x, y = int(parts[0].strip()), int(parts[1].strip())
                img = st.session_state["image"]
                h, w = img.shape[:2]
                _dw = display_width  # Dynamic — resolved at top of main()
                zoom = st.session_state.get("zoom_level", 1.0)
                pan_x = st.session_state.get("pan_x", 0.5)
                pan_y = st.session_state.get("pan_y", 0.5)
                start_x, start_y, view_w, view_h = get_crop_params(w, h, zoom, pan_x, pan_y)
                scale_factor = _dw / view_w
                real_x = int(x / scale_factor) + start_x
                real_y = int(y / scale_factor) + start_y
                
                # Execute Wand (Instant OpenCV Op)
                mask = magic_wand_selection(img, (real_x, real_y), tolerance=st.session_state.get("wand_tolerance", 25))
                if mask is not None and np.any(mask):
                    st.session_state["pending_selection"] = {'mask': mask, 'point': (real_x, real_y)}
                    cb_apply_pending(increment_canvas=False, silent=True)
                    st.session_state["render_id"] += 1
                
                if "tap" in st.query_params: 
                    del st.query_params["tap"]
            except Exception as e:
                print(f"DEBUG: Wand Error: {e}")
                if "tap" in st.query_params: 
                    del st.query_params["tap"]
        
        # --- AI POINT HANDLER ---
        print(f"DEBUG: Processing Mobile Tap (AI) -> {tap_param}")
        
        # Check if we are already processing this
        from paint_utils.async_processor import submit_sam_task, check_async_task
        async_status = check_async_task()
        
        if async_status == "running":
            with st.status("👆 AI is analyzing object...", expanded=False):
                st.write("Detecting boundaries...")
                import time
                from paint_utils.state_manager import preserve_sidebar_state
                preserve_sidebar_state()
                st.rerun()

        elif isinstance(async_status, dict) and async_status.get("status") == "success":
             # Success!
             mask = async_status.get("mask")
             
             if mask is not None:
                # Need to reconstruct point coords for pending selection metadata
                # We can't easily get it from async_result unless we store it.
                # But 'tap_param' is still here. Retreive coords again just for metadata.
                # (Optimized: we could have returned it from async task but parsing is fast)
                parts = tap_param.split(",")
                # ... Skipping re-parsing for brevity, just use dummy or parse quickly
                # Re-parsing is cheap:
                x, y = int(parts[0].strip()), int(parts[1].strip())
                 # Scaling logic... to get real_x, real_y...
                 # Actually, let's just assume we want to apply it.
                
                # We need real coords for the 'point' metadata
                img = st.session_state["image"]
                h, w = img.shape[:2]
                _dw = display_width  # Dynamic — resolved at top of main()
                zoom = st.session_state.get("zoom_level", 1.0)
                pan_x = st.session_state.get("pan_x", 0.5)
                pan_y = st.session_state.get("pan_y", 0.5)
                start_x, start_y, view_w, view_h = get_crop_params(w, h, zoom, pan_x, pan_y)
                scale_factor = _dw / view_w
                real_x = int(x / scale_factor) + start_x
                real_y = int(y / scale_factor) + start_y

                st.session_state["pending_selection"] = {'mask': mask, 'point': (real_x, real_y)}
                st.session_state["selection_op"] = st.session_state.get("selection_op", "Add")
                cb_apply_pending(increment_canvas=False, silent=True)
                st.session_state["render_id"] += 1
                
             # Clear Param
             if "tap" in st.query_params: 
                 del st.query_params["tap"]
        
        elif isinstance(async_status, dict) and async_status.get("status") == "error":
             st.error(f"Tap Error: {async_status.get('message')}")
             if "tap" in st.query_params: 
                 del st.query_params["tap"]
             from paint_utils.state_manager import preserve_sidebar_state
             preserve_sidebar_state()
             st.rerun()

        else:
            # NOT STARTED
            try:
                parts = tap_param.split(",")
                if len(parts) >= 2:
                    x, y = int(parts[0].strip()), int(parts[1].strip())
                    img = st.session_state["image"]
                    h, w = img.shape[:2]
                    _dw = display_width  # Dynamic — resolved at top of main()
                    zoom = st.session_state.get("zoom_level", 1.0)
                    pan_x = st.session_state.get("pan_x", 0.5)
                    pan_y = st.session_state.get("pan_y", 0.5)
                    start_x, start_y, view_w, view_h = get_crop_params(w, h, zoom, pan_x, pan_y)
                    scale_factor = _dw / view_w
                    
                    real_x = int(x / scale_factor) + start_x
                    real_y = int(y / scale_factor) + start_y
                    
                    # 🚀 FAST PATH: If embeddings are ready, run synchronously
                    if getattr(sam, "is_image_set", False) and getattr(sam, "image_rgb", None) is not None:
                        print("DEBUG: Fast path for Tap prediction")
                        current_tool = st.session_state.get("selection_tool", "")
                        is_wall_click_mode = "Wall Click" in current_tool
                        is_wall_mode = st.session_state.get("is_wall_only", False)
                        
                        mask = sam.generate_mask(
                            point_coords=[real_x, real_y], 
                            level=st.session_state.get("mask_level", 0), 
                            is_wall_only=is_wall_mode,
                            is_wall_click=is_wall_click_mode
                        )
                        # We need to reuse the success logic above. 
                        # Ideally refactor, but for now we set a flag and rerun immediately?
                        # Or just perform the action here? 
                        
                        # Let's perform the action here to save a rerun!
                        if mask is not None:
                            st.session_state["pending_selection"] = {'mask': mask, 'point': (real_x, real_y)}
                            st.session_state["selection_op"] = st.session_state.get("selection_op", "Add")
                            # Instant apply for point clicks
                            cb_apply_pending(increment_canvas=False, silent=True)
                            st.session_state["render_id"] += 1
                        
                        if "tap" in st.query_params: 
                            del st.query_params["tap"]

                    else:
                        # FALLBACK -> Async Worker
                        submit_sam_task(
                            sam_engine=sam,
                            image=img,
                            prompt_type="point",
                            prompt_data={
                                "point_coords": [real_x, real_y], 
                                "level": st.session_state.get("mask_level", 0),
                                "is_wall_only": True if "Wall Click" in st.session_state.get("selection_tool", "") else st.session_state.get("is_wall_only", False)
                            }
                        )
            except Exception as e:
                print(f"DEBUG: Tap Setup Error: {e}")
                if "tap" in st.query_params: 
                    del st.query_params["tap"]

    # --- 2b️⃣ CAPTURE POLY PARAM IMMEDIATELY ---
    poly_param = q_params.get("poly_pts", None)

    # --- 3b️⃣ PROCESS POLYGON SEGMENTATION IMMEDIATELY ---
    if poly_param and st.session_state.get("image") is not None:
        print(f"DEBUG: POLY PARAM DETECTED -> {poly_param}")
        try:
            # Parse Timestamp
            if "," in poly_param:
                parts = poly_param.split(",")
                # Format: x,y;x,y;...TIMESTAMP
                # The timestamp is the LAST element after the last comma or semicolon?
                # JS sends: `ptsStr + ',' + Date.now()` where ptsStr is `x,y;x,y`
                # So splitting by `,` might mix coords. 
                # Better: look for last comma
                last_comma_idx = poly_param.rfind(",")
                if last_comma_idx != -1:
                    timestamp = poly_param[last_comma_idx+1:]
                    if len(timestamp) > 9 and timestamp.isdigit():
                        poly_str = poly_param[:last_comma_idx]
                    else:
                        poly_str = poly_param
                else:
                    poly_str = poly_param
            else:
                poly_str = poly_param

            # Replicate View/Scale Logic
            img = st.session_state["image"]
            h, w = img.shape[:2]
            _dw = display_width  # Dynamic — resolved at top of main()
            
            zoom = st.session_state.get("zoom_level", 1.0)
            pan_x = st.session_state.get("pan_x", 0.5)
            pan_y = st.session_state.get("pan_y", 0.5)
            start_x, start_y, view_w, view_h = get_crop_params(w, h, zoom, pan_x, pan_y)
            scale_factor = _dw / view_w
            
            # Parse Points
            pts = []
            for p_pair in poly_str.split(";"):
                if "," in p_pair:
                    px, py = map(float, p_pair.split(","))
                    pts.append([int(px / scale_factor) + start_x, int(py / scale_factor) + start_y])
            
            if len(pts) > 2:
                # Determine Mode: Manual (Freehand) vs AI (Polygon)
                # "Lasso (Freehand)" -> Manual Fill (User expectation: "Draw the place to apply color")
                # "Polygonal Lasso" -> AI Assisted (SAM Box Prompts)
                
                current_tool = st.session_state.get("selection_tool", "")
                is_freehand = "Lasso (Freehand)" in current_tool
                
                # Check for explicit "Fill Selection" toggle (overrides default)
                # Default for Freehand is True (Manual), Default for Polygon is False (AI)
                force_manual = st.session_state.get("fill_selection", is_freehand)
                
                if is_freehand or force_manual:
                     print("DEBUG: processing as MANUAL MASK (Freehand)")
                     # Create blank mask
                     mask_shape = (h, w)
                     manual_mask = np.zeros(mask_shape, dtype=np.uint8)
                     
                     # Fill Polygon
                     pts_arr = np.array(pts, dtype=np.int32)
                     cv2.fillPoly(manual_mask, [pts_arr], 1)
                     
                     mask = manual_mask.astype(bool)
                else:
                    # STRATEGY: Use Bounding Box of Polygon as SAM Prompt
                    print("DEBUG: processing as AI MASK (SAM Box from Poly)")
                    pts_arr = np.array(pts)
                    x_min, y_min = np.min(pts_arr, axis=0)
                    x_max, y_max = np.max(pts_arr, axis=0)
                    box = [x_min, y_min, x_max, y_max]
                    
                    if not getattr(sam, "is_image_set", False):
                        with st.spinner("🧠 Preparing AI for precision tools..."):
                            sam.set_image(img)
                    current_tool = st.session_state.get("selection_tool", "")
                    is_wall_click_mode = "Wall Click" in current_tool
                    mask = sam.generate_mask(
                        box_coords=box, 
                        level=st.session_state.get("mask_level", 0), 
                        is_wall_only=st.session_state.get("is_wall_only", False),
                        is_wall_click=is_wall_click_mode
                    )

                if mask is not None:
                     # Check Operation: Add vs Subtract
                     operation = st.session_state.get("selection_op", "Add")
                     
                     if operation == "Subtract":
                         # ERASE Mode: Remove this mask from ALL existing active layers
                         cleaned_any = False
                         for layer in st.session_state["masks"]:
                             if layer.get("visible", True):
                                 # Apply subtraction: Keep existing True only if New is False
                                 target_mask = layer['mask']
                                 if sparse.issparse(target_mask):
                                     target_mask = target_mask.toarray()
                                     
                                 layer['mask'] = (target_mask > 0) & ~mask
                                 cleaned_any = True
                         
                         if cleaned_any:
                             st.session_state["render_id"] += 1
                             st.toast("✅ Area Erased!", icon="🧹")
                     else:
                         # ADD Mode: Append new layer
                         new_mask_entry = {
                            'mask': mask,
                            'color': st.session_state.get("picked_color", "#8FBC8F"),
                            'visible': True,
                            'name': f"Layer {len(st.session_state['masks'])+1}",
                            'refinement': 0,
                            'softness': st.session_state.get("selection_softness", 0),
                            'brightness': 0.0, 'contrast': 1.0, 'saturation': 1.0, 'hue': 0.0, 
                            'opacity': st.session_state.get("selection_highlight_opacity", 1.0), 
                            'finish': st.session_state.get("selection_finish", 'Standard')
                        }
                         st.session_state["masks"].append(new_mask_entry)
                         st.session_state["render_id"] += 1
                         st.toast("✅ Paint Applied!", icon="🎨")

                else:
                    st.toast("⚠️ No object found.", icon="🤷‍♂️")
                    pass
            
        except Exception as e:
            print(f"DEBUG: Poly Processor Error: {e}")
            import traceback
            traceback.print_exc()

        if "poly_pts" in st.query_params:
             del st.query_params["poly_pts"]
            
    # --- 4️⃣ RENDER IMAGE ---
    if st.session_state.get("image") is not None:
        render_visualizer_engine_v11(display_width)
    else:
        # Landing Page (Safe & Visible)
        st.markdown("""
            <div style="text-align: center; max-width: 800px; margin: 0 auto; padding: 20px;">
                <h1 style="font-size: 2.5rem; font-weight: 800; color: #111827; margin-bottom: 20px;">
                    Welcome to Color Visualizer
                </h1>
                <p style="font-size: 1.2rem; color: #4b5563; margin-bottom: 40px;">
                    Transform your space with AI. Upload a photo to begin experimenting with colors in real-time.
                </p>
                <div style="background: #f8f9fa; padding: 25px; border-radius: 16px; border: 1px dashed #ced4da; display: inline-block;">
                    <p style="margin: 0; color: #1f2937; font-weight: 600;">
                        👈 Start here: Use the sidebar to upload your photo
                    </p>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # --- 5️⃣ RENDER SIDEBAR LAST ---
    print("DEBUG: SIDEBAR RENDER")
    render_sidebar(sam, device_str)

    # --- 🤖 HIDDEN TECHNICAL BRIDGE (Bottom of script) ---
    st.markdown('<div id="global-sync-anchor"></div>', unsafe_allow_html=True)
    st.button("GLOBAL SYNC", key="global_sync_btn", help="Hidden sync for JS", type="secondary")
    st.markdown('<div class="global-sync-marker" style="display:none;" data-sync-id="global_sync"></div>', unsafe_allow_html=True)

    # MOBILE TOOLBAR REMOVED AS PER USER REQUEST (Existing flow preferred)
    pass

if __name__ == "__main__":
    main()

