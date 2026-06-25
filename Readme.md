# Image Resizer – Smart Fit

## 📖 Description

**Image Resizer – Smart Fit** is a powerful, production-ready image processing tool that resizes high-resolution images to five fixed aspect ratios using a **content‑aware "smart_fit"** algorithm. Unlike simple stretching or cropping, smart_fit intelligently scales each image to fill the target dimensions while minimising distortion and preserving the most important visual content.

The project provides two interfaces:

1. **Command‑Line Interface (CLI)** – For batch processing and automation.
2. **Streamlit Web App** – A user‑friendly GUI with real‑time previews, background removal (both colour‑based and AI‑powered), and bulk export.

### Key Features

- **Smart Fit Resizing** – Dynamically balances scaling and cropping to fit each target aspect ratio with minimal wasted space.
- **Five Preset Sizes** – Covers common use cases:
  - `1:1` (1000×1000) – Social media profile pictures
  - `2:3` (1440×2160) – Portrait / Instagram vertical
  - `4:3` (1600×1200) – Standard photo
  - `16:9` (1920×1080) – HD video thumbnail
  - `21:9` (2560×1080) – Ultra‑wide banner
- **Background Variants** – Generate multiple versions:
  - **Original** – Keep the image as‑is
  - **Transparent** – Remove background (colour‑based or AI)
  - **White** – Place subject on a white canvas
  - **Black** – Place subject on a black canvas
- **AI Background Removal** (Web App only) – Uses `rembg` (U²‑Net) to automatically separate foreground from background, even on complex images.
- **Auto‑trim** – Automatically detects and removes solid‑colour borders from source images.
- **Lossless Output** – PNG for transparent/white/black variants, high‑quality JPEG for originals.
- **Batch Processing** – Process multiple images at once.
- **ZIP Export** – Download all generated images as a single archive with per‑image folders.

---

## 🚀 Installation

### 1. Clone the repository (or download the files)

```bash
git clone https://github.com/sid-code14/Logo_Editor-Resizer.git
cd Logo_Editor-Resizer
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

**Required packages:**
- `Pillow >= 10.0.0` – Image processing
- `streamlit >= 1.28.0` – Web interface
- `numpy >= 1.24.0` – Array operations
- `rembg >= 2.0.0` – AI background removal (optional but recommended for web app)

**Note:** `rembg` will download a ~176 MB model (`u2net.onnx`) on first use if you enable AI background removal.

---

## 🖥️ Usage

### A. Command‑Line Interface (CLI)

#### Process a single image

```bash
python cli_tool.py path/to/your/image.jpg -o output_folder
```

#### Process all images in a folder

```bash
python cli_tool.py --input-dir images_folder -o output_folder
```

#### Options

| Argument | Description |
|----------|-------------|
| `image` | Path to a single image file |
| `-i`, `--input-dir` | Process all images in a folder |
| `-o`, `--output` | Output folder (default: `output`) |
| `--no-trim` | Disable auto‑trimming of solid‑colour borders |
| `--bg`, `--backgrounds` | Background variants: `original`, `transparent`, `white`, `black`, `all` (default: `original`) |

#### Examples

```bash
# Generate original, transparent, white, and black variants
python cli_tool.py photo.png --bg all -o results

# Process all PNGs in a folder with auto‑trim disabled
python cli_tool.py --input-dir ./images --no-trim -o output
```

**Output organisation:** Each input image gets its own subfolder (named after the file) inside the output directory.

---

### B. Streamlit Web App

Launch the interactive web interface:

```bash
streamlit run web_app.py
```

Then open your browser at `http://localhost:8501`.

#### Web App Workflow

1. **Upload Images** – Drag & drop one or more images (JPG, PNG, WebP).
2. **Choose Backgrounds** – Select which background variants to generate.
3. **Enable AI** (optional) – Use deep‑learning background removal for complex images.
4. **Set Source Background Colour** – Auto‑detected from the image edges; override if needed.
5. **Generate** – Click the button to process all sizes and backgrounds.
6. **Download** – Individual downloads per variant or a single ZIP archive.

---

## ⚙️ Configuration (`config.py`)

All global settings are in `config.py`:

```python
# Target sizes (width, height)
TARGET_SIZES = [
    (1000, 1000),   # 1:1
    (1440, 2160),   # 2:3
    (1600, 1200),   # 4:3
    (1920, 1080),   # 16:9
    (2560, 1080),   # 21:9
]

# Aspect ratio labels (for filenames)
ASPECT_LABELS = {
    (1000, 1000): "1x1",
    (1440, 2160): "2x3",
    (1600, 1200): "4x3",
    (1920, 1080): "16x9",
    (2560, 1080): "21x9",
}

# Padding colour (fallback for fit mode)
PAD_COLOR = (0, 0, 0)

# Auto‑trim borders from source images
AUTO_TRIM = True
TRIM_TOLERANCE = 12

# AI/soft keying settings
KEY_EDGE_SOFTNESS = 24

# Sharpening after resize
SHARPEN_AFTER_RESIZE = True
SHARPEN_PARAMS = dict(radius=1.2, percent=60, threshold=2)

# JPEG output quality
JPEG_QUALITY = 95
JPEG_PROGRESSIVE = True

# Preserve PNG transparency
PRESERVE_TRANSPARENCY = True
```

---

## 🧠 How "Smart Fit" Works

The `smart_fit` algorithm is the core innovation. It:

1. **Detects safe margins** – Measures how much solid‑colour border can be safely cropped from each edge without cutting into important content.
2. **Computes a scaling factor** – Starts with the "fit" scale (ensures the entire image fits inside the target) and increases it toward the "cover" scale based on the available safe margin.
3. **Resizes and centres** – Scales the image, crops any overflow (only from the safe‑margin areas), and pads any remaining space with the background colour.
4. **Sharpens** – Applies an adaptive unsharp mask that scales with the amount of upscaling.

This approach gives you the best of both **fit** (no cropping) and **cover** (no padding) – automatically choosing the optimal balance for each image and target size.

---

## 🛠️ Additional Tools

### `Folder_Name_Generator.py`

A small utility that creates a folder for each file in a given directory. Useful for organising images before batch processing.

```bash
python Folder_Name_Generator.py
# Enter folder path when prompted
```

---

## 📁 Project Structure

```
.
├── cli_tool.py              # Command‑line entry point
├── config.py                # Global configuration
├── resize_core.py           # Shared image‑processing logic
├── web_app.py               # Streamlit web interface
├── Folder_Name_Generator.py # Folder‑organisation helper
├── requirements.txt         # Python dependencies
├── README.md                # This file
└── output/                  # Default output folder (created on run)
```

---

## 🔧 Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Pillow  | ≥10.0.0 | Image I/O and manipulation |
| Streamlit | ≥1.28.0 | Web UI framework |
| NumPy   | ≥1.24.0 | Numerical array operations |
| rembg   | ≥2.0.0  | AI background removal (optional) |

---

## 📝 Notes

- **Background Removal:** The colour‑based method (`extract_foreground_mask`) requires that you set `PAD_COLOR` (or provide the source background colour via the web app) to the exact background colour of your image. The AI method (`remove_background_ai`) works on any image but is slower and requires an internet connection for the initial model download.
- **Output Formats:** PNG is used for transparent/white/black variants (to preserve quality). JPEG is used for originals (with quality=95 and subsampling=0 for minimal artefacts).
- **Large Batches:** The CLI tool processes images sequentially. The web app processes them in the browser thread – for very large batches, consider using the CLI.

---

## 🤝 Contributing

Contributions are welcome! Please open an issue or pull request for any improvements, bug fixes, or additional features.

---

## 📄 License

This project is licensed under the **MIT License**. Feel free to use, modify, and distribute it as you see fit.

---

## 📧 Contact

For questions or feedback, please open an issue on the repository.

---

**Happy resizing! 🖼️**
