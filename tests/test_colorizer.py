"""
Unit tests for core/colorizer.py color manipulation functions.

Tests cover hex conversion, color blending, LAB color space operations,
and multi-layer compositing.
"""

import pytest
import numpy as np
import cv2
from paint_core.colorizer import ColorTransferEngine


class TestHexToRGB:
    """Test suite for hex_to_rgb function."""
    
    def test_valid_hex_color(self):
        """Test conversion of valid hex color codes."""
        result = ColorTransferEngine.hex_to_rgb("#FF0000")
        assert result == (255, 0, 0), "Red color conversion failed"
        
        result = ColorTransferEngine.hex_to_rgb("#00FF00")
        assert result == (0, 255, 0), "Green color conversion failed"
        
        result = ColorTransferEngine.hex_to_rgb("#0000FF")
        assert result == (0, 0, 255), "Blue color conversion failed"
    
    def test_lowercase_hex(self):
        """Test that lowercase hex codes work."""
        result = ColorTransferEngine.hex_to_rgb("#8fbc8f")
        assert result == (143, 188, 143), "Lowercase hex failed"
    
    def test_invalid_length(self):
        """Test that invalid length hex codes raise ValueError."""
        with pytest.raises(ValueError, match="must be 7 characters"):
            ColorTransferEngine.hex_to_rgb("#FFF")
        
        with pytest.raises(ValueError, match="must be 7 characters"):
            ColorTransferEngine.hex_to_rgb("#FFFFFF00")
    
    def test_invalid_format(self):
        """Test that invalid format raises ValueError."""
        with pytest.raises(ValueError, match="Invalid hex color"):
            ColorTransferEngine.hex_to_rgb("FF0000")  # Missing #
        
        with pytest.raises(ValueError, match="Invalid hex color"):
            ColorTransferEngine.hex_to_rgb("#GGGGGG")  # Invalid characters
    
    def test_type_validation(self):
        """Test that non-string input raises TypeError."""
        with pytest.raises(TypeError, match="must be a string"):
            ColorTransferEngine.hex_to_rgb(123456)


class TestApplyColor:
    """Test suite for apply_color method."""
    
    def test_basic_color_application(self, sample_image, sample_mask, sample_color):
        """Test basic paint application to image."""
        result = ColorTransferEngine.apply_color(
            sample_image,
            sample_mask,
            sample_color,
            intensity=0.8
        )
        
        assert result.shape == sample_image.shape, "Output shape mismatch"
        assert result.dtype == np.uint8, "Output dtype should be uint8"
        assert not np.array_equal(result, sample_image), "Image should be modified"
    
    def test_zero_intensity(self, sample_image, sample_mask, sample_color):
        """Test that zero intensity returns original image."""
        result = ColorTransferEngine.apply_color(
            sample_image,
            sample_mask,
            sample_color,
            intensity=0.0
        )
        
        np.testing.assert_array_equal(result, sample_image,
                                     "Zero intensity should not modify image")
    
    def test_full_intensity(self, sample_image, sample_mask, sample_color):
        """Test full intensity color application."""
        result = ColorTransferEngine.apply_color(
            sample_image,
            sample_mask,
            sample_color,
            intensity=1.0
        )
        
        # Masked area should be significantly different
        masked_area_original = sample_image[sample_mask]
        masked_area_result = result[sample_mask]
        assert not np.array_equal(masked_area_original, masked_area_result),\
            "Masked area should be modified"
    
    def test_empty_mask(self, sample_image, sample_color):
        """Test that empty mask returns original image."""
        empty_mask = np.zeros_like(sample_image[:, :, 0], dtype=bool)
        result = ColorTransferEngine.apply_color(
            sample_image,
            empty_mask,
            sample_color
        )
        
        np.testing.assert_array_equal(result, sample_image,
                                     "Empty mask should not modify image")
    
    def test_invalid_mask_shape(self, sample_image, sample_color):
        """Test that mismatched mask shape raises ValueError."""
        wrong_mask = np.ones((50, 50), dtype=bool)
        
        with pytest.raises(ValueError, match="must match image dimensions"):
            ColorTransferEngine.apply_color(
                sample_image,
                wrong_mask,
                sample_color
            )
    
    def test_intensity_bounds(self, sample_image, sample_mask, sample_color):
        """Test that intensity is properly bounded."""
        # Intensity > 1.0 should be clamped
        result_high = ColorTransferEngine.apply_color(
            sample_image,
            sample_mask,
            sample_color,
            intensity=1.5
        )
        
        result_max = ColorTransferEngine.apply_color(
            sample_image,
            sample_mask,
            sample_color,
            intensity=1.0
        )
        
        # Should produce same result due to clamping
        np.testing.assert_array_equal(result_high, result_max,
                                     "Intensity should be clamped to 1.0")


class TestCompositeMultipleLayers:
    """Test suite for composite_multiple_layers method."""
    
    def test_single_layer(self, sample_image, sample_mask, sample_color):
        """Test compositing with single layer."""
        layers = [{
            'mask': sample_mask,
            'color': sample_color,
            'intensity': 0.8
        }]
        
        result = ColorTransferEngine.composite_multiple_layers(
            sample_image,
            layers
        )
        
        assert result.shape == sample_image.shape
        assert result.dtype == np.uint8
    
    def test_multiple_layers(self, sample_image):
        """Test compositing with multiple overlapping layers."""
        mask1 = np.zeros((100, 100), dtype=bool)
        mask1[:, :50] = True
        
        mask2 = np.zeros((100, 100), dtype=bool)
        mask2[:, 25:75] = True
        
        layers = [
            {'mask': mask1, 'color': '#FF0000', 'intensity': 0.7},
            {'mask': mask2, 'color': '#0000FF', 'intensity': 0.7}
        ]
        
        result = ColorTransferEngine.composite_multiple_layers(
            sample_image,
            layers
        )
        
        assert result.shape == sample_image.shape
        # Overlapping area should show blended effect
        overlap_area = result[:, 25:50]
        assert overlap_area.mean() > 0, "Overlapping area should be painted"
    
    def test_empty_layers(self, sample_image):
        """Test that empty layers list returns original image."""
        result = ColorTransferEngine.composite_multiple_layers(
            sample_image,
            []
        )
        
        np.testing.assert_array_equal(result, sample_image,
                                     "Empty layers should return original")
    
    @pytest.mark.slow
    def test_many_layers_performance(self, sample_large_image):
        """Test performance with many layers."""
        layers = []
        for i in range(10):
            mask = np.random.rand(768, 1024) > 0.8
            layers.append({
                'mask': mask,
                'color': f'#{i%16:01x}{(i*2)%16:01x}{(i*3)%16:01x}000',
                'intensity': 0.5
            })
        
        result = ColorTransferEngine.composite_multiple_layers(
            sample_large_image,
            layers
        )
        
        assert result.shape == sample_large_image.shape


@pytest.mark.unit
class TestColorAccuracy:
    """Test color accuracy and LAB color space operations."""
    
    def test_color_transfer_preserves_saturation(self, sample_image):
        """Test that color transfer preserves image saturation patterns."""
        mask = np.ones((100, 100), dtype=bool)
        result = ColorTransferEngine.apply_color(
            sample_image,
            mask,
            "#808080",  # Gray
            intensity=0.5
        )
        
        # Result should maintain some color variation
        std_original = sample_image.std()
        std_result = result.std()
        
        assert std_result > 0, "Result should have color variation"
        assert std_result < std_original, "Gray should reduce variation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
