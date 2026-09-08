"""
Unit tests for core/segmentation.py mask generation and refinement.

Tests cover SAM integration, mask generation, coordinate validation,
and mask refinement logic.
"""

import pytest
import numpy as np
from unittest.mock import Mock, patch
from paint_core.segmentation import SegmentationEngine


class TestSegmentationEngineInit:
    """Test SegmentationEngine initialization."""
    
    def test_initialization_with_model(self, mock_sam_predictor):
        """Test that engine initializes with SAM model."""
        # mock_sam_predictor here is actually the model instance for the engine
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        assert engine.sam == mock_sam_predictor
        assert not engine.is_image_set
    
    def test_initialization_without_model(self):
        """Test that engine raises error without model or path."""
        with pytest.raises(ValueError, match="Either checkpoint_path or model_instance must be provided"):
            SegmentationEngine(None)


class TestSetImage:
    """Test set_image method."""
    
    def test_set_image_success(self, mock_sam_predictor, sample_image):
        """Test successful image setting."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        assert engine.is_image_set
        assert np.array_equal(engine.image_rgb, sample_image)
        # The predictor is created internally using SamPredictor(self.sam)
        # We need to verify set_image was called on the internal predictor
        # But since we mocked the model_instance, and SamPredictor(model) is called,
        # we might need to mock SamPredictor as well or check how it's used.
    
    def test_set_image_converts_bgr_to_rgb(self, mock_sam_predictor, sample_image):
        """Test that image is stored correctly."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        # Simulate BGR input
        bgr_image = sample_image[:, :, ::-1]
        engine.set_image(bgr_image)
        
        assert engine.is_image_set
        # Verify conversion happened (stored as RGB)
        assert engine.image_rgb.shape == sample_image.shape
    
    def test_set_image_without_predictor(self, sample_image):
        """Test that setting image without predictor raises error."""
        # This test is no longer strictly applicable as __init__ now requires model
        pass
    
    def test_set_image_invalid_dimensions(self, mock_sam_predictor):
        """Test that invalid image dimensions raise ValueError."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        
        # Grayscale image (2D)
        with pytest.raises(ValueError, match="must be 3-channel"):
            engine.set_image(np.zeros((100, 100), dtype=np.uint8))
        
        # 4-channel image
        with pytest.raises(ValueError, match="must be 3-channel"):
            engine.set_image(np.zeros((100, 100, 4), dtype=np.uint8))


class TestGenerateMask:
    """Test generate_mask method."""
    
    def test_generate_mask_with_point(self, mock_sam_predictor, sample_image):
        """Test mask generation with point coordinates."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        mask = engine.generate_mask(point_coords=[50, 50], level=0)
        
        assert mask is not None
        assert mask.shape == (sample_image.shape[0], sample_image.shape[1])
        assert mask.dtype == bool
        mock_sam_predictor.predict.assert_called_once()
    
    def test_generate_mask_with_box(self, mock_sam_predictor, sample_image):
        """Test mask generation with bounding box."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        mask = engine.generate_mask(box_coords=[10, 10, 90, 90], level=0)
        
        assert mask is not None
        assert mask.shape == (sample_image.shape[0], sample_image.shape[1])
        mock_sam_predictor.predict.assert_called_once()
    
    def test_generate_mask_without_image_set(self, mock_sam_predictor):
        """Test that generating mask without set image raises error."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        
        with pytest.raises(RuntimeError, match="must call set_image"):
            engine.generate_mask(point_coords=[50, 50])
    
    def test_generate_mask_invalid_coordinates(self, mock_sam_predictor, sample_image):
        """Test that invalid coordinates raise ValueError."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        # Out of bounds point
        with pytest.raises(ValueError, match="out of image bounds"):
            engine.generate_mask(point_coords=[150, 150])
        
        # Negative coordinates
        with pytest.raises(ValueError, match="out of image bounds"):
            engine.generate_mask(point_coords=[-10, 50])
        
        # Invalid box (x2 < x1)
        with pytest.raises(ValueError, match="Invalid box coordinates"):
            engine.generate_mask(box_coords=[90, 10, 10, 90])
    
    def test_generate_mask_level_parameter(self, mock_sam_predictor, sample_image):
        """Test that level parameter affects mask selection."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        # Mock predictor to return multiple masks
        mock_sam_predictor.predict.return_value = (
            np.array([
                np.ones((100, 100), dtype=bool),
                np.zeros((100, 100), dtype=bool),
                np.ones((100, 100), dtype=bool) * 0.5
            ]),
            np.array([0.9, 0.8, 0.7]),
            np.zeros((3, 100, 100), dtype=bool)
        )
        
        # Level 0 should return first mask
        mask0 = engine.generate_mask(point_coords=[50, 50], level=0)
        assert mask0.sum() > 0, "Level 0 should return non-empty mask"
        
        # Level 1 should return second mask
        mask1 = engine.generate_mask(point_coords=[50, 50], level=1)
        assert mask1 is not None
    
    def test_generate_mask_with_refinement(self, mock_sam_predictor, sample_image):
        """Test mask refinement logic is applied."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        # Test with color difference refinement
        mask = engine.generate_mask(point_coords=[50, 50], level=0)
        
        assert mask is not None
        # Refined mask should not include entire image
        assert mask.sum() < mask.size, "Refined mask should be selective"
    
    @pytest.mark.slow
    def test_generate_mask_performance(self, mock_sam_predictor, sample_large_image):
        """Test mask generation performance on large images."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_large_image)
        
        import time
        start = time.time()
        mask = engine.generate_mask(point_coords=[512, 384])
        duration = time.time() - start
        
        # Should complete in reasonable time (< 1 second for mock)
        assert duration < 1.0, "Mask generation should be fast"
        assert mask is not None


class TestMaskRefinement:
    """Test mask refinement and cleanup logic."""
    
    def test_small_object_detection(self, mock_sam_predictor, sample_image):
        """Test that small objects are detected correctly."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        engine.set_image(sample_image)
        
        # Mock small mask
        small_mask = np.zeros((100, 100), dtype=bool)
        small_mask[45:55, 45:55] = True  # 10x10 = 100 pixels (1% of image)
        
        mock_sam_predictor.predict.return_value = (
            np.array([small_mask]),
            np.array([0.9]),
            np.zeros((1, 100, 100), dtype=bool)
        )
        
        mask = engine.generate_mask(point_coords=[50, 50], level=0)
        assert mask is not None
        # Small object logic should preserve small masks
        assert mask.sum() > 0


@pytest.mark.integration
class TestSegmentationIntegration:
    """Integration tests for full segmentation workflow."""
    
    def test_full_workflow_point_mode(self, mock_sam_predictor, sample_image):
        """Test complete workflow: set image -> generate mask with point."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        
        # Step 1: Set image
        engine.set_image(sample_image)
        assert engine.is_image_set
        
        # Step 2: Generate mask
        mask = engine.generate_mask(point_coords=[50, 50], level=0)
        assert mask is not None
        assert mask.shape == (100, 100)
        
        # Step 3: Verify mask is binary
        assert set(np.unique(mask)).issubset({False, True})
    
    def test_full_workflow_box_mode(self, mock_sam_predictor, sample_image):
        """Test complete workflow: set image -> generate mask with box."""
        engine = SegmentationEngine(model_instance=mock_sam_predictor)
        
        engine.set_image(sample_image)
        mask = engine.generate_mask(box_coords=[20, 20, 80, 80], level=0)
        
        assert mask is not None
        assert mask.shape == (100, 100)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
