"""
Configuration constants for AI Paint Visualizer.
All tunable parameters and magic numbers are defined here with explanations.
"""


class SegmentationConfig:
    """Configuration for SAM-based image segmentation."""
    
    # --- Color Difference Thresholds ---
    # Max allowed RGB channel difference for small objects (0-255 scale)
    # Lower = stricter matching, higher = more tolerance for color variation
    COLOR_DIFF_SMALL_OBJECT = 50
    
    # Base color tolerance for standard walls (can decay with distance)
    # Allows paint to flow over subtle color variations
    COLOR_DIFF_STANDARD_WALL = 115
    
    # Tolerance for box selection mode (more relaxed)
    COLOR_DIFF_BOX_MODE = 100
    
    COLOR_DIFF_WALL_MODE = 95
    # Original edge detection: 30 - balanced edge detection
    EDGE_THRESHOLD_WALL_MODE = 10
    
    # --- Intelligent Object Detection (for auto mask selection) ---
    # Thresholds to detect doors/windows vs walls in Standard Walls mode
    DOOR_WINDOW_AREA_THRESHOLD = 0.15  # Objects < 15% of image are likely doors/windows
    DOOR_ASPECT_RATIO_MIN = 1.3  # Doors are taller than wide (height/width > 1.3)
    DOOR_WIDTH_MAX_RATIO = 0.30  # Doors typically < 30% of image width
    
    # Tolerance for level 1 (sub-segment) selections
    INTENSITY_DIFF_LEVEL_1 = 45
    
    # Tolerance for level 2 (whole object) selections
    INTENSITY_DIFF_LEVEL_2 = 100
    
    # --- Edge Detection Thresholds ---
    # Laplacian edge threshold for small objects (0-255)
    # Lower = detects finer edges, higher = only strong boundaries
    EDGE_THRESHOLD_SMALL_OBJECT = 20
    
    # Edge threshold for standard walls
    EDGE_THRESHOLD_STANDARD_WALL = 35
    
    # Edge threshold for box mode
    EDGE_THRESHOLD_BOX_MODE = 15
    
    # --- Size Thresholds ---
    # Minimum mask size in pixels to be considered valid
    MIN_MASK_AREA_PIXELS = 50
    
    # Threshold to classify as "small object" (3% of image area)
    SMALL_OBJECT_THRESHOLD = 0.03
    
    # Maximum area for noise filtering (0.3% of image area)
    NOISE_AREA_THRESHOLD = 0.003
    
    # --- Distance Decay Parameters ---
    # Maximum distance (pixels) before tolerance starts decaying
    # OPTIMIZED: Effectively disabled for standard rooms to ensure full coverage.
    DECAY_DISTANCE_MAX = 3000.0
    
    # Minimum decay factor (tolerance won't go below 80% of base)
    DECAY_FACTOR_MIN = 0.80
    
    # --- Morphological Operations ---
    # Kernel size for morphological operations
    MORPH_KERNEL_SIZE = (3, 3)
    
    # Gaussian blur kernel for mask smoothing
    GAUSSIAN_KERNEL_SIZE = (3, 3)
    
    # Circle radius for ensuring click point is preserved
    CLICK_PRESERVE_RADIUS = 2
    
    # --- SAM Model Parameters ---
    # Minimum score threshold for accepting SAM predictions
    SAM_MIN_SCORE = 0.4
    
    # Connectivity for connected components (4 or 8)
    CONNECTED_COMPONENTS_CONNECTIVITY = 8
    
    # --- Component Filtering (to prevent small object leaks) ---
    # Minimum component size as ratio of clicked component (0.15 = 15%)
    MIN_COMPONENT_RATIO = 0.15
    
    # Max distance allowed from click for disconnected pieces (pixels)
    MAX_COMPONENT_DISTANCE = 250


class AdaptiveProcessingConfig:
    """Configuration for adaptive paint processing based on object characteristics."""
    
    # Blur kernel adaptation based on edge density
    SHARP_EDGE_BLUR = (3, 3)  # For furniture, doors, sharp objects
    MEDIUM_BLUR = (5, 5)       # For standard walls
    SOFT_BLUR = (7, 7)         # For large floors/ceilings
    
    # Edge density thresholds for blur selection
    EDGE_DENSITY_SHARP_THRESHOLD = 0.3   # >30% edges = sharp object
    EDGE_DENSITY_MEDIUM_THRESHOLD = 0.1  # >10% edges = medium
    
    # Texture detection
    TEXTURE_VARIANCE_THRESHOLD = 100.0  # Laplacian variance for texture detection
    
    # Bilateral filter (for textured surfaces)
    BILATERAL_DIAMETER = 9
    BILATERAL_SIGMA_COLOR = 75
    BILATERAL_SIGMA_SPACE = 75
    
    # Object classification thresholds
    SMALL_OBJECT_AREA_THRESHOLD = 0.03   # <3% of image = small object
    LARGE_OBJECT_AREA_THRESHOLD = 0.30   # >30% of image = floor/ceiling
    CEILING_Y_THRESHOLD = 0.3            # Top 30% of image
    FLOOR_Y_THRESHOLD = 0.7              # Bottom 30% of image
    
    # Object-specific parameters
    WALL_SMOOTH_COLOR_TOL = 40.0
    WALL_TEXTURED_COLOR_TOL = 50.0
    FLOOR_COLOR_TOL = 60.0
    SMALL_OBJECT_COLOR_TOL = 30.0
    FURNITURE_COLOR_TOL = 35.0
    
    WALL_SMOOTH_EDGE_THRESH = 30
    WALL_TEXTURED_EDGE_THRESH = 40
    FLOOR_EDGE_THRESH = 25
    SMALL_OBJECT_EDGE_THRESH = 45
    FURNITURE_EDGE_THRESH = 50


class ColorizerConfig:
    """Configuration for color blending and application."""
    
    # --- Mask Processing ---
    # Number of dilation iterations to fill small gaps
    # Optimized for realistic coverage without bleeding
    DILATION_ITERATIONS = 1
    
    # Kernel size for dilation operations
    DILATION_KERNEL_SIZE = (3, 3)
    
    # Gaussian blur kernel for edge feathering
    # Optimized for realistic paint appearance
    BLUR_KERNEL_SIZE = (5, 5)  # Softer edges for realism
    
    # --- Texture Application ---
    # Maximum texture dimension before scaling down
    MAX_TEXTURE_SIZE = 512
    
    # Texture blending brightness multiplier
    TEXTURE_BRIGHTNESS_BOOST = 1.5
    
    # Default texture opacity
    DEFAULT_TEXTURE_OPACITY = 0.8
    
    # --- Color Space ---
    # Color space used for blending (LAB preserves luminosity)
    COLOR_SPACE = 'LAB'


class UIConfig:
    """Configuration for user interface behavior."""
    
    # --- Canvas ---
    # Default display width for canvas (pixels)
    DEFAULT_CANVAS_WIDTH = 800
    
    # Point display radius in point mode
    POINT_DISPLAY_RADIUS = 20
    
    # Stroke width for canvas drawings
    CANVAS_STROKE_WIDTH = 3
    
    # --- Zoom & Pan ---
    # Zoom level limits
    ZOOM_MIN = 1.0
    ZOOM_MAX = 4.0
    ZOOM_STEP = 0.2
    
    # Pan control arrow margin (pixels from edge)
    PAN_ARROW_MARGIN = 40
    
    # Pan arrow size
    PAN_ARROW_SIZE = 10
    
    # Pan arrow opacity
    PAN_ARROW_OPACITY = 0.6
    
    # --- Mobile Touch ---
    # Tap threshold (pixels) - movement below this is considered a tap
    TAP_THRESHOLD_PIXELS = 5
    
    # Sidebar width on mobile
    MOBILE_SIDEBAR_WIDTH = 320
    
    # --- Timing ---
    # Debounce delay for mobile sync (milliseconds)
    MOBILE_SYNC_DELAY_MS = 50
    
    # Interval for responsive scale checks (milliseconds)
    RESPONSIVE_SCALE_INTERVAL_MS = 500
    
    # --- Selection Highlight ---
    # Highlight blend opacity (0-1)
    HIGHLIGHT_OPACITY = 0.5
    
    # Default highlight color (RGB)
    DEFAULT_HIGHLIGHT_COLOR = (59, 130, 246)


class PerformanceConfig:
    """Configuration for performance optimization."""
    
    # --- Image Processing ---
    # Maximum image dimension for processing (larger images are resized)
    # OPTIMIZATION: Reduced from 1100 to 800 to match canvas width and speed up MobileSAM 
    MAX_IMAGE_DIMENSION = 800
    
    # JPEG quality for background image encoding (1-100)
    # Lower = smaller payload, faster loading, but lower quality
    BACKGROUND_IMAGE_QUALITY = 40
    
    # --- Caching ---
    # Maximum cache entries for image encoding
    IMAGE_ENCODING_CACHE_SIZE = 10
    
    # --- Threading ---
    # Number of OpenMP threads for CPU operations
    OMP_NUM_THREADS = 2
    
    # MKL threads
    MKL_NUM_THREADS = 2
    
    # PyTorch threads
    TORCH_NUM_THREADS = 2
    
    # --- Model ---
    # Model type for SAM
    SAM_MODEL_TYPE = "vit_t"
    
    # Model checkpoint path
    SAM_CHECKPOINT_PATH = "weights/mobile_sam.pt"
    
    # Cache version (increment to invalidate caches)
    # Cache version (increment to invalidate caches)
    # Cache version (increment to invalidate caches)
    CACHE_VERSION = "V1.7.0-TEXTURE-ARMOR-FIX"


# --- Export Convenience Constants ---
# These can be used directly without accessing the class

# Segmentation
COLOR_TOLERANCE_SMALL = SegmentationConfig.COLOR_DIFF_SMALL_OBJECT
COLOR_TOLERANCE_WALL = SegmentationConfig.COLOR_DIFF_STANDARD_WALL
EDGE_THRESHOLD = SegmentationConfig.EDGE_THRESHOLD_STANDARD_WALL

# UI
CANVAS_WIDTH = UIConfig.DEFAULT_CANVAS_WIDTH
TAP_THRESHOLD = UIConfig.TAP_THRESHOLD_PIXELS

# Performance
MAX_IMAGE_DIM = PerformanceConfig.MAX_IMAGE_DIMENSION
MAX_IMAGE_DIMENSION = PerformanceConfig.MAX_IMAGE_DIMENSION  # Direct export for imports
JPEG_QUALITY = PerformanceConfig.BACKGROUND_IMAGE_QUALITY
