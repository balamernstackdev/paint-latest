# AI Paint Visualizer - System Architecture

## Overview

The AI Paint Visualizer is a Streamlit-based web application that uses AI-powered segmentation (MobileSAM) to enable realistic paint visualization on walls and objects. The system combines computer vision, color science, and interactive UI components to deliver a professional-grade paint preview experience.

## System Design Principles

1. **Separation of Concerns**: Core logic (segmentation, color transfer) separated from UI
2. **Performance First**: Aggressive caching, optimized image processing, fragment-based UI
3. **Mobile-Responsive**: Custom touch handlers, responsive layouts, mobile-optimized controls
4. **Maintainability**: Modular architecture, comprehensive documentation, type hints

## Component Architecture

### Core Modules

#### 1. Segmentation Engine (`core/segmentation.py`)
**Purpose**: AI-powered object detection and mask generation

**Key Components:**
- `SegmentationEngine`: Main class wrapping MobileSAM predictor
- Mask generation with point-click or bounding box input
- Adaptive mask refinement using color/edge detection
- Three precision levels: walls, small objects, floors

#### 2. Color Transfer Engine (`core/colorizer.py`)
**Purpose**: Realistic paint application using LAB color space

**Key Components:**
- `ColorTransferEngine`: Stateless color manipulation
- `hex_to_rgb()`: Hex color validation and conversion
- `apply_color()`: Single-layer paint application
- `composite_multiple_layers()`: Multi-layer blending

**Color Science:**
1. Convert RGB → LAB color space (perceptually uniform)
2. Transfer A/B channels (color) while preserving L (lightness)
3. Apply Gaussian blur for natural feathering
4. Blend using alpha compositing with intensity control
5. Convert back to RGB for display

#### 3. UI Components (`utils/ui/`)
**Purpose**: Modular, responsive UI with fragment-based updates

###Data Flow

**Paint Application Workflow:**
1. User Interaction → Coordinate Capture
2. Coordinate Transformation (display → original space)
3. Mask Generation (SAM inference + refinement)
4. Color Application (LAB color transfer)
5. Layer Composition (multi-layer blending)
6. Display Update (crop, scale, cache)

## Technology Stack

- **Frontend**: Streamlit 1.38.0
- **AI/ML**: PyTorch 2.x, MobileSAM
- **Image Processing**: OpenCV, PIL, NumPy
- **Testing**: pytest, pytest-cov

## Design Patterns

1. **Engine Pattern**: Stateless processors (SegmentationEngine, ColorTransferEngine)
2. **Fragment Pattern**: Isolated UI updates via `@st.fragment`
3. **Caching Strategy**: Multi-level (Streamlit cache, session state, LRU)
4. **Configuration over Code**: Central constants in `config/`
5. **Delegation Pattern**: Backward compatibility via module delegation

## Performance Optimizations

1. Image caching with render_id
2. LAB conversion caching
3. JPEG compression for backgrounds
4. Fragment isolation for zoom/pan
5. Lazy SAM loading

See full documentation in project docs/ folder.
