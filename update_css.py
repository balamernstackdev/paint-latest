
import os

path = r'd:\latest paint\paint_utils\ui_components.py'

with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Inject Meta Viewport Tag for Zoom
# We can inject this via st.markdown if not present, but better to put it in the style block or verify.
# Streamlit usually blocks meta tag injection effectively unless using st.html.
# But let's focus on CSS.

# 2. Fix CSS: touch-action: none (so JS can handle pinch)
# Find previous edits and revert/fix.
# We want strict blocking of browser behavior on canvas to allow our JS to work.

block_check = 'iframe[title="streamlit_drawable_canvas.st_canvas"],'
if block_check in content:
    # We will replace the entire block with a robust version using regex or strict string replace
    pass

# Force replace touch-action pinch-zoom with none
content = content.replace('touch-action: pinch-zoom !important;', 'touch-action: none !important;')

# Ensure pointer-events: auto
if 'pointer-events: auto !important;' not in content:
    content = content.replace('user-select: none !important;', 'user-select: none !important;\n            pointer-events: auto !important;')

# Global Context Menu Killer
if '/* 🛑 GLOBAL CONTEXT MENU KILLER */' not in content:
    content = content.replace('.stApp {{', '.stApp {{\n            /* 🛑 GLOBAL CONTEXT MENU KILLER */\n            -webkit-touch-callout: none !important;')

# Save
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Updated CSS successfully")
