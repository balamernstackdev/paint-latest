import streamlit as st
import numpy as np
try:
    from streamlit.elements.image import image_to_url
    print("Found in streamlit.elements.image")
except ImportError:
    try:
        from streamlit.image_utils import image_to_url
        print("Found in streamlit.image_utils")
    except ImportError:
        print("Not found")

# Test signature
if 'image_to_url' in locals():
    print("Testing image_to_url...")
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    try:
        # Signature: image, width, clamp, channels, output_format, image_id
        url = image_to_url(img, -1, True, "RGB", "PNG", "test_id")
        print(f"Success: {url[:50]}...")
    except Exception as e:
        print(f"Failed: {e}")
