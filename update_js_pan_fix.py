
import os

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# REPLACE the handlePinch function body with the full PAN + ZOOM logic
# We need to find the old handlePinch and replace it.
# It starts with "const handlePinch = (e) => {" and ends with "};" before "try {"?
# No, it's inside the IIFE.

# Let's use a robust string replacement for the loop body.
pointer_logic_old = "if (window.lastPinchDist > 0) {"
pointer_logic_new = r"""if (window.lastPinchDist > 0) {
                // ZOOM
                const delta = dist / window.lastPinchDist;
                // Accumulate zoom with limits
                let newZoom = (window.userZoomLevel || 1.0) * delta;
                if (newZoom < 1.0) newZoom = 1.0;
                if (newZoom > 5.0) newZoom = 5.0;
                window.userZoomLevel = newZoom;
                
                // PAN
                const cx = (t1.clientX + t2.clientX) / 2;
                const cy = (t1.clientY + t2.clientY) / 2;
                
                if (window.lastPinchCenter && window.lastPinchCenter.x) {
                    const dx = cx - window.lastPinchCenter.x;
                    const dy = cy - window.lastPinchCenter.y;
                    window.panX = (window.panX || 0) + dx;
                    window.panY = (window.panY || 0) + dy;
                }
                
                window.lastPinchCenter = { x: cx, y: cy };
                
                // Force update
                applyResponsiveScale();
            }"""

if pointer_logic_old in js_content and "window.panX" not in js_content:
    # Find the block and replace. 
    # The old block was shorter: 
    # const delta = dist / window.lastPinchDist;
    # ...
    # window.userZoomLevel = newZoom;
    # // Force update
    # ...
    
    # Let's just create a new file content with the full function text
    pass

# Actually, the file content is manageable. Let's just find the `handlePinch` definition and replace the whole function.
# Or better, just rewrite the Whole JS file with the known-good content locally? No, that's too much code.
# Let's use the Python replacement approach but be very specific about the target string.

target_str = """
            if (window.lastPinchDist > 0) {
                const delta = dist / window.lastPinchDist;
                // Accumulate zoom with limits
                let newZoom = (window.userZoomLevel || 1.0) * delta;
                if (newZoom < 1.0) newZoom = 1.0;
                if (newZoom > 5.0) newZoom = 5.0;
                
                window.userZoomLevel = newZoom;
                
                // Force update
                const iframes = parent.document.getElementsByTagName('iframe');
                for (let iframe of iframes) {
                     if (iframe.title === "streamlit_drawable_canvas.st_canvas") {
                         // We can call applyResponsiveScale() directly if it's in scope, 
                         // but since we are inside the closure, we can just trigger it.
                         // Or better, just rely on frame loop if applyResponsiveScale runs often?
                         // It doesn't. We need to call it.
                     }
                }
            }
"""

# The previous update_js.py wrote this block (approximately).
# Let's try to match it.

# Actually, I can just use regex to find the block "if (window.lastPinchDist > 0) { ... }"
import re

pattern = re.compile(r'if \(window\.lastPinchDist > 0\) \{[\s\S]*?\}', re.MULTILINE)

replacement = r"""if (window.lastPinchDist > 0) {
                // ZOOM
                const delta = dist / window.lastPinchDist;
                let newZoom = (window.userZoomLevel || 1.0) * delta;
                if (newZoom < 1.0) newZoom = 1.0;
                if (newZoom > 5.0) newZoom = 5.0;
                window.userZoomLevel = newZoom;
                
                // PAN
                const cx = (t1.clientX + t2.clientX) / 2;
                const cy = (t1.clientY + t2.clientY) / 2;
                
                if (window.lastPinchCenter) {
                    const dx = cx - window.lastPinchCenter.x;
                    const dy = cy - window.lastPinchCenter.y;
                    window.panX = (window.panX || 0) + dx;
                    window.panY = (window.panY || 0) + dy;
                }
                window.lastPinchCenter = { x: cx, y: cy };

                applyResponsiveScale();
            }"""

js_content = re.sub(pattern, replacement, js_content, count=1)

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)
