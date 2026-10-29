# Upgrade Roadmap: Phase 3 - "Pro" Features

Great news! The core performance optimizations (**Sparse Masks, AI Quantization**) and visual upgrades (**Texture Mode**) are now **COMPLETE**.

Your project is stable and fast. The next set of upgrades should focus on **User Control** and **Export Quality**.

## 1. Top Priority: User Control Features

### **A. Manual "Touch-up" Brush (Critical)**
*   **The Problem:** AI is 95% perfect, but sometimes misses a corner or paints a light switch.
*   **The Solution:** Add a manual "Brush" and "Eraser" tool.
*   **How to Build:**
    1.  Add a generic "Paint Brush" tool in the sidebar.
    2.  When the user draws on the canvas, capture that path.
    3.  **Add Mode:** Combine the drawn path with the current layer using `OR`.
    4.  **Erase Mode:** Remove the drawn path using `AND NOT`.

### **B. Magic Wand Tool**
*   **The Problem:** Painting a simple, solid-colored wall with AI feels like overkill and can be slow.
*   **The Solution:** A classic "Magic Wand" like Photoshop.
*   **How to Build:**
    1.  Use OpenCV's `cv2.floodFill` algorithm.
    2.  Input: Click point + Color Threshold (Tolerance).
    3.  Output: A mask of all connected pixels with similar color.

## 2. Top Priority: Output Quality

### **A. Smart High-Res Export**
*   **The Problem:** Users are painting on a resized 800px preview. The download is currently low resolution.
*   **The Solution:** "Replay" the paint job on the original 4K image during export.
*   **How to Build:**
    1.  Keep a log of all operations (e.g., `Layer 1: Box=[100, 200...], Color=#FF0000`).
    2.  When user clicks "Download":
    3.  Load `image_original` (hidden from UI).
    4.  Scale all coordinates up (e.g., `x * 4`).
    5.  Re-run the masking and coloring on the 4K image.
    6.  Serve the high-res file.

## 3. Future Architecture Upgrade

### **Async Background Processing**
*   **The Problem:** The "Running..." spinner blocks the entire interface while the AI thinks.
*   **The Solution:** Move the heavy AI work to a background thread.
*   **How to Build:**
    1.  Use `concurrent.futures.ThreadPoolExecutor`.
    2.  Submit the `sam.generate_mask` task.
    3.  Show a "Processing..." status indicator that polls for the result without freezing the UI buttons.

## Summary Checklist
- [x] Memory Optimization (Sparse Matrices)
- [x] Realistic Texture Rendering
- [ ] Manual Touch-up Tools
- [ ] High-Res Export
- [ ] Magic Wand
