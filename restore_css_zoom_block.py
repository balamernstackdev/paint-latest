
import os
import re

ui_path = r'd:\latest paint\paint_utils\ui_components.py'

with open(ui_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Enable Custom JS Zoom by blocking browser zoom on the canvas (touch-action: none)
# The user's checklist says "touch-action: auto" if focusing on browser zoom, 
# but "touch-action: none" is standard for Custom JS Zoom (Best Solution).
# I will use "none" to allow full JS control.

if 'touch-action: pan-x pan-y pinch-zoom !important;' in content:
    content = content.replace('touch-action: pan-x pan-y pinch-zoom !important;', 'touch-action: none !important;')

if 'width=device-width, initial-scale=1.0, maximum-scale=5.0, user-scalable=yes' not in content:
    # It might be in app.py, but let's check ui_components.py isn't setting something contradictory?
    # ui_components.py style block has "html, body... touch-action: manipulation".
    # I should ensure that's not blocking.
    pass

with open(ui_path, 'w', encoding='utf-8') as f:
    f.write(content)
