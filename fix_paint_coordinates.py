
import os
import re

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    js_content = f.read()

# 1. Update applyResponsiveScale to transform OVERLAY (sibling of iframe)
# We look for the loop over iframes and add logic for overlay
new_scale_logic = r"""    function applyResponsiveScale() {
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

            // BASE Scale
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
                        overflow: hidden; 
                        touch-action: none;
                        user-select: none;
                        -webkit-user-select: none;
                    `;

                    // Shared Transform Style for Iframe AND Overlay
                    const transformStyle = `
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

                    iframe.style.cssText = transformStyle;

                    // 🛠️ APPLY TO OVERLAY TOO
                    const overlay = wrapper.querySelector('[id$="-overlay"]');
                    if (overlay) {
                         // Keep base overlay styles but override transform/size
                         overlay.style.cssText = `
                             ${transformStyle}
                             display: block; 
                             z-index: 999;
                             cursor: crosshair;
                             overflow: visible;
                         `;
                         // Ensure overlay has correct ID style for touch
                         overlay.style.touchAction = 'none';
                    }
                }
            }
        } catch (e) { }
    }"""

# 2. Update BoxEditor/PolygonEditor Input Logic to handle Scale
# We need to divide by the visual scale factor.

# We will define a helper function in JS to get the current scale factor from the rect?
# Or just calculate inline.
# `const scale = rect.width / CANVAS_WIDTH;`
# `const rx = (e.clientX - rect.left) / scale;`
# `const ry = (e.clientY - rect.top) / scale;`

# I will replace the BoxEditor and PolygonEditor classes entirely or valid chunks.
# BoxEditor.onPointerDown
box_pointer_down = r"""        onPointerDown(e) {
            // 🛡️ STRICT GESTURE GUARD
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1 || (Date.now() - window.lastPinchTime < 600)) {
                this.cancelDrawing();
                return;
            }

            this.overlay.setPointerCapture(e.pointerId);

            const rect = this.overlay.getBoundingClientRect();
            // 🔍 COORDINATE MAPPING (Visual -> Intrinsic)
            // rect.width is the ZOOMED visual width. CANVAS_WIDTH is validation.
            const scale = rect.width / CANVAS_WIDTH;
            const x = (e.clientX - rect.left) / scale;
            const y = (e.clientY - rect.top) / scale;

            // 1. Check Active Handles
            if (e.target.dataset.handle) {
                this.isMoving = false;
                this.isDrawing = false;
                this.activeHandle = e.target.dataset.handle;
                this.startBox = { ...this.boxes[this.selectedIndex] };
                this.startX = x; // Store intrinsic start
                this.startY = y;
                return;
            }

            // 2. Check Box Click (Move)
            for (let i = this.boxes.length - 1; i >= 0; i--) {
                const b = this.boxes[i];
                if (x >= b.x && x <= b.x + b.w && y >= b.y && y <= b.y + b.h) {
                    this.selectedIndex = i;
                    this.isMoving = true;
                    this.isDrawing = false;
                    this.activeHandle = null;
                    this.startX = x;
                    this.startY = y;
                    this.startBox = { ...b };
                    this.updateDOM();
                    return;
                }
            }

            // 3. New Box
            this.isDrawing = true;
            this.isMoving = false;
            this.activeHandle = null;
            this.startX = x;
            this.startY = y;
            const newBox = { x, y, w: 0, h: 0 };
            this.boxes.push(newBox);
            this.selectedIndex = this.boxes.length - 1;
            this.startBox = { ...newBox };
            this.updateDOM();
        }"""

# BoxEditor.onPointerMove
box_pointer_move = r"""        onPointerMove(e) {
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1) {
                this.cancelDrawing();
                return;
            }
            if (!this.isDrawing && !this.isMoving && !this.activeHandle) return;
            e.preventDefault();

            const rect = this.overlay.getBoundingClientRect();
            // 🔍 COORDINATE MAPPING
            const scale = rect.width / CANVAS_WIDTH;
            const x = (e.clientX - rect.left) / scale;
            const y = (e.clientY - rect.top) / scale;

            if (this.isDrawing) {
                const b = this.boxes[this.selectedIndex];
                const minX = Math.min(this.startX, x);
                const minY = Math.min(this.startY, y);
                const w = Math.abs(x - this.startX);
                const h = Math.abs(y - this.startY);
                // Clamp
                b.x = Math.max(0, minX);
                b.y = Math.max(0, minY);
                b.w = Math.min(w, CANVAS_WIDTH - b.x); // Clamp to Intrinsic Size
                b.h = Math.min(h, CANVAS_HEIGHT - b.y);
            }
            else if (this.isMoving) {
                const dx = x - this.startX;
                const dy = y - this.startY;
                const b = this.boxes[this.selectedIndex];
                const sb = this.startBox;
                let nx = sb.x + dx;
                let ny = sb.y + dy;
                // Clamp
                nx = Math.max(0, Math.min(nx, CANVAS_WIDTH - sb.w));
                ny = Math.max(0, Math.min(ny, CANVAS_HEIGHT - sb.h));
                b.x = nx; b.y = ny;
            }
            else if (this.activeHandle) {
                const dx = x - this.startX;
                const dy = y - this.startY;
                const b = this.boxes[this.selectedIndex];
                const sb = this.startBox;
                let nx = sb.x, ny = sb.y, nw = sb.w, nh = sb.h;

                if (this.activeHandle.includes('e')) nw = sb.w + dx;
                if (this.activeHandle.includes('s')) nh = sb.h + dy;
                if (this.activeHandle.includes('w')) { nw = sb.w - dx; nx = sb.x + dx; }
                if (this.activeHandle.includes('n')) { nh = sb.h - dy; ny = sb.y + dy; }

                if (nw < 20) { if (this.activeHandle.includes('w')) nx = sb.x + sb.w - 20; nw = 20; }
                if (nh < 20) { if (this.activeHandle.includes('n')) ny = sb.y + sb.h - 20; nh = 20; }

                b.x = nx; b.y = ny; b.w = nw; b.h = nh;
            }
            requestAnimationFrame(() => this.updateDOM());
        }"""

# BoxEditor.commit (Simplified Scaling)
box_commit = r"""        commit() {
            if (this.boxes.length === 0) return;
            // Coords are already intrinsic. No scale needed (or scale=1).
            const parts = this.boxes.map(b => {
                const cx1 = Math.round(b.x);
                const cy1 = Math.round(b.y);
                const cx2 = Math.round(b.x + b.w);
                const cy2 = Math.round(b.y + b.h);
                return `${cx1},${cy1},${cx2},${cy2}`;
            });
            const val = parts.join('|') + ',' + Date.now();
            const url = new URL(parent.location.href);
            url.searchParams.set('box', val);
            url.searchParams.delete('tap'); url.searchParams.delete('poly_pts');
            throttledReplaceState(url);
            this.boxes = [];
            this.selectedIndex = -1;
            this.updateDOM();
            setTimeout(() => triggerRerun(), 500);
        }"""


# Polygon Pointer Down/Move
poly_pointer_down = r"""        onPointerDown(e) {
            const touchCount = e.pointerType === 'touch' ? window.activePointers.size : 0;
            if (window.isCanvasGesturing || touchCount > 1 || (Date.now() - (window.lastPinchTime || 0) < 600)) return;
            e.stopPropagation();

            if (this.isClosed) return;

            const rect = this.overlay.getBoundingClientRect();
            // 🔍 COORDINATE MAPPING
            const scale = rect.width / CANVAS_WIDTH;
            const x = (e.clientX - rect.left) / scale;
            const y = (e.clientY - rect.top) / scale;

            if (this.mode === 'freedraw') {
                this.points = [{ x, y }];
                this.isDrawing = true;
                this.render();
            } else {
                if (this.points.length > 2) {
                    const start = this.points[0];
                    const dx = x - start.x;
                    const dy = y - start.y;
                    if (Math.sqrt(dx * dx + dy * dy) < 20) { // 20px intrinsic tolerance
                        this.closePolygon();
                        return;
                    }
                }
                this.points.push({ x, y });
                this.render();
            }
        }"""

poly_pointer_move = r"""        onPointerMove(e) {
            if (this.mode === 'freedraw' && this.isDrawing) {
                const rect = this.overlay.getBoundingClientRect();
                const scale = rect.width / CANVAS_WIDTH;
                const x = (e.clientX - rect.left) / scale;
                const y = (e.clientY - rect.top) / scale;

                const last = this.points[this.points.length - 1];
                const dx = x - last.x;
                const dy = y - last.y;
                if (dx * dx + dy * dy > 5) { // 5px tolerance implicit
                    this.points.push({ x, y });
                    this.render();
                }
            }
        }"""

poly_commit = r"""        commit() {
            if (!this.isClosed || this.points.length < 3) return;
            // Coords are already intrinsic.
            const ptsStr = this.points.map(p => {
                return `${Math.round(p.x)},${Math.round(p.y)}`;
            }).join(';');
            
            const val = ptsStr + ',' + Date.now();
            const url = new URL(parent.location.href);
            url.searchParams.set('poly_pts', val);
            url.searchParams.delete('tap'); url.searchParams.delete('box');
            throttledReplaceState(url);

            this.points = [];
            this.isClosed = false;
            this.render();
            setTimeout(() => triggerRerun(), 500);
        }"""

# APPLY UPDATES
# 1. replace applyResponsiveScale
start_sig = "function applyResponsiveScale() {"
end_sig = "class PolygonEditor extends BaseEditor {"
s_idx = js_content.find(start_sig)
e_idx = js_content.find(end_sig)
if s_idx != -1 and e_idx != -1:
    js_content = js_content[:s_idx] + new_scale_logic + "\n\n    " + js_content[e_idx:]

# 2. replace BoxEditor methods
js_content = re.sub(r'onPointerDown\(e\) \{[\s\S]*?^        }', box_pointer_down, js_content, flags=re.MULTILINE)
js_content = re.sub(r'onPointerMove\(e\) \{[\s\S]*?^        }', box_pointer_move, js_content, flags=re.MULTILINE)
js_content = re.sub(r'commit\(\) \{[\s\S]*?^        }', box_commit, js_content, flags=re.MULTILINE)

# 3. replace PolygonEditor methods
# Need to be specific as function names overlap with BoxEditor
# We can find "class PolygonEditor" and then strict search after it.
poly_start = js_content.find("class PolygonEditor extends BaseEditor")
if poly_start != -1:
    post_poly = js_content[poly_start:]
    # Replace methods inside this block
    post_poly = re.sub(r'onPointerDown\(e\) \{[\s\S]*?^        }', poly_pointer_down, post_poly, flags=re.MULTILINE, count=1)
    post_poly = re.sub(r'onPointerMove\(e\) \{[\s\S]*?^        }', poly_pointer_move, post_poly, flags=re.MULTILINE, count=1)
    post_poly = re.sub(r'commit\(\) \{[\s\S]*?^        }', poly_commit, post_poly, flags=re.MULTILINE, count=1)
    
    js_content = js_content[:poly_start] + post_poly

# Write
with open(js_path, 'w', encoding='utf-8') as f:
    f.write(js_content)
    
print("Updated CanvasTouchHandler with Overlay Scaling and Coordinate Mapping.")
