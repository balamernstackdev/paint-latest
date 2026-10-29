# 🚀 Phase 1: Performance Optimization Plan

This roadmap outlines the steps to significantly improve the speed and stability of your AI Paint Visualizer.

## 1. Optimize Image Processing Resolution
**Goal:** Reduce CPU load by 40-50% while maintaining visual quality on mobile devices.

- **Current State:** `MAX_IMAGE_DIMENSION` is set to `1100` pixels. This is too high for real-time segmentation on CPU, especially for `MobileSAM` which is optimized for smaller inputs (usually 1024x1024 max, but 640-800 is faster).
- **Proposed Change:**
  - Lower default processing resolution to `800` px in `config/constants.py`.
  - This matches your canvas width (`DEFAULT_CANVAS_WIDTH = 800`), ensuring 1:1 pixel mapping without waste.
  - *Result:* Faster mask generation (approx 1.5x speedup).

## 2. Smart Caching for Compositing
**Goal:** Eliminate "white screen" flickers and reduce render time by 80%.

- **Current State:** The `render_visualizer_engine_v11` function likely recomposites *all* layers every time you add a new stroke.
- **Proposed Change:**
  - Implement **Layer Caching**:
    - Cache the "User Painted Layers" into a single merged image (`st.session_state["cached_composite"]`).
    - When adding a new layer, just blend the *new* mask on top of the cached composite.
    - Only perform a full re-render when an existing layer is *Erased* or *Hidden*.
  - *Result:* Instant visual feedback for "Add" operations.

## 3. Asynchronous Model Inference (Spinners)
**Goal:** Stop the UI from freezing/hanging during processing.

- **Current State:** The app hangs during `sam.set_image()` and `sam.generate_mask()`.
- **Proposed Change:**
  - The `utils/async_processor.py` is already partially set up. We will enforce its usage for *all* model interactions.
  - Add a dedicated "Processing..." state that shows a lightweight loading spinner while the heavy computation happens in a background thread.

## 4. MobileSAM Verification
**Goal:** Ensure the fastest model is actually running.

- **Current State:** Config points to `vit_t` (MobileSAM), but we must ensure it's not falling back to the default `vit_b` if weights are missing.
- **Proposed Change:**
  - Add a strict check in `core/segmentation.py`. If `mobile_sam.pt` is missing, auto-download it instead of falling back to a slow model.

---

### 🛑 User Action Required
To apply these changes safely, I will perform them one file at a time.
**Shall I begin with Step 1 (Resolution & Caching)?**
