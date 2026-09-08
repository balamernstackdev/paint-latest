# Security validation and input sanitization utilities

import re
from typing import Tuple, Optional
import numpy as np


def validate_hex_color(color: str) -> Tuple[bool, Optional[str]]:
    """
    Validate and sanitize hex color code.
    
    Args:
        color: Hex color string to validate
        
    Returns:
        tuple: (is_valid, error_message)
        
    Example:
        >>> validate_hex_color("#FF0000")
        (True, None)
        >>> validate_hex_color("invalid")
        (False, "Invalid hex color format")
    """
    if not isinstance(color, str):
        return False, "Color must be a string"
    
    if not color.startswith("#"):
        return False, "Hex color must start with #"
    
    if len(color) != 7:
        return False, "Hex color must be 7 characters (#RRGGBB)"
    
    if not re.match(r"^#[0-9A-Fa-f]{6}$", color):
        return False, "Invalid hex color format"
    
    return True, None


def validate_coordinates(x: int, y: int, image_width: int, image_height: int) -> Tuple[bool, Optional[str]]:
    """
    Validate that coordinates are within image bounds.
    
    Args:
        x, y: Coordinates to validate
        image_width, image_height: Image dimensions
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if x < 0 or x >= image_width:
        return False, f"X coordinate {x} out of bounds (0-{image_width-1})"
    
    if y < 0 or y >= image_height:
        return False, f"Y coordinate {y} out of bounds (0-{image_height-1})"
    
    return True, None


def validate_box_coordinates(x1: int, y1: int, x2: int, y2: int, 
                             image_width: int, image_height: int) -> Tuple[bool, Optional[str]]:
    """
    Validate bounding box coordinates.
    
    Args:
        x1, y1, x2, y2: Box coordinates (top-left, bottom-right)
        image_width, image_height: Image dimensions  
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check individual coordinates
    for x, y in [(x1, y1), (x2, y2)]:
        valid, msg = validate_coordinates(x, y, image_width, image_height)
        if not valid:
            return False, msg
    
    # Check box validity
    if x2 <= x1:
        return False, f"Invalid box: x2 ({x2}) must be greater than x1 ({x1})"
    
    if y2 <= y1:
        return False, f"Invalid box: y2 ({y2}) must be greater than y1 ({y1})"
    
    return True, None


def validate_image_array(image: np.ndarray) -> Tuple[bool, Optional[str]]:
    """
    Validate image array format and dimensions.
    
    Args:
        image: NumPy array to validate
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if not isinstance(image, np.ndarray):
        return False, "Image must be a NumPy array"
    
    if image.ndim != 3:
        return False, f"Image must be 3-dimensional, got {image.ndim}D"
    
    if image.shape[2] != 3:
        return False, f"Image must have 3 channels (RGB), got {image.shape[2]}"
    
    if image.dtype != np.uint8:
        return False, f"Image must be uint8, got {image.dtype}"
    
    if image.size == 0:
        return False, "Image is empty"
    
    return True, None


def sanitize_filename(filename: str, max_length: int = 255) -> str:
    """
    Sanitize filename to prevent path traversal and invalid characters.
    
    Args:
        filename: Original filename
        max_length: Maximum allowed length
        
    Returns:
        str: Sanitized filename
        
    Example:
        >>> sanitize_filename("../../etc/passwd")
        'passwd'
        >>> sanitize_filename("my<image>.png")
        'my_image_.png'
    """
    # Remove path components
    filename = filename.split("/")[-1].split("\\")[-1]
    
    # Remove invalid characters
    filename = re.sub(r'[<>:"/\\|?*]', '_', filename)
    
    # Truncate if too long
    if len(filename) > max_length:
        name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
        filename = name[:max_length-len(ext)-1] + '.' + ext if ext else name[:max_length]
    
    return filename or "untitled"


def validate_upload_file(file_obj, max_size_mb: int = 10, 
                         allowed_extensions: Tuple[str, ...] = ('.jpg', '.jpeg', '.png')) -> Tuple[bool, Optional[str]]:
    """
    Validate uploaded file for security.
    
    Args:
        file_obj: Streamlit UploadedFile object
        max_size_mb: Maximum file size in megabytes
        allowed_extensions: Tuple of allowed file extensions
        
    Returns:
        tuple: (is_valid, error_message)
    """
    if file_obj is None:
        return False, "No file provided"
    
    # Check file extension
    filename = file_obj.name.lower()
    if not any(filename.endswith(ext) for ext in allowed_extensions):
        return False, f"File type not allowed. Allowed: {', '.join(allowed_extensions)}"
    
    # Check file size
    file_size_mb = file_obj.size / (1024 * 1024)
    if file_size_mb > max_size_mb:
        return False, f"File too large ({file_size_mb:.1f}MB). Maximum: {max_size_mb}MB"
    
    return True, None
