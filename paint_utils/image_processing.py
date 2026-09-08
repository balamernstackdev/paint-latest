import cv2
import numpy as np
import streamlit as st
from PIL import Image
from paint_core.colorizer import ColorTransferEngine
from app_config.constants import UIConfig

def get_crop_params(image_width, image_height, zoom_level, pan_x, pan_y):
    """
    Calculate crop coordinates based on zoom and normalized pan (0.0 to 1.0).
    """
    if zoom_level <= 1.0:
        return 0, 0, image_width, image_height

    # visible width/height
    view_w = int(image_width / zoom_level)
    view_h = int(image_height / zoom_level)

    # ensure pan stays within bounds
    # pan_x=0 -> left edge, pan_x=1 -> right edge
    max_x = image_width - view_w
    max_y = image_height - view_h
    
    start_x = int(max_x * pan_x)
    start_y = int(max_y * pan_y)
    
    return start_x, start_y, view_w, view_h

def composite_image(original_rgb, masks_data):
    """
    Apply all color layers to user image using optimized multi-layer blending.
    PERFORMANCE: Uses incremental background caching to speed up tuning.
    """
    visible_masks = [m for m in masks_data if m.get('visible', True)]
    
    # 🎯 ULTRA-STABLE FULL COMPOSITE 🎯
    # Optimization: Pass original mask objects to Core to enable identity-based caching.
    # The Core engine handles sparse decompression and refinement internally.
    result = ColorTransferEngine.composite_multiple_layers(original_rgb, visible_masks)

    # --- Selection Highlight (Fast Blending) ---
    try:
        # ALWAYS apply highlight at the end, regardless of mask count.
        pending = st.session_state.get("pending_selection")
        if pending is not None:
            mask = pending['mask']
            # Decompress Pending if sparse (rare but possible)
            if sparse.issparse(mask): mask = mask.toarray()
            pc = st.session_state.get("picked_color", "#3B82F6")
            try:
                c_rgb = tuple(int(pc.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
                highlight = np.array([c_rgb[0], c_rgb[1], c_rgb[2]], dtype=np.uint8) 
            except:
                highlight = np.array(UIConfig.DEFAULT_HIGHLIGHT_COLOR, dtype=np.uint8) 
            
            # --- FASTER BLENDING (No float32 conversion) ---
            m_idx = mask
            if mask.shape[:2] != result.shape[:2]:
                m_idx = cv2.resize(mask.astype(np.uint8), (result.shape[1], result.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
            else:
                m_idx = mask > 0

            if m_idx.any():
                # Create a copy only if there's a highlight, to avoid mutating cached backgrounds
                result = result.copy()
                # Blend with 50% opacity using integer math: (A + B) / 2
                # We use uint16 to prevent overflow during addition
                result[m_idx] = ((result[m_idx].astype(np.uint16) + highlight.astype(np.uint16)) // 2).astype(np.uint8)
    except Exception as e:
        # Fallback to prevent crash if highlighting fails
        st.error(f"Highlight Error: {e}")
        pass

    return result

def process_lasso_path(scaled_path, w, h, thickness=6, fill=False):
    """
    Renders the SVG path from st_canvas into a binary mask.
    Handles 'M', 'L', 'Q' commands. 
    If fill=True, ensures the shape is closed and filled (Manual Fill Mode).
    If fill=False, draws a thick polyline (Brush/AI Mode).
    """
    mask = np.zeros((h, w), dtype=np.uint8)
    points = []
    
    try:
        for cmd in scaled_path:
            if not cmd: continue
            c_type = cmd[0]
            if c_type in ['M', 'L']:
                points.append([int(cmd[1]), int(cmd[2])])
            elif c_type == 'Q':
                points.append([int(cmd[3]), int(cmd[4])])
                
        if len(points) > 1:
            if fill and len(points) > 2:
                # 🎨 Manual Fill Mode: Solid enclosed shape
                cv2.fillPoly(mask, [np.array(points, np.int32)], 255)
            else:
                # 🧠 Brush/AI Mode: Thick polyline
                cv2.polylines(mask, [np.array(points, np.int32)], isClosed=False, color=255, thickness=max(1, thickness))
            
    except Exception as e:
        print(f"Lasso Path processing error: {e}")
        
    return mask > 0


def magic_wand_selection(image, seed_point, tolerance=10):
    if image is None: return None
    h, w = image.shape[:2]
    
    # Create mask compatible with floodFill (h+2, w+2)
    mask = np.zeros((h+2, w+2), np.uint8)
    
    flags = 4 | (255 << 8) | cv2.FLOODFILL_FIXED_RANGE | cv2.FLOODFILL_MASK_ONLY
    
    lo_diff = (tolerance, tolerance, tolerance)
    up_diff = (tolerance, tolerance, tolerance)
    
    try:
        cv2.floodFill(image, mask, seed_point, (255, 255, 255), lo_diff, up_diff, flags)
        return mask[1:-1, 1:-1] > 0
    except Exception as e:
        print(f'Magic Wand Error: {e}')
        return None


def to_grayscale_rgb(image_rgb):
    """Convert an RGB image to grayscale, returned as a 3-channel RGB array.
    
    This keeps the image in RGB format so it works seamlessly with all
    downstream rendering code that expects an (H, W, 3) array.
    
    Args:
        image_rgb: NumPy array (H, W, 3) in RGB format
        
    Returns:
        NumPy array (H, W, 3) — grayscale values repeated across all 3 channels
    """
    gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
    return cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)


def get_display_base_image(image_rgb):
    """Return the current base image respecting Grayscale Preview Mode.
    
    When grayscale_mode is ON: returns grayscale version of the image.
    When grayscale_mode is OFF: returns original RGB image unchanged.
    
    Never modifies the original image in session state.
    
    Args:
        image_rgb: Source RGB image from session_state["image"]
        
    Returns:
        NumPy array (H, W, 3) in RGB format
    """
    if st.session_state.get("grayscale_mode", False):
        return to_grayscale_rgb(image_rgb)
    return image_rgb


def composite_image_grayscale_aware(original_rgb, masks_data):
    """composite_image variant that honours Grayscale Preview Mode.
    
    In NORMAL mode:
        Behaves identically to composite_image().
    
    In GRAYSCALE mode:
        - Starts from a grayscale base
        - Applies color ONLY inside each painted mask (rest stays gray)
        - This creates the signature "color pops on grayscale" look
    
    Args:
        original_rgb: The color source image (always the original color photo)
        masks_data: List of mask layer dicts (same format as composite_image)
    
    Returns:
        NumPy array (H, W, 3) in RGB format
    """
    from paint_core.colorizer import ColorTransferEngine
    from scipy import sparse as _sparse

    gray_mode = st.session_state.get("grayscale_mode", False)

    if not gray_mode:
        # Normal path — delegate to existing fast compositor
        from paint_utils.image_processing import composite_image
        return composite_image(original_rgb, masks_data)

    # ── Grayscale-mode path ──────────────────────────────────────────────
    # 1. Build grayscale base
    gray_base = to_grayscale_rgb(original_rgb)
    h, w = gray_base.shape[:2]

    # Start with gray canvas
    result = gray_base.copy().astype(np.float32) / 255.0

    # 2. For each visible layer: composite color ONLY inside the mask
    for layer in masks_data:
        if not layer.get("visible", True):
            continue
        mask = layer["mask"]
        if _sparse.issparse(mask):
            mask = mask.toarray()
        color_hex = layer.get("color", "#FFFFFF")
        opacity = layer.get("opacity", 1.0)

        # Resize mask if needed
        if mask.shape[:2] != (h, w):
            mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
        else:
            mask = mask > 0

        if not mask.any():
            continue

        # Build a fully-colored version of the ORIGINAL image under this mask
        # Use the same LAB recolor as the main engine for consistency
        try:
            r, g, b = ColorTransferEngine.hex_to_rgb(color_hex)
            target_a, target_b = ColorTransferEngine.get_target_ab(color_hex)

            orig_f = original_rgb.astype(np.float32) / 255.0
            orig_lab = cv2.cvtColor(orig_f, cv2.COLOR_RGB2Lab)
            L, A, B = cv2.split(orig_lab)

            new_A = np.full_like(A, target_a)
            new_B = np.full_like(B, target_b)
            colored_lab = cv2.merge([L, new_A, new_B])
            colored_rgb = cv2.cvtColor(colored_lab, cv2.COLOR_Lab2RGB)  # float32 0-1
        except Exception:
            colored_rgb = result.copy()

        # Soft mask for feathered edges
        mask_f = mask.astype(np.float32)
        softness = layer.get("softness", 0)
        if softness > 0:
            k = softness * 4 + 1
            mask_f = cv2.GaussianBlur(mask_f, (k, k), 0)
        else:
            mask_f = cv2.GaussianBlur(mask_f, (3, 3), 0)

        mask_3ch = np.stack([mask_f] * 3, axis=-1) * opacity

        # Blend colored pixels over gray only inside mask
        result = result * (1.0 - mask_3ch) + colored_rgb * mask_3ch

    # 3. Pending selection highlight (same as normal mode)
    try:
        pending = st.session_state.get("pending_selection")
        if pending is not None:
            pmask = pending["mask"]
            if _sparse.issparse(pmask):
                pmask = pmask.toarray()
            pc = st.session_state.get("picked_color", "#3B82F6")
            try:
                c_rgb = tuple(int(pc.lstrip("#")[i:i+2], 16) / 255.0 for i in (0, 2, 4))
                highlight = np.array(c_rgb, dtype=np.float32)
            except:
                highlight = np.array([0.23, 0.51, 0.96], dtype=np.float32)

            if pmask.shape[:2] != (h, w):
                pmask = cv2.resize(pmask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST) > 0
            else:
                pmask = pmask > 0

            if pmask.any():
                result_copy = result.copy()
                result_copy[pmask] = (
                    result_copy[pmask] * 0.5 + highlight * 0.5
                )
                result = result_copy
    except Exception:
        pass

    return np.clip(result * 255.0, 0, 255).astype(np.uint8)

