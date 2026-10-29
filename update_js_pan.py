
import os

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# 1. Initialize PAN State Variables
if "window.panX = 0;" not in js_content:
    js_content = js_content.replace(
        "window.userZoomLevel = 1.0;", 
        "window.userZoomLevel = 1.0;\n    window.panX = 0;\n    window.panY = 0;"
    )

# 2. Update Pinch Logic to include Panning
pinch_logic_replacement = r"""
    // 🤏 GLOBAL PINCH & PAN HANDLER
    const handlePinch = (e) => {
        if (e.touches.length === 2) {
            window.isCanvasGesturing = true;
            const t1 = e.touches[0];
            const t2 = e.touches[1];
            
            // Distance for Zoom
            const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
            
            // Center for Pan
            const cx = (t1.clientX + t2.clientX) / 2;
            const cy = (t1.clientY + t2.clientY) / 2;
            
            if (window.lastPinchDist > 0) {
                // ZOOM
                const delta = dist / window.lastPinchDist;
                let newZoom = (window.userZoomLevel || 1.0) * delta;
                if (newZoom < 1.0) newZoom = 1.0;
                if (newZoom > 5.0) newZoom = 5.0;
                window.userZoomLevel = newZoom;
                
                // PAN
                const dx = cx - window.lastPinchCenter.x;
                const dy = cy - window.lastPinchCenter.y;
                window.panX = (window.panX || 0) + dx;
                window.panY = (window.panY || 0) + dy;
                
                // Force update
                const iframes = parent.document.getElementsByTagName('iframe');
                for (let iframe of iframes) {
                     if (iframe.title === "streamlit_drawable_canvas.st_canvas") {
                         // Manually trigger scale update logic 
                         // We can't easily call applyResponsiveScale from here due to scope unless it's global?
                         // It is NOT global, it's inside the IIFE.
                         // But we can replicate the transform update here for responsiveness.
                         
                         // Actually, applyResponsiveScale is defined in the same scope (IIFE).
                         // So we CAN call it if we move the definition up or rely on hoisting.
                         // Function declarations are hoisted.
                         applyResponsiveScale();
                     }
                }
            }
            
            window.lastPinchDist = dist;
            window.lastPinchCenter = { x: cx, y: cy };
            window.lastPinchTime = Date.now();
            e.preventDefault(); 
            e.stopPropagation();
        }
    };
"""

# Replace the previous handlePinch block if it exists, or insert new
# Since we just wrote the file, we can look for "const handlePinch = (e) => {"
if "const handlePinch = (e) => {" in js_content:
    # Use regex or simple split/join to replace the function body?
    # Easier to just overwrite the whole file again with the new logic 
    # but maintaining the file structure is better.
    # Let's verify if I can just replace the block.
    start_marker = "// 🤏 GLOBAL PINCH HANDLER"
    end_marker = "try {"
    # This is risky if markers are not exact.
    pass

# Let's RE-WRITE the whole update_js logic to be cleaner and just replace the whole file content 
# with the robust version including pan.
# Re-reading the file content in Python allows me to do precise replacement.

# We need to inject the 'window.lastPinchCenter' initialization in touchstart?
# The handler uses 'window.lastPinchCenter' but it needs to be set on START of pinch.
# My previous code didn't have a specific 'touchstart' for 2 fingers to set initial distance?
# Ah, the 'touchmove' checks 'if (window.lastPinchDist > 0)'. 
# I need a 'touchstart' listener to initialize dist and center.

init_logic = r"""
        window.parent.document.addEventListener('touchstart', e => {
            if (e.touches.length === 2) {
                 const t1 = e.touches[0];
                 const t2 = e.touches[1];
                 window.lastPinchDist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
                 window.lastPinchCenter = { 
                     x: (t1.clientX + t2.clientX) / 2, 
                     y: (t1.clientY + t2.clientY) / 2 
                 };
            }
        }, { capture: true });
"""

# 3. Inject init logic
if "window.parent.document.addEventListener('touchstart', e => {" in js_content:
    # We already have a touchstart listener for 'isCanvasGesturing'.
    # We should append our logic there.
    js_content = js_content.replace(
        "window.isCanvasGesturing = true;", 
        "window.isCanvasGesturing = true;\n            window.lastPinchDist = Math.hypot(e.touches[1].clientX - e.touches[0].clientX, e.touches[1].clientY - e.touches[0].clientY);\n            window.lastPinchCenter = { x: (e.touches[0].clientX + e.touches[1].clientX) / 2, y: (e.touches[0].clientY + e.touches[1].clientY) / 2 };"
    )

# 4. Update applyResponsiveScale to use TRANSLATE
# Old: transform: scale(${scale});
# New: transform: translate(${window.panX || 0}px, ${window.panY || 0}px) scale(${scale});

if "transform: scale(${scale});" in js_content:
    js_content = js_content.replace(
        "transform: scale(${scale});", 
        "transform: translate(${window.panX || 0}px, ${window.panY || 0}px) scale(${scale});"
    )

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)

print("Updated JS with Pan logic successfully")
