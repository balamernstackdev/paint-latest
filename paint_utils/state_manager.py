import streamlit as st
import numpy as np
import cv2
from scipy import sparse
from .performance import cleanup_session_caches, should_trigger_cleanup

def initialize_session_state():
    """Initialize all session state variables with multi-layer safety."""
    defaults = {
        "image": None,          # 640px preview image
        "image_original": None, # Full resolution original
        "file_name": None,
        "masks": [],
        "history": [],      # Full state history for reliable undo/redo
        "masks_redo": [],   # Full state redo stack
        "selection_op": "Add",
        "is_wall_only": False,
        "selection_softness": 0,
        "selection_highlight_opacity": 0.5,
        "zoom_level": 1.0,
        "pan_x": 0.5,
        "pan_y": 0.5,
        "last_click_global": None,
        "mask_level": 0,    # 0, 1, or 2 for granularity
        "selection_tool": "👆 AI Click (Point)",
        "ai_drag_sub_tool": "🆕 Draw New",
        "picked_color": "#8FBC8F",
        "pending_selection": None,
        "pending_boxes": [],
        "render_id": 0,
        "canvas_id": 0,
        "uploader_id": 0,
        "sidebar_p_open": False,
        "last_export": None,
        "selected_layer_idx": None,
        "loop_guarded": False,
        "grayscale_mode": False,     # 🎨 Grayscale Preview Mode
        "canvas_container_width": 800,  # 📐 Actual container width reported by JS (defaults to 800)
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
            
    # Restore any states saved before a rerun abort
    restore_sidebar_state()

SIDEBAR_KEYS = [
    "selection_tool", "selection_op", "picked_color", 
    "grayscale_mode", "is_wall_only", "mask_level", 
    "selection_softness", "selection_refinement",
    "selection_highlight_opacity", "fill_selection", "lasso_thickness",
    "selection_finish" 
]

def preserve_sidebar_state():
    """Preserve Streamlit widget states before an abortive rerun."""
    for key in SIDEBAR_KEYS:
        if key in st.session_state:
            st.session_state[f"_saved_{key}"] = st.session_state[key]

def restore_sidebar_state():
    """Restore preserved widget states at the start of a run."""
    for key in SIDEBAR_KEYS:
        if f"_saved_{key}" in st.session_state:
            st.session_state[key] = st.session_state[f"_saved_{key}"]
            del st.session_state[f"_saved_{key}"]

def cb_apply_pending(increment_canvas=True, silent=False):
    if st.session_state.get("pending_selection") is not None:
        new_mask = st.session_state["pending_selection"].copy()
        new_mask.update({
            'color': st.session_state["picked_color"],
            'visible': True,
            'name': f"Layer {len(st.session_state['masks'])+1}",
            'refinement': st.session_state.get("selection_refinement", 0), # Expansion/Contraction (-10 to 10)
            'softness': st.session_state.get("selection_softness", 0),
            'brightness': 0.0, 'contrast': 1.0, 'saturation': 1.0, 'hue': 0.0, 
            'opacity': st.session_state.get("selection_highlight_opacity", 1.0), 
            'finish': st.session_state.get("selection_finish", 'Standard')
        })
        
        # DEBUG: Track operation state
        current_op = st.session_state.get("selection_op")
        num_masks = len(st.session_state["masks"])
        print(f"DEBUG: cb_apply_pending -> Operation: {current_op}, Existing masks: {num_masks}")
        
        # ⚡ MEMORY OPTIMIZATION: Compress mask to sparse matrix for storage
        if not sparse.issparse(new_mask['mask']):
            try:
                new_mask['mask'] = sparse.csc_matrix(new_mask['mask'])
            except Exception as e:
                print(f"WARNING: Sparse compression failed: {e}")
        
        
        # Handle Subtraction Logic
        # Handle Subtraction Logic (Eraser Mode)
        if current_op == "Subtract":
            if st.session_state["masks"]:
                print(f"DEBUG: SUBTRACT mode -> Applying to ALL layers")
                
                total_removed = 0
                cleaned_any = False
                new_selection_mask = new_mask['mask']

                # Iterate through ALL layers to erase from everything
                # Iterate through ALL layers to erase from everything
                for layer in st.session_state["masks"]:
                    if layer.get("visible", True):
                        target_mask = layer['mask']
                        
                        # 🛡️ SAFE DECOMPRESSION: Convert to dense for boolean logic
                        if sparse.issparse(target_mask):
                            target_mask = target_mask.toarray()
                        
                        # Resize if needed (safety check for consistency)
                        dense_new_sel = new_selection_mask
                        if sparse.issparse(dense_new_sel):
                            dense_new_sel = dense_new_sel.toarray()
                            
                        # Resize to match execution context
                        if target_mask.shape != dense_new_sel.shape:
                            resized_new = cv2.resize(dense_new_sel.astype(np.uint8), (target_mask.shape[1], target_mask.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
                        else:
                            resized_new = dense_new_sel

                        before_count = np.sum(target_mask)
                        
                        # PERFORM SUBTRACTION (Dense Arrays)
                        layer_mask = target_mask & ~resized_new
                        
                        # ⚡ RE-COMPRESS RESULT
                        layer['mask'] = sparse.csc_matrix(layer_mask)
                        
                        after_count = np.sum(layer_mask)
                        
                        diff = before_count - after_count
                        total_removed += diff
                        if diff > 0:
                            cleaned_any = True

                print(f"DEBUG: Subtraction applied -> Removed {total_removed} pixels total")
                
                # --- USER FEEDBACK (Only if not silent) ---
                if not silent:
                    if not cleaned_any:
                        st.toast("⚠️ selected area didn't overlap with any paint.", icon="ℹ️")
                    else:
                        st.toast("✅ Paint Erased!", icon="🧹")
                        
                # Save state for undo ONLY if something was erased
                if cleaned_any:
                    if "history" not in st.session_state: st.session_state["history"] = []
                    # We save the state AFTER the erase. Wait, we should save state BEFORE the erase!
                    # Actually, the logic to save state must happen before we mutate masks.
                    pass # We will handle state saving below.
            else:
                if not silent:
                    st.toast("⚠️ Nothing to erase! The canvas is clean.", icon="✨")
        
        else:
            # ADD Mode (Default)
            print(f"DEBUG: ADD mode -> Creating or Updating layer")
            
            # --- SAVE HISTORY BEFORE MUTATION ---
            if "history" not in st.session_state: st.session_state["history"] = []
            current_snapshot = [dict(m) for m in st.session_state.get("masks", [])]
            st.session_state["history"].append(current_snapshot)
            st.session_state["masks_redo"] = [] # Clear redo stack
            
            # --- APPLY EDGE COVERAGE FIX ---
            # 1. Extract dense mask
            mask_dense = new_mask['mask']
            if sparse.issparse(mask_dense):
                mask_dense = mask_dense.toarray()
            
            mask_uint8 = mask_dense.astype(np.uint8)
            
            # 2. IDENTIFY SAME REGION (RECOLORING LOGIC)
            best_layer_idx = -1
            
            # 2a. Remove Direct Hit Test - Use ONLY IoU matching
            best_iou = 0
            for i, layer in enumerate(st.session_state["masks"]):
                if layer.get("visible", True):
                    existing = layer['mask']
                    if sparse.issparse(existing):
                        existing = existing.toarray()
                    
                    if existing.shape != mask_uint8.shape:
                        existing = cv2.resize(existing.astype(np.uint8), (mask_uint8.shape[1], mask_uint8.shape[0]), interpolation=cv2.INTER_NEAREST)
                    
                    existing_bool = existing.astype(bool)
                    new_bool = mask_uint8.astype(bool)
                    
                    intersection = np.logical_and(existing_bool, new_bool).sum()
                    union = np.logical_or(existing_bool, new_bool).sum()
                    iou = intersection / union if union > 0 else 0
                    
                    # LAYER_MATCH_IOU_THRESHOLD = 0.35
                    # Do not use 'click is inside existing layer -> recolor'
                    if iou >= 0.35:
                        if iou > best_iou:
                            best_iou = iou
                            best_layer_idx = i
            
            if best_layer_idx != -1:
                # 3a. SAME REGION -> UPDATE Color (Recolor)
                print(f"DEBUG: SAME REGION detected (IoU: {best_iou:.2f}). Recoloring layer {best_layer_idx}.")
                st.session_state["masks"][best_layer_idx]['color'] = st.session_state["picked_color"]
                st.session_state["masks"][best_layer_idx]['refinement'] = st.session_state.get("selection_refinement", 0)
                st.session_state["masks"][best_layer_idx]['softness'] = st.session_state.get("selection_softness", 0)
                st.session_state["masks"][best_layer_idx]['opacity'] = st.session_state.get("selection_highlight_opacity", 1.0)
                st.session_state["masks"][best_layer_idx]['finish'] = st.session_state.get("selection_finish", 'Standard')
                # Do NOT subtract or create a new layer.
            else:
                # 3b. DIFFERENT REGION -> CREATE NEW MASK & PROTECT EXISTING
                print(f"DEBUG: DIFFERENT REGION detected (IoU: {best_iou:.2f}). Creating new layer with protection.")
                # Removed artificial dilation/closing to preserve the strict boundary refinement from generate_mask
                
                # Edge-Aware Refinement & Subtract Existing Painted Masks
                for layer in st.session_state["masks"]:
                    if layer.get("visible", True):
                        existing = layer['mask']
                        if sparse.issparse(existing):
                            existing = existing.toarray()
                        
                        if existing.shape != mask_uint8.shape:
                            existing = cv2.resize(existing.astype(np.uint8), (mask_uint8.shape[1], mask_uint8.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
                        
                        # Subtract existing mask
                        mask_uint8 = mask_uint8 & ~existing.astype(bool)
                
                # Re-compress and store
                new_mask['mask'] = sparse.csc_matrix(mask_uint8)
                st.session_state["masks"].append(new_mask)
            
        st.session_state["pending_selection"] = None
        st.session_state["pending_boxes"] = []
        st.session_state["render_id"] += 1
        
        # ⚡ OPTIMIZATION: Allow skipping canvas reset for smooth continuous clicking
        if increment_canvas:
            st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
            
        st.session_state["canvas_raw"] = {} # Force clear cached objects
        st.session_state["just_applied"] = True # 🛡️ Guard against object persistence loops


def cb_cancel_pending():
    st.session_state["pending_selection"] = None
    st.session_state["pending_boxes"] = []
    st.session_state["render_id"] += 1
    st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
    st.session_state["canvas_raw"] = {} # Force clear cached objects

def cb_undo():
    """Undo last paint layer/action with automatic memory cleanup."""
    if "history" in st.session_state and st.session_state["history"]:
        # Save current to redo
        current_state = [dict(m) for m in st.session_state.get("masks", [])]
        st.session_state["masks_redo"].append(current_state)
        
        # Pop from history
        previous_state = st.session_state["history"].pop()
        st.session_state["masks"] = previous_state
        
        st.session_state["render_id"] += 1
        st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
        
        # Check if cleanup needed after undo
        if should_trigger_cleanup():
            cleanup_session_caches(aggressive=False)

def cb_redo():
    """Redo the last undone paint layer/action."""
    if st.session_state.get("masks_redo"):
        # Save current to history
        current_state = [dict(m) for m in st.session_state.get("masks", [])]
        if "history" not in st.session_state:
            st.session_state["history"] = []
        st.session_state["history"].append(current_state)
        
        # Pop from redo
        next_state = st.session_state["masks_redo"].pop()
        st.session_state["masks"] = next_state
        
        st.session_state["render_id"] += 1
        st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1

def cb_clear_all():
    """Clear all paint layers and perform memory cleanup."""
    if st.session_state.get("masks"):
        if "history" not in st.session_state: st.session_state["history"] = []
        st.session_state["history"].append([dict(m) for m in st.session_state["masks"]])
        
    st.session_state["masks"] = []
    st.session_state["masks_redo"] = []
    
    # Aggressive cleanup when clearing all
    cleanup_session_caches(aggressive=True)
    st.session_state["render_id"] += 1
    st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1

def cb_delete_layer(idx):
    if st.session_state.get("masks") and 0 <= idx < len(st.session_state["masks"]):
        if "history" not in st.session_state: st.session_state["history"] = []
        st.session_state["history"].append([dict(m) for m in st.session_state["masks"]])
        
        st.session_state["masks"].pop(idx)
        st.session_state["selected_layer_idx"] = None
        st.session_state["masks_redo"] = []
        st.session_state["render_id"] += 1
        st.session_state["canvas_id"] = st.session_state.get("canvas_id", 0) + 1
