import streamlit as st
from io import BytesIO
import base64
from PIL import Image
import numpy as np
from app_config.constants import PerformanceConfig

@st.cache_data(show_spinner=False, max_entries=PerformanceConfig.IMAGE_ENCODING_CACHE_SIZE)
def _cached_image_to_url(_image, width, use_column_width, clamp, format, image_id):
    """Internal cached encoder that avoids hashing the heavy image data."""
    try:
        # Handle both numpy arrays and PIL Images
        if isinstance(_image, np.ndarray):
            img = Image.fromarray(_image)
        elif isinstance(_image, Image.Image):
            img = _image
        else:
            img = _image
            
        if img.mode != "RGB": 
            img = img.convert("RGB")
        
        # PERFORMANCE: Resize if width is provided to reduce payload
        if width is not None and width > 0:
             w_percent = (width / float(img.size[0]))
             h_size = int((float(img.size[1]) * float(w_percent)))
             img = img.resize((width, h_size), Image.NEAREST)
             
        buf = BytesIO()
        # PERFORMANCE: JPEG compression is sufficient for background reference and much lighter
        img.save(buf, format="JPEG", quality=PerformanceConfig.BACKGROUND_IMAGE_QUALITY)
        return f"data:image/jpeg;base64,{base64.b64encode(buf.getvalue()).decode()}"
    except Exception as e:
        return ""

def image_to_url_patch(image, width=0, use_column_width=False, clamp=False, format="JPEG", image_id=""):
    """Standard signature wrapper for Streamlit internal image utility."""
    return _cached_image_to_url(image, width, use_column_width, clamp, format, image_id)
