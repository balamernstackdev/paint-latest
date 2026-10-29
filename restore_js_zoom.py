
import os
import re

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# 1. Re-Introduce the Custom Zoom Logic + Pan
# We will replace handlePinch and applyResponsiveScale with the "Good" version.
# The user's checklist asks for "distance = Math.sqrt(...) scale = distance / initialDistance".
# My previous implementation did exactly that: "const delta = dist / window.lastPinchDist;"

pinch_code = r"""    // 🤏 GLOBAL PINCH & PAN HANDLER (Custom JS)
    const handlePinch = (e) => {
        if (e.touches.length === 2) {
            window.isCanvasGesturing = true;
            
            const t1 = e.touches[0];
            const t2 = e.touches[1];
            const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
            const cx = (t1.clientX + t2.clientX) / 2;
            const cy = (t1.clientY + t2.clientY) / 2;

            if (window.lastPinchDist > 0) {
                // ZOOM
                const delta = dist / window.lastPinchDist;
                let newZoom = (window.userZoomLevel || 1.0) * delta;
                if (newZoom < 1.0) newZoom = 1.0;
                if (newZoom > 5.0) newZoom = 5.0; // Max Scale
                window.userZoomLevel = newZoom;
                
                // PAN
                if (window.lastPinchCenter && window.lastPinchCenter.x) {
                    const dx = cx - window.lastPinchCenter.x;
                    const dy = cy - window.lastPinchCenter.y;
                    window.panX = (window.panX || 0) + dx;
                    window.panY = (window.panY || 0) + dy;
                }
                
                applyResponsiveScale();
            }
            
            window.lastPinchDist = dist;
            window.lastPinchCenter = { x: cx, y: cy };
            window.lastPinchTime = Date.now();
            
            e.preventDefault(); 
            e.stopPropagation();
        }
    };"""

# Replace existing handlePinch
if "const handlePinch = (e) => {" in js_content:
   # Use regex to replace the function block
   pattern = re.compile(r'const handlePinch = \(e\) => \{[\s\S]*?\}\s*};', re.MULTILINE)
   js_content = re.sub(pattern, pinch_code, js_content, count=1)

# 2. Update applyResponsiveScale to use the Zoom/Pan
scale_code = r"""    function applyResponsiveScale() {
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

            // BASE Scale (to fit screen initially)
            let baseScale = targetWidth / CANVAS_WIDTH;
            if (baseScale < 0.1) baseScale = 0.1;
            
            // USER Zoom (multiplied)
            let totalScale = baseScale * (window.userZoomLevel || 1.0);

            for (let iframe of iframes) {
                if (iframe.title === "streamlit_drawable_canvas.st_canvas" || iframe.src.includes('streamlit_drawable_canvas')) {
                    const wrapper = iframe.parentElement;
                    if (!wrapper) continue;

                    // Wrapper stays at base size (or should it grow? No, wrapper is viewport)
                    // If wrapper grows, layout breaks. Wrapper should be fixed size (viewport).
                    // Canvas transforms INSIDE wrapper.
                    // Actually, if we want to pan, wrapper should clip? yes.
                    
                    wrapper.style.cssText = `
                        width: ${Math.floor(CANVAS_WIDTH * baseScale)}px;
                        height: ${Math.floor(CANVAS_HEIGHT * baseScale)}px;
                        position: relative;
                        margin: 0 auto !important;
                        display: block !important;
                        overflow: hidden; /* Clip the zoomed content */
                        touch-action: none;
                    `;

                    iframe.style.cssText = `
                        width: ${CANVAS_WIDTH}px;
                        height: ${CANVAS_HEIGHT}px;
                        transform: translate(${window.panX || 0}px, ${window.panY || 0}px) scale(${totalScale});
                        transform-origin: top left;
                        position: absolute;
                        top: 0; left: 0;
                        touch-action: none;
                        opacity: 1;
                    `;
                }
            }
        } catch (e) { }
    }"""

# Replace existing applyResponsiveScale
if "function applyResponsiveScale() {" in js_content:
    pattern = re.compile(r'function applyResponsiveScale\(\) \{[\s\S]*?const iframes[\s\S]*?catch \(e\) \{ \}', re.MULTILINE)
    # This might be tricky if braces don't match exactly.
    # Let's matching from signature to catch block.
    # A simpler way is to find the function signature and replace until "class PolygonEditor"?
    start_sig = "function applyResponsiveScale() {"
    end_sig = "class PolygonEditor extends BaseEditor {"
    
    s_idx = js_content.find(start_sig)
    e_idx = js_content.find(end_sig)
    
    if s_idx != -1 and e_idx != -1:
        js_content = js_content[:s_idx] + scale_code + "\n\n    " + js_content[e_idx:]

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)

print("Restored Custom JS Zoom logic.")
