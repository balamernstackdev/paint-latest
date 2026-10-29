
import os
import re

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# 1. CLEAN PINCH HANDLER (Center Logic)
# We focus on scaling (zoom) and simple panning.
# Origin logic is moved to CSS.
pinch_code = r"""    // 🤏 GLOBAL PINCH & PAN HANDLER (Centric Zoom)
    const handlePinch = (e) => {
        if (e.touches.length === 2) {
            window.isCanvasGesturing = true;
            
            const t1 = e.touches[0];
            const t2 = e.touches[1];
            
            // Current Distance
            const dist = Math.hypot(t2.clientX - t1.clientX, t2.clientY - t1.clientY);
            
            // Current Center
            const cx = (t1.clientX + t2.clientX) / 2;
            const cy = (t1.clientY + t2.clientY) / 2;

            if (window.lastPinchDist > 0) {
                // ZOOM CALCULATION
                const delta = dist / window.lastPinchDist;
                let newZoom = (window.userZoomLevel || 1.0) * delta;
                
                // Safety Limits
                if (newZoom < 0.5) newZoom = 0.5;   // Allow slight undershoot
                if (newZoom > 8.0) newZoom = 8.0;   // Higher Max Zoom
                
                window.userZoomLevel = newZoom;
                
                // PAN CALCULATION (From Finger Movement)
                if (window.lastPinchCenter && window.lastPinchCenter.x) {
                    const dx = cx - window.lastPinchCenter.x;
                    const dy = cy - window.lastPinchCenter.y;
                    
                    // Simple additive pan (1:1 movement)
                    window.panX = (window.panX || 0) + dx;
                    window.panY = (window.panY || 0) + dy;
                }
                
                applyResponsiveScale();
            }
            
            // Update State
            window.lastPinchDist = dist;
            window.lastPinchCenter = { x: cx, y: cy };
            window.lastPinchTime = Date.now();
            
            e.preventDefault(); 
            e.stopPropagation();
        }
    };"""

# 2. UPDATE SCALE FUNCTION (CSS Centering)
# Uses transform-origin: center center
# Uses absolute centering + translate chaining
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

            // BASE Scale (Fit to Logic)
            let baseScale = targetWidth / CANVAS_WIDTH;
            if (baseScale < 0.1) baseScale = 0.1;
            
            // Combined Scale
            let totalScale = baseScale * (window.userZoomLevel || 1.0);
            
            // Pan Values
            let px = window.panX || 0;
            let py = window.panY || 0;

            for (let iframe of iframes) {
                if (iframe.title === "streamlit_drawable_canvas.st_canvas" || iframe.src.includes('streamlit_drawable_canvas')) {
                    const wrapper = iframe.parentElement;
                    if (!wrapper) continue;

                    // Wrapper: Fixed Viewport
                    wrapper.style.cssText = `
                        width: ${Math.floor(CANVAS_WIDTH * baseScale)}px;
                        height: ${Math.floor(CANVAS_HEIGHT * baseScale)}px;
                        position: relative;
                        margin: 0 auto !important;
                        display: block !important;
                        overflow: hidden; /* ✂️ Clip zoomed content */
                        touch-action: none;
                        user-select: none;
                        -webkit-user-select: none;
                    `;

                    // Iframe: Centered & Scaled
                    // transform-origin: center center ensures zoom grows from middle
                    // translate(-50%, -50%) centers it initially
                    // translate(px, py) applies user pan
                    // scale(totalScale) checks zoom
                    
                    iframe.style.cssText = `
                        width: ${CANVAS_WIDTH}px;
                        height: ${CANVAS_HEIGHT}px;
                        position: absolute;
                        top: 50%; 
                        left: 50%;
                        transform-origin: center center; 
                        transform: translate(-50%, -50%) translate(${px}px, ${py}px) scale(${totalScale});
                        will-change: transform;
                        touch-action: none;
                        opacity: 1;
                        border: none;
                    `;
                }
            }
        } catch (e) { }
    }"""

# Replace handlePinch
if "const handlePinch = (e) => {" in js_content:
   pattern = re.compile(r'const handlePinch = \(e\) => \{[\s\S]*?\}\s*};', re.MULTILINE)
   js_content = re.sub(pattern, pinch_code, js_content, count=1)

# Replace applyResponsiveScale
if "function applyResponsiveScale() {" in js_content:
    s_idx = js_content.find("function applyResponsiveScale() {")
    e_idx = js_content.find("class PolygonEditor extends BaseEditor {")
    if s_idx != -1 and e_idx != -1:
        js_content = js_content[:s_idx] + scale_code + "\n\n    " + js_content[e_idx:]

with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)

print("Updated JS with Centered Zoom and Transform Chaining.")
