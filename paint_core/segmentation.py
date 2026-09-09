import numpy as np
import torch
import cv2
import logging
from mobile_sam import sam_model_registry, SamPredictor
from app_config.constants import SegmentationConfig

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SegmentationEngine:
    def __init__(self, checkpoint_path=None, model_type="vit_b", device=None, model_instance=None):
        """
        Initialize the SAM model.
        Args:
            checkpoint_path: Path to weights (if loading new).
            model_type: SAM architecture type.
            device: 'cuda' or 'cpu'.
            model_instance: Pre-loaded sam_model_registry instance (optional).
        """
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device
            
        if model_instance is not None:
             self.sam = model_instance
        elif checkpoint_path:
             # OPTIMIZATION: Force vit_t if filename suggests MobileSAM
             if "mobile_sam" in checkpoint_path and model_type != "vit_t":
                 logger.warning(f"Model type override: Detected MobileSAM weights but requested {model_type}. Forcing 'vit_t'.")
                 model_type = "vit_t"
                 
             logger.info(f"Loading SAM model ({model_type}) on {self.device}...")
             self.sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
             self.sam.to(device=self.device)
        else:
             raise ValueError("Either checkpoint_path or model_instance must be provided.")

        self.predictor = SamPredictor(self.sam)
        self.is_image_set = False

    def set_image(self, image_rgb):
        """
        Process the image and compute embeddings.
        Args:
            image_rgb: NumPy array (H, W, 3) in RGB format.
        """
        # OPTIMIZATION: Check if image is already set to avoid expensive re-encoding
        if self.is_image_set and hasattr(self, 'image_rgb') and self.image_rgb is not None:
            if image_rgb.shape == self.image_rgb.shape and np.array_equal(image_rgb, self.image_rgb):
                logger.info("Image already set. Skipping embedding computation.")
                print("DEBUG: SAM Engine - Image already set.")
                return

        logger.info("Computing image embeddings...")
        print(f"DEBUG: SAM Engine {id(self)} - Computing embeddings...")
        self.predictor.set_image(image_rgb)
        self.is_image_set = True
        self.image_rgb = image_rgb
        
        # --- PRE-COMPUTE FEATURES FOR FASTER CLICKS ---
        # 1. Grayscale
        self.image_gray = cv2.cvtColor(image_rgb, cv2.COLOR_RGB2GRAY)
        self.image_u16 = image_rgb.astype(np.uint16)
        
        # 2. Gaussian Blur (for small objects/edge detection)
        k_size = SegmentationConfig.GAUSSIAN_KERNEL_SIZE
        self.image_blurred = cv2.GaussianBlur(self.image_gray, k_size, 0)
        
        # 3. Laplacian Edges (base)
        edges = cv2.Laplacian(self.image_blurred, cv2.CV_16S, ksize=3)
        self.image_edges_map = cv2.convertScaleAbs(edges)
        
        print(f"DEBUG: SAM Engine {id(self)} - is_image_set = True ✅ (Features Pre-computed)")
        logger.info("Embeddings and features computed.")

    def generate_mask(self, point_coords=None, point_labels=None, box_coords=None, level=None, is_wall_only=False, cleanup=True, is_wall_click=False):
        print(f"DEBUG: Entering generate_mask v4.3.1 (UUID: {id(self)})")
        is_small_object = False 
        area_ratio = 0.0        
        aspect_ratio = 0.0      
        if self.predictor is None:
            return None
        """
        Generate a mask for a given point or box.
        Args:
            point_coords: List of [x, y] or NumPy array.
            point_labels: List of labels (1 for foreground, 0 for background).
            box_coords: [x1, y1, x2, y2]
            level: int (0, 1, 2) or None. 
                   0=Fine Details, 1=Sub-segment, 2=Whole Object. 
                   If None, auto-selects highest score.
            is_wall_only: bool. If True, uses stricter wall-specific thresholds.
            cleanup: bool. If True, removes disconnected components to prevent leaks.
        """
        if not self.is_image_set:
            raise RuntimeError("Image not set. Call set_image() first.")

        # Prepare inputs
        sam_point_coords = None
        sam_point_labels = None
        sam_box = None

        if point_coords is not None:
            # Check input structure
            # Case 1: Single point [x, y] -> wrap to [[x, y]]
            # Case 2: List of points [[x, y], ...] -> use as is
            
            arr = np.array(point_coords)
            if arr.ndim == 1:
                sam_point_coords = np.array([point_coords])
            else:
                 sam_point_coords = arr
            
            if point_labels is None:
                # We have N points, so we need N labels
                sam_point_labels = np.array([1] * len(sam_point_coords))
            else:
                sam_point_labels = np.array(point_labels)
        
        if box_coords is not None:
            sam_box = np.array(box_coords)

        with torch.inference_mode():
            masks, scores, logits = self.predictor.predict(
                point_coords=sam_point_coords,
                point_labels=sam_point_labels,
                box=sam_box,
                multimask_output=True # Generate multiple masks and choose best
            )

        # Handle batch dimension if present (MobileSAM/TinySAM might return (1, 3, H, W))
        if len(masks.shape) == 4:
            masks = masks[0]
        if len(scores.shape) == 2:
            scores = scores[0]

        h, w = masks[0].shape
        image_area = h * w
        
        ref_x, ref_y = None, None
        if point_coords is not None and len(point_coords) > 0:
            pos_indices = np.where(sam_point_labels == 1)[0]
            if len(pos_indices) > 0:
                idx = pos_indices[-1]
                ref_x, ref_y = int(sam_point_coords[idx][0]), int(sam_point_coords[idx][1])
        elif box_coords is not None:
            ref_x = int((box_coords[0] + box_coords[2]) / 2)
            ref_y = int((box_coords[1] + box_coords[3]) / 2)
            
        best_candidate_idx = -1
        best_candidate_score = -9999
        best_mask = None
        
        # 1. CANDIDATE VALIDATION
        for idx in range(3):
            mask_candidate = masks[idx]
            mask_uint8_cand = (mask_candidate * 255).astype(np.uint8)
            mask_area = np.sum(mask_candidate)
            area_ratio = mask_area / image_area
            
            # Ensure click containment
            click_containment = 1.0
            if ref_x is not None and ref_y is not None:
                ix = max(0, min(ref_x, w - 1))
                iy = max(0, min(ref_y, h - 1))
                if mask_candidate[iy, ix] == 0:
                    click_containment = 0.0
            
            # Edge conflict (how much of the mask boundary sits on strong edges)
            kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
            mask_dilated = cv2.dilate(mask_uint8_cand, kernel_dilate)
            mask_eroded = cv2.erode(mask_uint8_cand, kernel_dilate)
            boundary = mask_dilated - mask_eroded
            
            # Average edge energy on boundary
            boundary_pixels = np.sum(boundary > 0)
            edge_conflict = 0.0
            if boundary_pixels > 0:
                edge_sum = np.sum(self.image_edges_map[boundary > 0])
                edge_conflict = edge_sum / (boundary_pixels * 255.0)
                
            # Score formula
            final_score = (scores[idx] * 40.0) - (edge_conflict * 100.0)
            
            reason = ""
            if click_containment == 0.0:
                reason = "REJECTED: Does not contain click"
                final_score = -9999
            elif area_ratio < 0.005:
                reason = "REJECTED: Too small (<0.5%)"
                final_score = -9999
            elif area_ratio > 0.30 and not box_coords:
                reason = "REJECTED: Oversized (>30%)"
                final_score = -9999
            
            print(f"Candidate {idx}:\narea={area_ratio*100:.1f}%\nSAM={scores[idx]:.2f}\nclick={click_containment:.2f}\nedgeConflict={edge_conflict:.2f}\nscore={final_score:.2f}")
            if reason:
                print(reason)
                
            if final_score > best_candidate_score:
                best_candidate_score = final_score
                best_candidate_idx = idx
                best_mask = mask_candidate
                
        if best_mask is None:
            # Fallback if all rejected
            best_candidate_idx = np.argmax(scores)
            best_mask = masks[best_candidate_idx]
            print(f"All candidates rejected. Falling back to Candidate {best_candidate_idx}")
            
        print(f"\nSelected candidate {best_candidate_idx}")
        
        if cleanup:
            mask_uint8 = (best_mask * 255).astype(np.uint8)
            orig_area_ratio = np.sum(best_mask) / image_area
            print(f"Original mask area: {orig_area_ratio*100:.1f}%")
            
            # 2. CONNECTED COMPONENT FILTERING
            if ref_x is not None and ref_y is not None:
                ix = int(max(0, min(ref_x, w - 1)))
                iy = int(max(0, min(ref_y, h - 1)))
                
                num_labels, labels_im, stats, centroids = cv2.connectedComponentsWithStats(mask_uint8, connectivity=8)
                target_label = labels_im[iy, ix]
                
                if target_label != 0:
                    best_mask = (labels_im == target_label)
                else:
                    # Fallback to largest
                    max_area = 0
                    max_label = 1
                    for i in range(1, num_labels):
                        if stats[i, cv2.CC_STAT_AREA] > max_area:
                            max_area = stats[i, cv2.CC_STAT_AREA]
                            max_label = i
                    best_mask = (labels_im == max_label)
                    
            cc_area_ratio = np.sum(best_mask) / image_area
            print(f"Connected component: {cc_area_ratio*100:.1f}%")
            
            mask_uint8 = (best_mask * 255).astype(np.uint8)
            
            # 3. SELECTIVE HOLE FILLING
            # Fill small holes inside the mask (e.g. shadows under overhangs or small obstacles)
            cnts, hierarchy = cv2.findContours(mask_uint8, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
            out_mask = np.copy(mask_uint8)
            if hierarchy is not None:
                hierarchy = hierarchy[0]
                for i, c in enumerate(cnts):
                    parent_idx = hierarchy[i][3]
                    if parent_idx != -1:  # It's an internal hole
                        area = cv2.contourArea(c)
                        # Fill if hole is smaller than 0.5% of the image (prevent swallowing large windows)
                        if area < (h * w * 0.005):
                            cv2.drawContours(out_mask, [c], -1, 255, thickness=-1)
            mask_uint8 = out_mask

            # 4. ARCHITECTURAL BOUNDARY REFINEMENT & MORPHOLOGY
            # Instead of a destructive bitwise AND that creates black lines, we use the edge barrier 
            # merely to stop morphological dilation/closing from expanding over edges.
            _, edge_barrier = cv2.threshold(self.image_edges_map, SegmentationConfig.EDGE_THRESHOLD_WALL_MODE if is_wall_only else 35, 255, cv2.THRESH_BINARY_INV)
            
            # Dilate to snap to edges, but don't cross the barrier
            kernel_snap = np.ones((5, 5), np.uint8)
            mask_dilated = cv2.dilate(mask_uint8, kernel_snap)
            mask_refined = (mask_dilated & edge_barrier) | mask_uint8
            
            # Conservative erosion to pull back slightly from edges
            erosion_kernel = np.ones((3, 3), np.uint8)
            mask_refined = cv2.erode(mask_refined, erosion_kernel, iterations=1)
            
            # Minor noise cleanup
            open_close_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
            mask_refined = cv2.morphologyEx(mask_refined, cv2.MORPH_OPEN, open_close_kernel)
            mask_refined = cv2.morphologyEx(mask_refined, cv2.MORPH_CLOSE, open_close_kernel)
            
            # Ensure click point is preserved
            if ref_x is not None and ref_y is not None:
                cv2.circle(mask_refined, (ref_x, ref_y), 2, 255, -1)
                
            best_mask = (mask_refined > 0)
            final_area_ratio = np.sum(best_mask) / image_area
            print(f"Refined mask area: {final_area_ratio*100:.1f}%\n")
            
        return best_mask

    def _filter_small_components(self, mask, click_x, click_y, target_label, labels_im, stats, centroids):
        """
        Internal helper to remove disconnected components that are too small or too far from click.
        Helps prevent painting unintended pots/decorations when walls are selected.
        """
        num_labels = len(stats)
        h, w = mask.shape
        
        # Get clicked component stats
        main_area = stats[target_label, cv2.CC_STAT_AREA]
        
        # Build cleaned mask
        clean_mask = np.zeros((h, w), dtype=np.uint8)
        
        for i in range(1, num_labels):
            component_area = stats[i, cv2.CC_STAT_AREA]
            cx, cy = centroids[i]
            
            # Distance from click
            dist = np.sqrt((cx - click_x)**2 + (cy - click_y)**2)
            
            # Keep component if:
            # 1. It's exactly the clicked component
            # 2. OR it's a reasonably large piece (>=10% of main) AND close enough
            if i == target_label:
                clean_mask[labels_im == i] = 1
            elif (component_area >= main_area * SegmentationConfig.MIN_COMPONENT_RATIO and 
                  dist < SegmentationConfig.MAX_COMPONENT_DISTANCE):
                clean_mask[labels_im == i] = 1
        
        return clean_mask.astype(bool)

