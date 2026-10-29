import streamlit as st
from .ui_components import TOOL_MAPPING
from .state_manager import cb_undo, cb_redo, cb_apply_pending, cb_cancel_pending, preserve_sidebar_state

def render_mobile_toolbar():
    """
    Renders a sticky bottom toolbar designed for mobile users.
    Only visible on small screens via CSS media queries.
    """
    if st.session_state.get("image") is None:
        return
    
    # 1. CSS for Sticky Footer
    st.markdown("""
    <style>
    /* Default: Hide the specific Streamlit container that holds our toolbar on Desktop */
    /* We'll assign a specific class to the container via a hack or just assume logical placement */
    
    /* Force the specific container (identified by having these specific buttons) to be sticky bottom */
    div[data-testid="stVerticalBlock"] > div:has(div[data-testid="stButton"]) {
        /* This selector is tricky in generic Streamlit. 
           Instead, we'll wrap the toolbar in a container with a custom class using the updated layout options. 
           But since we can't easily add classes to containers, we rely on 'bottom' placement. */
    }

    /* Better approach: Fixed position container overlay */
    .mobile-toolbar-wrapper {
        position: fixed;
        bottom: 0;
        left: 0;
        width: 100%;
        background: rgba(255, 255, 255, 0.95);
        backdrop-filter: blur(10px);
        border-top: 1px solid #ddd;
        padding: 10px 10px 20px 10px; /* Extra padding for safe area */
        z-index: 99999;
        display: flex;
        justify-content: space-around;
        align-items: center;
        box-shadow: 0 -2px 10px rgba(0,0,0,0.1);
        transition: transform 0.3s ease;
    }
    
    /* Hide on Desktop */
    @media (min-width: 800px) {
        .mobile-toolbar-wrapper {
            display: none !important;
        }
    }
    
    .mobile-btn {
        background: none;
        border: none;
        font-size: 24px;
        cursor: pointer;
        padding: 5px;
        border-radius: 10px;
    }
    .mobile-btn:active {
        background: #f0f0f0;
    }
    .mobile-btn.active {
        background: #ffe5e5;
        color: #ff4b4b;
    }
    </style>
    """, unsafe_allow_html=True)

    # 2. Logic to handle clicks (using standard Streamlit buttons in a bottom layout)
    # Since we can't easily put standard widgets into a custom HTML div, 
    # we will render this as a standard Streamlit columns row at the very bottom of the script,
    # and use CSS to force 'position: fixed' on THAT specific block.
    
    # We use a unique key for the container to target it? 
    # Streamlit 1.30+ allows `st.container(height=...)`.
    # We will use `st.container()` and then some JS to move it to the `body`.
    
    # Simpler: Just rendering it at the bottom of app.py is usually "good enough" for mobile 
    # if we just want it to be the last thing. 
    # But "Sticky" is requested.
    
    # Let's try the "Floating Action Button" via HTML trick that triggers internal logic?
    # No, that's brittle.
    
    # Let's use the new `st.popover` or similar? No.
    
    # BEST PATH: Render standard buttons, but inject CSS to target this specific group div
    # and make it fixed bottom.
    
    m_container = st.container()
    with m_container:
        st.markdown('<div class="mobile-toolbar-target"></div>', unsafe_allow_html=True)
        # We need to wrap these buttons in something we can target.
        # Javascript can find this marker and apply styles to the parent.
        
        cols = st.columns([1, 1, 1, 1, 1])
        
        current_tool = st.session_state.get("selection_tool", "")
        
        with cols[0]:
            # Tool Switcher
            if st.button("👆", key="mob_tool_click", help="Point Click", use_container_width=True):
                st.session_state["selection_tool"] = TOOL_MAPPING["👆"]
                preserve_sidebar_state()
                st.rerun()
                
        with cols[1]:
            if st.button("✨", key="mob_tool_box", help="Box/Object", use_container_width=True):
                st.session_state["selection_tool"] = TOOL_MAPPING["✨"]
                preserve_sidebar_state()
                st.rerun()
                
        with cols[2]:
             if st.button("✏️", key="mob_tool_brush", help="Brush", use_container_width=True):
                st.session_state["selection_tool"] = TOOL_MAPPING["✏️"]
                preserve_sidebar_state()
                st.rerun()

        with cols[3]:
            # Undo
            if st.button("↩️", key="mob_undo", use_container_width=True):
                cb_undo()
                preserve_sidebar_state()
                st.rerun()
                
        with cols[4]:
            # Apply
             if st.button("✅", key="mob_apply", type="primary", use_container_width=True):
                 cb_apply_pending()
                 preserve_sidebar_state()
                 st.rerun()

    # CSS to force this container to bottom
    st.markdown("""
    <script>
    // Find the container with our marker
    const marker = window.parent.document.querySelector('.mobile-toolbar-target');
    if (marker) {
        // Find the parent vertical block
        const block = marker.closest('[data-testid="stVerticalBlock"]');
        if (block) {
            block.style.position = 'fixed';
            block.style.bottom = '0';
            block.style.left = '0';
            block.style.width = '100%';
            block.style.zIndex = '999999';
            block.style.background = 'white';
            block.style.borderTop = '1px solid #ccc';
            block.style.padding = '10px';
            block.style.display = 'block'; // Default
            
            // Basic responsive toggle
            if (window.parent.innerWidth > 800) {
                block.style.display = 'none';
            }
        }
    }
    </script>
    """, unsafe_allow_html=True)
