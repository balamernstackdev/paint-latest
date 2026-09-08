
import cv2
import numpy as np

def test_mask_fix():
    h, w = 100, 100
    
    # Mocks
    mask_sam = np.zeros((1, h, w), dtype=bool) # (1, 100, 100)
    
    # Proposed Fix Logic
    mask = mask_sam
    if mask.ndim == 3:
        if mask.shape[0] == 1:
            mask = mask[0]
        elif mask.shape[-1] == 1:
            mask = mask[..., 0]
            
    print(f"Mask shape after squeeze: {mask.shape}")
    
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
    else:
        mask = mask.astype(np.uint8)
        
    print(f"Final mask shape: {mask.shape}")
    
    # Test weird shape (50, 80)
    mask_wrong = np.zeros((1, 50, 80), dtype=bool)
    mask = mask_wrong
    if mask.ndim == 3:
        if mask.shape[0] == 1:
            mask = mask[0]
        elif mask.shape[-1] == 1:
            mask = mask[..., 0]
            
    if mask.shape[:2] != (h, w):
        mask = cv2.resize(mask.astype(np.uint8), (w, h), interpolation=cv2.INTER_NEAREST)
        
    print(f"Resized mask shape: {mask.shape}")

if __name__ == "__main__":
    test_mask_fix()
