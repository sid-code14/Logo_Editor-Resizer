# config.py

# Target output sizes (width, height)
TARGET_SIZES = [
    (1000, 1000),   # 1:1
    (1440, 2160),   # 2:3
    (1600, 1200),   # 4:3
    (1920, 1080),   # 16:9
    (2560, 1080),   # 21:9
]

# Map each size to a short aspect‑ratio label
ASPECT_LABELS = {
    (1000, 1000): "1x1",
    (1440, 2160): "2x3",
    (1600, 1200): "4x3",
    (1920, 1080): "16x9",
    (2560, 1080): "21x9",
}

# Default resize mode – now always smart_fit
MODE = 'smart_fit'

# Padding colour for 'fit' mode (used by smart_fit internally as fallback)
PAD_COLOR = (0, 0, 0)

# Auto-trim flat-colour borders from the source image before resizing.
AUTO_TRIM = True

# Tolerance (0-255) for how close a pixel must be to PAD_COLOR
TRIM_TOLERANCE = 12

# Width of the soft ramp for background removal
KEY_EDGE_SOFTNESS = 24

# Apply a light unsharp-mask after resizing
SHARPEN_AFTER_RESIZE = True
SHARPEN_PARAMS = dict(radius=1.2, percent=60, threshold=2)

# 'smart_fit' settings
SMART_FIT_MAX_OVERFLOW = 1.0

# Resize in linear light (gamma-correct)
GAMMA_CORRECT_RESIZE = True

# Output quality for JPEG
JPEG_QUALITY = 95
JPEG_PROGRESSIVE = True

# Preserve transparency in PNG output
PRESERVE_TRANSPARENCY = True