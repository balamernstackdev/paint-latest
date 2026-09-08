
import os

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()    

# 1. Initialize State Variables
if "window.userZoomLevel" not in js_content:
    js_content = js_content.replace(
        "window.activePointers = new Map();", 
        "window.activePointers = new Map();\n    window.userZoomLevel = 1.0;\n    window.lastPinchDist = 0;"
    )

# 2. Add Pinch Logic
pinch_code = r"""
    // 🤏 GLOBAL PINCH HANDLER
    const handlePinch = (e) => {
        if (e.touches.length === 2) {
            window.isCanvasGesturing = true;
            const t1 = e.touches[0];
            const t2 = e.touches[1];
            const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
            
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
            window.lastPinchDist = dist;
            window.lastPinchTime = Date.now();
            e.preventDefault(); 
            e.stopPropagation();
        }
    };

    // Attach to parent to catch events before they hit iframe
    try {
        window.parent.document.addEventListener('touchmove', handlePinch, { capture: true, passive: false });
        window.parent.document.addEventListener('touchend', e => {
            if (e.touches.length < 2) {
                window.lastPinchDist = 0;
                setTimeout(() => window.isCanvasGesturing = false, 300);
            }
        }, { capture: true });
        
        // Also attach to local window just in case
        window.addEventListener('touchmove', handlePinch, { capture: true, passive: false });
        window.addEventListener('touchend', e => {
             if (e.touches.length < 2) window.lastPinchDist = 0;
        }, { capture: true });
        
    } catch (e) {}
"""

if "GLOBAL PINCH HANDLER" not in js_content:
    # Insert before "Config Check"
    js_content = js_content.replace("// Config Check", pinch_code + "\n    // Config Check")

# 3. Update applyResponsiveScale
# We need to make sure applyResponsiveScale uses userZoomLevel
# Find: let scale = targetWidth / CANVAS_WIDTH;
# Replace: let scale = (targetWidth / CANVAS_WIDTH) * (window.userZoomLevel || 1.0);

if "let scale = targetWidth / CANVAS_WIDTH;" in js_content:
    js_content = js_content.replace(
        "let scale = targetWidth / CANVAS_WIDTH;", 
        "let scale = (targetWidth / CANVAS_WIDTH) * (window.userZoomLevel || 1.0);"
    )

# 4. Remove max scale cap (crucial!)
if "if (scale > 1.0) scale = 1.0;" in js_content:
    js_content = js_content.replace(
        "if (scale > 1.0) scale = 1.0;", 
        "// if (scale > 1.0) scale = 1.0; // ALLOW ZOOM > 1.0"
    )

# 5. Fix touchAction to NONE so browser doesn't interfere
js_content = js_content.replace("touchAction: 'pinch-zoom'", "touchAction: 'none'")
js_content = js_content.replace("touch-action: pinch-zoom", "touch-action: none")

# 6. Call applyResponsiveScale inside handlePinch? 
# The function is defined later in the file. Javascript hoisting works for function declarations.
# So we can just add applyResponsiveScale() call inside the handlePinch logic above.
js_content = js_content.replace("// Force update", "applyResponsiveScale(); // Force update")

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)

print("Updated JS successfully")
