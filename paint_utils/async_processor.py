import streamlit as st
from concurrent.futures import ThreadPoolExecutor
import time
import uuid
import logging
import numpy as np
import cv2

# Global executor
# We use 1 worker to ensure sequential processing of heavy AI tasks
executor = ThreadPoolExecutor(max_workers=1)

def run_async_sam_task(sam_engine, image, prompt_type, prompt_data, **kwargs):
    """
    Wrapper to run SAM generation in a background thread.
    Returns: (masks, scores, logs)
    """
    # Create a capture logger for this thread
    logs = []
    
    try:
        # 1. Set image (heavy operation)
        # Always call set_image; the engine handles skipping internally if it's the same image
        print(f"ASYNC WORKER: Setting image...")
        sam_engine.set_image(image)
        
        print(f"ASYNC WORKER: Starting {prompt_type} task...")
        
        # 2. Generate
        masks = None
        scores = None
        
        if prompt_type == "point":
             # Use the high-level generate_mask which handles selection logic
             mask = sam_engine.generate_mask(
                point_coords=prompt_data.get('point_coords'),
                level=prompt_data.get('level', 0),
                is_wall_only=prompt_data.get('is_wall_only', False),
                is_wall_click=prompt_data.get('is_wall_click', False)
             )
        
        elif prompt_type == "box":
             mask = sam_engine.generate_mask(
                box_coords=prompt_data.get('box_coords'),
                level=prompt_data.get('level', 0),
                is_wall_only=prompt_data.get('is_wall_only', False),
                is_wall_click=prompt_data.get('is_wall_click', False)
             )
             
        elif prompt_type == "multi_box":
             accumulated = None
             import numpy as np
             for box in prompt_data.get('boxes', []):
                 m = sam_engine.generate_mask(
                    box_coords=box,
                    level=prompt_data.get('level', 0),
                    is_wall_only=prompt_data.get('is_wall_only', False),
                    is_wall_click=prompt_data.get('is_wall_click', False)
                 )
                 if m is not None:
                     if accumulated is None: accumulated = m
                     else: accumulated = np.logical_or(accumulated, m)
             mask = accumulated
        
        return {"status": "success", "mask": mask}
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

def submit_sam_task(sam_engine, image, prompt_type, prompt_data):
    """Submits a SAM task to the executor."""
    future = executor.submit(run_async_sam_task, sam_engine, image, prompt_type, prompt_data)
    
    st.session_state["async_task"] = {
        "id": str(uuid.uuid4()),
        "future": future,
        "type": prompt_type,
        "start_time": time.time()
    }
    
    # Trigger immediate rerun to show spinner
    from paint_utils.state_manager import preserve_sidebar_state
    preserve_sidebar_state()
    st.rerun()

def check_async_task():
    """
    Checks the status of the running async task.
    Returns: 
       None if no task
       "running" if running
       result_dict if completed
    """
    task = st.session_state.get("async_task")
    if not task:
        return None
        
    future = task["future"]
    
    if future.done():
        # Task completed!
        try:
            result = future.result()
            # Cleanup
            del st.session_state["async_task"]
            return result
        except Exception as e:
            del st.session_state["async_task"]
            return {"status": "error", "message": str(e)}
    else:
        return "running"
