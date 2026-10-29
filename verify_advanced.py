import sys
from unittest.mock import MagicMock
import numpy as np
import cv2

# Mock streamlit before any imports that use it
mock_st = MagicMock()
mock_st.session_state = {
    "masks": [],
    "picked_color": "#FF0000",
    "selection_op": "Add",
    "render_id": 0,
    "canvas_id": 0,
    "pending_boxes": []
}
sys.modules["streamlit"] = mock_st

# Mock performance utils
mock_perf = MagicMock()
mock_perf.should_trigger_cleanup.return_value = False
sys.modules["paint_utils.performance"] = mock_perf

# Now we can import the modules to test
from paint_utils.ui_components import process_lasso_path
from paint_utils.state_manager import cb_apply_pending

def test_advanced_selection():
    print("Running Advanced Selection Logic Tests...")
    
    # 1. Test Lasso Path Processing
    h, w = 100, 100
    path = [["M", 10, 10], ["L", 90, 10], ["L", 90, 90], ["L", 10, 90], ["Z"]]
    mask = process_lasso_path(path, w, h)
    
    assert mask.shape == (100, 100)
    assert mask[50, 50] == True
    assert mask[5, 5] == False
    print("✅ Lasso path to mask conversion successful")
    
    # 2. Test Add Operation
    mock_st.session_state["pending_selection"] = {"mask": mask}
    cb_apply_pending()
    assert len(mock_st.session_state["masks"]) == 1
    assert "refinement" in mock_st.session_state["masks"][0]
    print("✅ Mask addition successful (with refinement state)")
    
    # 3. Test Subtract Operation
    sub_path = [["M", 40, 40], ["L", 60, 40], ["L", 60, 60], ["L", 40, 60], ["Z"]]
    sub_mask = process_lasso_path(sub_path, w, h)
    
    mock_st.session_state["selection_op"] = "Subtract"
    mock_st.session_state["pending_selection"] = {"mask": sub_mask}
    cb_apply_pending()
    
    assert len(mock_st.session_state["masks"]) == 1
    assert mock_st.session_state["masks"][0]["mask"][50, 50] == False
    assert mock_st.session_state["masks"][0]["mask"][20, 20] == True
    print("✅ Mask subtraction successful")
    
    print("\nALL ADVANCED SELECTION TESTS PASSED!")

if __name__ == "__main__":
    try:
        test_advanced_selection()
    except AssertionError as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
