
import os
import re

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# 1. Update BaseEditor touchAction to pinch-zoom
# This allows native browser zoom but blocks standard pan, except pinch-zoom also blocks standard scrolling usually?
# No, "touch-action: pan-x pan-y pinch-zoom" allows everything.
# "touch-action: pinch-zoom" allows ONLY pinch zoom (and clicks).
# We want to allow pinch zoom (browser handled) but single finger?
# If we want native zoom, we should use `touch-action: pan-x pan-y pinch-zoom` 
# BUT we need to prevent scrolling if we want to DRAW.
# Ah, the dilemma.
# If we allow native zoom, we allow native scroll.
# If we block native scroll (touch-action: none), we block native zoom.
# So if the user wants "Two fingers zoom options", and we stick with touch-action: none, we MUST use Custom JS Zoom.

# The user said "before working properly" -> implies native behavior?
# The user might be referring to the "responsive image" layout issue I just fixed.
# "Mobile responsive image on mmobie devices, before working properly"
# This sentence structure is confusing. "Fix X, [it was] working properly before [something]?" OR "Fix X before [I can say it is] working properly"?
# OR "Fix mobile responsive image... [it behaves like] before working properly" (meaning it looks bad like before).

# Let's assume the user wants the Custom JS Zoom to be SMOOTH/BETTER or just Native Zoom.
# Given the "Two fingers zooming options" request, maybe they want to be able to zoom in to draw details.
# My Custom Zoom implementation does exactly that.

# However, I should honor the plan to revert to NATIVE if that's safer.
# BUT, native zoom + single finger drawing is mutually exclusive without complex pointer event handling (preventDefault on 1 finger, allow on 2).
# If I use `touch-action: none` (which I have), I have full control.
# If `handlePinch` works, it should be fine.
# Why did I think of reverting? Because of potential bugs or "weird feel".

# Let's try to IMPROVE the Custom Zoom instead of reverting, unless I am sure native is requested.
# "implement two fingers zooming options" -> sounds like "it's not there, add it".
# It IS there in code. Maybe it's not working?
# Ah, I see `window.parent.document.addEventListener`.
# Maybe on mobile, `e.touches` inside the `handlePinch` isn't firing correctly or valid?
# Or `preventDefault` usage.

# Let's stick to the Plan: Revert to Native + JS filtering for drawing.
# How to do native zoom + single finger draw?
# CSS: `touch-action: manipulation;` (or `pan-x pan-y pinch-zoom`)
# JS:
#   touchstart: if (touches.length === 1) e.preventDefault(); (Blocks scroll, allows draw?)
#   touchstart: if (touches.length === 2) return; (Allows browser to zoom?)
# Browsers are strict. `touchstart` is passive by default. You cannot preventDefault in passive listener.
# You must set `{ passive: false }`.
# So:
# 1. CSS: `touch-action: pan-x pan-y pinch-zoom;` (Allow everything by default)
# 2. JS:
#    overlay.addEventListener('touchstart', e => {
#        if (e.touches.length === 1) {
#            // Drawing! Block scroll.
#            e.preventDefault(); 
#        }
#        // If 2 fingers, do nothing (let browser zoom/scroll)
#    }, { passive: false });

# This is the standard way!
# My current code uses `touch-action: none` which forces ME to re-implement zoom.
# Switching to the Standard handling is much better.

# ACTION:
# 1. Update CSS to `touch-action: none` -> `touch-action: pan-x pan-y pinch-zoom` ? 
#    Actually, keeping `touch-action: none` is usually required for `pointermove` low latency.
#    But let's try the Event-based filter.

# AND I need to Clean up `canvas_touch_handler.js` to remove the Custom Zoom code if I go Native.
# AND I need to update `applyResponsiveScale` to be static (just fit width).

# Step 1: Replace applyResponsiveScale with simple version
simple_scale_logic = r"""    function applyResponsiveScale() {
        if (window.isCanvasGesturing) return; 
        try {
            const iframes = parent.document.getElementsByTagName('iframe');
            if (!iframes.length) return;

            let winW = parent.window.innerWidth || parent.document.documentElement.clientWidth;
            if (parent.window.visualViewport) {
                winW = parent.window.visualViewport.width;
            }

            const targetWidth = winW < 1024 ? winW - 4 : winW - 40;
            if (targetWidth <= 50 || !CANVAS_WIDTH) return;

            let scale = targetWidth / CANVAS_WIDTH;
            if (scale < 0.1) scale = 0.1;

            for (let iframe of iframes) {
                if (iframe.title === "streamlit_drawable_canvas.st_canvas" || iframe.src.includes('streamlit_drawable_canvas')) {
                    const wrapper = iframe.parentElement;
                    if (!wrapper) continue;

                    wrapper.style.cssText = `
                        width: ${Math.floor(CANVAS_WIDTH * scale)}px;
                        height: ${Math.floor(CANVAS_HEIGHT * scale)}px;
                        position: relative;
                        margin: 0 auto !important;
                        display: block !important;
                        overflow: visible;
                    `;

                    iframe.style.cssText = `
                        width: ${CANVAS_WIDTH}px;
                        height: ${CANVAS_HEIGHT}px;
                        transform: scale(${scale});
                        transform-origin: top left;
                        position: absolute;
                        top: 0; left: 0;
                        opacity: 1;
                    `;
                }
            }
        } catch (e) { }
    }"""

# Find existing applyResponsiveScale and replace
# We need to be careful with regex matching.
# Let's search for "function applyResponsiveScale() {" and match block?
# Or just replace the whole file? No.
# Use Python string split/find.

start_sig = "function applyResponsiveScale() {"
end_sig = "class PolygonEditor extends BaseEditor {"

if start_sig in js_content and end_sig in js_content:
    s_idx = js_content.find(start_sig)
    e_idx = js_content.find(end_sig)
    
    # We replace from s_idx to e_idx
    new_js = js_content[:s_idx] + simple_scale_logic + "\n\n    " + js_content[e_idx:]
    
    # Also remove handlePinch listeners to stop custom logic interference?
    # Or just leave them, they won't trigger if I clear the listeners.
    # I should remove the listeners block.
    
    # Remove the `handlePinch` function and its listeners.
    # It is located before applyResponsiveScale.
    
    # Let's simply write the cleaned JS file.
    
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(new_js)
    print("Reverted applyResponsiveScale to native-compatible static scaling.")

