
import os
import re

js_path = r'd:\latest paint\assets\js\canvas_touch_handler.js'

with open(js_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Define the clean handlePinch function
clean_handle_pinch = r"""    // 🤏 GLOBAL PINCH HANDLER
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
                if (newZoom > 5.0) newZoom = 5.0;
                window.userZoomLevel = newZoom;
                
                // PAN
                if (window.lastPinchCenter) {
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

# Use regex to find the existing handlePinch block and replace it.
# We look for "const handlePinch = (e) => {" and match until the end of the logical block.
# Since the file has syntax errors now (extra braces), simple block matching might be hard.
# But we can try to match from "const handlePinch" up to just before "try {" which usually follows it in my previous structure?
# Let's check the file content again... yes, "try {" starts on line 110.

# We will replace from "const handlePinch" down to just before "// Attach to parent".
pattern = re.compile(r'// 🤏 GLOBAL PINCH HANDLER\s*const handlePinch = \(e\) => \{[\s\S]*?\}\s*};', re.MULTILINE)

# The current file has:
# // 🤏 GLOBAL PINCH HANDLER
# const handlePinch = (e) => {
#    ...
# };

# And we know the next section starts with "// Attach to parent" (although line 109 says "// Attach to parent to catch...").
# Let's be safer: Replace the text between "// 🤏 GLOBAL PINCH HANDLER" and "// Attach to parent"
start_marker = "// 🤏 GLOBAL PINCH HANDLER"
end_marker = "// Attach to parent"

if start_marker in content and end_marker in content:
    start_idx = content.find(start_marker)
    end_idx = content.find(end_marker)
    
    new_content = content[:start_idx] + clean_handle_pinch + "\n\n    " + content[end_idx:]
    
    with open(js_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("Fixed handlePinch syntax error.")
else:
    print("Could not find markers to replace handlePinch.")

