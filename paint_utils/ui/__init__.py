"""
UI Components Package - Modularized for better maintainability.

This package contains all UI-related components for the AI Paint Visualizer.
Currently delegates to original ui_components.py for full functionality while
the modular structure is being finalized.

Package structure:
- canvas.py: Canvas wrapper with caching (READY)
- sidebar.py: Sidebar controls (READY with full docstrings)
- fragments.py: Fragment components (READY with docstrings)
- styles.py: CSS styling (delegates to original)

For backward compatibility, all exports remain available.
"""

# Delegate to original ui_components for full functionality
# This maintains stability while modular structure is finalized
from ..ui_components import (
    st_canvas,
    setup_styles,
    sidebar_paint_fragment,
    render_zoom_controls,
    render_editor_fragment,
    sidebar_toggle_fragment,
    render_sidebar
)

__all__ = [
    'st_canvas',
    'setup_styles',
    'sidebar_paint_fragment',
    'render_zoom_controls',
    'render_editor_fragment',
    'sidebar_toggle_fragment',
    'render_sidebar'
]
