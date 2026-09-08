
import streamlit as st
import numpy as np
from PIL import Image
from streamlit_drawable_canvas import st_canvas
import base64
from io import BytesIO

st.set_page_config(page_title="Canvas Debugger")

st.title("Canvas Debugger")

# Create a simple red image
img = Image.new('RGB', (200, 200), color = 'red')
st.image(img, caption="Expected Background (Native st.image)")

st.write("Canvas below (Should show the red square):")
try:
    canvas_result = st_canvas(
        fill_color="rgba(255, 165, 0, 0.3)",
        stroke_width=3,
        stroke_color="#000000",
        background_image=img,
        update_streamlit=True,
        height=200,
        width=200,
        drawing_mode="rect",
        key="canvas",
    )
    if canvas_result.image_data is not None:
        st.write("Canvas is interactive.")
except Exception as e:
    st.error(f"Canvas failed: {e}")
