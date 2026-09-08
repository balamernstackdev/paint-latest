import numpy as np
import cv2

def process_lasso_path(path_data, w, h):
    """Convert Fabric.js path data to a binary mask."""
    mask = np.zeros((h, w), dtype=np.uint8)
    points = []
    for cmd in path_data:
        if cmd[0] in ["M", "L"]:
            points.append([cmd[1], cmd[2]])
        elif cmd[0] == "Q": # Quadratic curve
            points.append([cmd[3], cmd[4]])
    
    if len(points) > 2:
        pts = np.array(points, np.int32)
        cv2.fillPoly(mask, [pts], 255)
    return mask > 0

def test_logic():
    print("Testing Lasso & Subtraction Logic...")
    
    # 1. Test Lasso Path Processing
    h, w = 100, 100
    path = [["M", 10, 10], ["L", 90, 10], ["L", 90, 90], ["L", 10, 90], ["Z"]]
    mask = process_lasso_path(path, w, h)
    
    assert mask.shape == (100, 100)
    assert mask[50, 50] == True
    assert mask[5, 5] == False
    print("✅ Lasso path to mask conversion successful")
    
    # 2. Test Subtraction Logic
    # Larger mask (base)
    base_mask = mask.copy()
    
    # Smaller mask (to subtract)
    sub_path = [["M", 40, 40], ["L", 60, 40], ["L", 60, 60], ["L", 40, 60], ["Z"]]
    sub_mask = process_lasso_path(sub_path, w, h)
    
    # Logic: Base &= ~Sub
    base_mask &= ~sub_mask
    
    assert base_mask[50, 50] == False
    assert base_mask[20, 20] == True
    print("✅ Mask subtraction logic successful")
    
    # 3. Test Dilation/Erosion Logic
    ref = 2 # Expand
    kernel_size = abs(ref) * 2 + 1
    kernel = np.ones((kernel_size, kernel_size), np.uint8)
    # Original mask had 10-90 (81 pixel side)
    # Dilation with 5x5 kernel should expand it
    dilated = cv2.dilate(mask.astype(np.uint8)*255, kernel, iterations=1) > 127
    assert dilated[9, 9] == True # Was False (10,10 was edge)
    print("✅ Mask expansion (dilation) logic successful")

    ref = -2 # Contract
    contracted = cv2.erode(mask.astype(np.uint8)*255, kernel, iterations=1) > 127
    assert contracted[11, 11] == False # Was True
    print("✅ Mask contraction (erosion) logic successful")
    
    print("\nALL LOGIC TESTS PASSED!")

if __name__ == "__main__":
    test_logic()
