# AI-Powered Interactive Object Color Visualization System

## Overview
This application allows users to upload interior images, select objects (walls, furniture) via AI-assisted segmentation (SAM), and recolor them realistically using LAB color space blending.

## Prerequisites
- Python 3.8+
- CUDA-capable GPU (Recommended) or CPU

## Installation

1.  **Clone/Open Project Directory**
    ```bash
    cd "Python Image with color"
    ```

2.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Download Model Weights**
    If the `weights/` folder is empty, run:
    ```bash
    python download_weights.py
    ```
    This downloads the `sam_vit_b_01ec64.pth` checkpoint.

## Running the Application
Run the Streamlit app:
```bash
streamlit run app.py
```

## Usage Guide
1.  **Upload**: Drag and drop an interior image (JPG/PNG).
2.  **Wait**: The system will compute embeddings (takes ~5-10s on CPU initially).
3.  **Select**: Click on the object you want to recolor on the image.
4.  **Recolor**: Pick a color from the sidebar and click "Apply Color".
5.  **Iterate**: Use "Undo" to revert changes.
6.  **Download**: Click "Download Image" to save your result.

## Architecture
-   **Frontend**: Streamlit
-   **AI Model**: Segment Anything Model (ViT-B)
-   **Color Engine**: OpenCV (LAB Color Space)

## Deployment (Render)

This project includes configuration for deploying to [Render](https://render.com).

1.  Push this code to a **GitHub** or **GitLab** repository.
2.  Log in to Render and click **New +** -> **Web Service**.
3.  Connect your repository.
4.  Render should automatically detect the `render.yaml` file.
    *   If manually configuring:
        *   **Runtime**: Python 3
        *   **Build Command**: `./build.sh`
        *   **Start Command**: `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`
5.  **Important**: Select the **Starter** plan or higher. The AI model requires significant RAM and may crash on the Free tier.

