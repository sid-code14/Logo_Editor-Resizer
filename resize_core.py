# resize_core.py
"""
Shared image-resizing logic for the CLI tool and the Streamlit web app.
"""

import numpy as np
from PIL import Image, ImageFilter, ImageChops

from config import (
    PAD_COLOR,
    AUTO_TRIM,
    TRIM_TOLERANCE,
    KEY_EDGE_SOFTNESS,
    SHARPEN_AFTER_RESIZE,
    SHARPEN_PARAMS,
    PRESERVE_TRANSPARENCY,
    SMART_FIT_MAX_OVERFLOW,
    GAMMA_CORRECT_RESIZE,
)


def _has_alpha(img):
    return img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)


def _srgb_to_linear(arr):
    return np.where(arr <= 0.04045, arr / 12.92, ((arr + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(arr):
    arr = np.clip(arr, 0.0, 1.0)
    return np.where(arr <= 0.0031308, arr * 12.92, 1.055 * (arr ** (1 / 2.4)) - 0.055)


def high_quality_resize(img, target_w, target_h):
    """
    Resize like a polished commercial tool would: do the actual pixel
    averaging in LINEAR light rather than gamma-encoded sRGB space.
    """
    if target_w <= 0 or target_h <= 0:
        raise ValueError("Target dimensions must be positive")

    if not GAMMA_CORRECT_RESIZE:
        return img.resize((target_w, target_h), Image.LANCZOS)

    has_alpha = _has_alpha(img)
    rgb = img.convert("RGB")
    arr = np.asarray(rgb).astype(np.float32) / 255.0
    linear = _srgb_to_linear(arr)

    h, w, c = linear.shape
    out = np.empty((target_h, target_w, c), dtype=np.float32)
    for ch in range(c):
        chan_img = Image.fromarray(linear[:, :, ch], mode="F")
        out[:, :, ch] = np.asarray(chan_img.resize((target_w, target_h), Image.LANCZOS))

    srgb = _linear_to_srgb(out)
    srgb_u8 = np.clip(srgb * 255.0 + 0.5, 0, 255).astype(np.uint8)
    result = Image.fromarray(srgb_u8, mode="RGB")

    if has_alpha:
        alpha = img.convert("RGBA").split()[-1]
        alpha_resized = alpha.resize((target_w, target_h), Image.LANCZOS)
        result = result.convert("RGBA")
        result.putalpha(alpha_resized)

    return result


def _scaled_sharpen_params(orig_size, new_size, base_params):
    """
    Scale unsharp-mask strength with how much upscaling happened.
    """
    orig_w, orig_h = orig_size
    new_w, new_h = new_size
    ratio = max(new_w / max(orig_w, 1), new_h / max(orig_h, 1))

    params = dict(base_params)
    if ratio > 1:
        boost = min(ratio, 3.0)
        params["percent"] = int(min(base_params["percent"] * boost, 180))
        params["radius"] = round(min(base_params["radius"] * (1 + 0.15 * (boost - 1)), 2.5), 2)
    return params


def auto_trim(img, bg_color=PAD_COLOR, tolerance=TRIM_TOLERANCE):
    """
    Crop away solid-colour borders that match bg_color (within tolerance).
    """
    if _has_alpha(img):
        rgba = img.convert("RGBA")
        alpha = rgba.split()[-1]
        bbox = alpha.getbbox()
        if bbox:
            return img.crop(bbox)
        return img

    rgb = img.convert("RGB")
    bg = Image.new("RGB", rgb.size, bg_color)
    diff = ImageChops.difference(rgb, bg)

    if tolerance > 0:
        diff = diff.point(lambda p: 0 if p <= tolerance else p)

    bbox = diff.getbbox()
    if bbox:
        return img.crop(bbox)
    return img


def _safe_crop_fractions(img, bg_color=PAD_COLOR, tolerance=TRIM_TOLERANCE):
    """
    After the image has already been trimmed to its tight bounding box,
    measure how much additional margin on each axis is STILL flat
    background colour.
    """
    if _has_alpha(img):
        rgba = img.convert("RGBA")
        mask = rgba.split()[-1].point(lambda a: 255 if a > 8 else 0)
    else:
        rgb = img.convert("RGB")
        bg = Image.new("RGB", rgb.size, bg_color)
        diff = ImageChops.difference(rgb, bg)
        gray = diff.convert("L")
        mask = gray.point(lambda p: 255 if p > tolerance else 0)

    w, h = mask.size
    bbox = mask.getbbox()
    if not bbox:
        return 1.0, 1.0

    left, top, right, bottom = bbox
    margin_left, margin_right = left, w - right
    margin_top, margin_bottom = top, h - bottom

    safe_w_frac = min(margin_left, margin_right) / (w / 2) if w else 0.0
    safe_h_frac = min(margin_top, margin_bottom) / (h / 2) if h else 0.0

    return safe_w_frac, safe_h_frac


def detect_background_color(img, border_px=12):
    """
    Best-effort guess at an image's background colour by sampling thin
    strips along all four edges and taking the median colour.

    Most exported logo/product PNGs and JPGs have a solid-colour
    background that touches all four edges of the canvas, so this is a
    much safer default than assuming a single hard-coded colour (like
    PAD_COLOR) matches every image a user uploads.
    """
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, w, _ = rgb.shape
    b = max(1, min(border_px, h // 4 or 1, w // 4 or 1))

    strips = np.concatenate([
        rgb[:b, :, :].reshape(-1, 3),
        rgb[-b:, :, :].reshape(-1, 3),
        rgb[:, :b, :].reshape(-1, 3),
        rgb[:, -b:, :].reshape(-1, 3),
    ])
    return tuple(int(round(c)) for c in np.median(strips, axis=0))


def _decontaminate_edges(rgb_arr, alpha_u8, bg_color):
    """
    Remove background-colour bleed from semi-transparent edge pixels.

    A pixel that is, say, 40% foreground / 60% background already has the
    background colour mixed into its RGB value (that's exactly what
    anti-aliasing along an edge is). If we just keep that RGB value as-is
    and lower its alpha, recompositing it onto a *different* background
    leaves a visible halo/fringe of the ORIGINAL background colour around
    every edge. This "un-mixes" the colour so only the foreground
    contribution remains, the standard fix used by real cutout tools.
    """
    bg = np.asarray(bg_color, dtype=np.float32)
    a = (alpha_u8.astype(np.float32) / 255.0)[..., None]
    a_safe = np.clip(a, 0.12, 1.0)  # avoid divide-by-near-zero blowups on near-invisible pixels

    fg = bg + (rgb_arr.astype(np.float32) - bg) / a_safe
    fg = np.clip(fg, 0, 255)

    # Only touch genuine edge pixels; leave fully-opaque interior pixels untouched.
    out = np.where(a >= 0.98, rgb_arr.astype(np.float32), fg)
    return out.astype(np.uint8)


def extract_foreground_mask(img, bg_color=PAD_COLOR, tolerance=TRIM_TOLERANCE,
                             edge_softness=KEY_EDGE_SOFTNESS):
    """
    Convert pixels matching bg_color to transparent.

    Unlike a hard 0/255 cutoff, this ramps alpha smoothly over
    `edge_softness` levels of colour distance so anti-aliased edges in the
    source (curved letterforms, soft shadows, etc.) stay smooth instead of
    becoming jagged/stair-stepped. Edge pixels also get background-colour
    bleed removed (see `_decontaminate_edges`) so there's no white/black
    halo when the cutout is placed on a new background.

    IMPORTANT: bg_color must be the ACTUAL background colour of `img`, not
    just whatever padding colour the rest of the pipeline happens to use.
    Use `detect_background_color(img)` if you don't know it ahead of time.
    """
    if _has_alpha(img):
        return img.convert("RGBA")

    rgb_arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    bg = np.asarray(bg_color, dtype=np.float32)

    dist = np.sqrt(((rgb_arr - bg) ** 2).sum(axis=-1))
    alpha = np.clip((dist - tolerance) / max(edge_softness, 1e-6), 0.0, 1.0)
    alpha_u8 = np.round(alpha * 255.0).astype(np.uint8)

    rgb_u8 = rgb_arr.astype(np.uint8)
    decontaminated = _decontaminate_edges(rgb_u8, alpha_u8, bg_color)

    out = np.dstack([decontaminated, alpha_u8])
    return Image.fromarray(out, mode="RGBA")


def remove_background_ai(image):
    """
    Use rembg to remove the background from an image.
    Returns an RGBA image with transparent background.
    """
    try:
        from rembg import remove
        # rembg expects a PIL Image, returns a PIL Image with alpha
        return remove(image)
    except ImportError:
        raise ImportError("rembg not installed. Please install it: pip install rembg")


def compose_background(img, bg_color):
    """
    Place an image (with or without alpha) onto a solid RGB canvas.
    If bg_color is None, returns the image with an alpha channel unchanged.
    """
    if bg_color is None:
        return img.convert("RGBA")

    canvas = Image.new("RGB", img.size, bg_color)
    if _has_alpha(img):
        canvas.paste(img, (0, 0), img.convert("RGBA"))
    else:
        canvas.paste(img, (0, 0))
    return canvas


def resize_to_target(img, target_w, target_h, mode,
                     do_trim=AUTO_TRIM,
                     pad_color=PAD_COLOR,
                     trim_color=PAD_COLOR):
    """
    Resize `img` to exactly (target_w, target_h) using one of:
      - 'stretch': direct resize, ignores aspect ratio
      - 'crop':    scale to fill, crop overflow
      - 'fit':     scale to fit inside, pad remainder with pad_color
      - 'smart_fit': content-aware scaling (uses trim_color for margin detection)
    """
    working = img

    if do_trim:
        working = auto_trim(working, bg_color=trim_color)

    source_size = working.size

    if mode == "stretch":
        result = high_quality_resize(working, target_w, target_h)

    elif mode == "crop":
        orig_w, orig_h = working.size
        target_ratio = target_w / target_h
        orig_ratio = orig_w / orig_h

        if orig_ratio > target_ratio:
            new_w = round(orig_h * target_ratio)
            new_h = orig_h
        else:
            new_w = orig_w
            new_h = round(orig_w / target_ratio)

        left = (orig_w - new_w) // 2
        top = (orig_h - new_h) // 2
        cropped = working.crop((left, top, left + new_w, top + new_h))
        result = high_quality_resize(cropped, target_w, target_h)

    elif mode in ("fit", "smart_fit"):
        has_alpha = _has_alpha(working) and PRESERVE_TRANSPARENCY
        orig_w, orig_h = working.size
        target_ratio = target_w / target_h
        orig_ratio = orig_w / orig_h

        if mode == "fit":
            scale = min(target_w / orig_w, target_h / orig_h)
        else:
            safe_w_frac, safe_h_frac = _safe_crop_fractions(
                working, bg_color=trim_color, tolerance=TRIM_TOLERANCE
            )
            fit_scale = min(target_w / orig_w, target_h / orig_h)
            cover_scale = max(target_w / orig_w, target_h / orig_h)

            if orig_ratio > target_ratio:
                allowed = safe_w_frac
            else:
                allowed = safe_h_frac

            ceiling = max(0.0, min(1.0, SMART_FIT_MAX_OVERFLOW))
            allowed = max(0.0, min(1.0, allowed)) * ceiling
            scale = fit_scale + (cover_scale - fit_scale) * allowed

        new_w = max(1, round(orig_w * scale))
        new_h = max(1, round(orig_h * scale))
        scaled = high_quality_resize(working, new_w, new_h)

        if new_w > target_w or new_h > target_h:
            left = max(0, (new_w - target_w) // 2)
            top = max(0, (new_h - target_h) // 2)
            scaled = scaled.crop((left, top, left + min(new_w, target_w), top + min(new_h, target_h)))
            new_w, new_h = scaled.size

        if has_alpha:
            if isinstance(pad_color, tuple) and len(pad_color) == 4:
                canvas = Image.new("RGBA", (target_w, target_h), pad_color)
            else:
                canvas = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        else:
            canvas = Image.new("RGB", (target_w, target_h), pad_color)

        offset = ((target_w - new_w) // 2, (target_h - new_h) // 2)
        canvas.paste(scaled, offset, scaled if has_alpha else None)
        result = canvas

    else:
        raise ValueError(f"Unknown mode: {mode}")

    if SHARPEN_AFTER_RESIZE:
        params = _scaled_sharpen_params(source_size, (target_w, target_h), SHARPEN_PARAMS)
        result = result.filter(ImageFilter.UnsharpMask(**params))

    return result


def finalize_for_save(img, prefer_lossless=False):
    """
    Decide output format/mode.

    prefer_lossless=True forces PNG even when there's no alpha channel.
    Use this for the white/black/transparent background variants: they're
    flat-colour logo graphics with crisp edges and text, and JPEG's
    chroma-subsampled DCT compression visibly smudges exactly that kind of
    content (ringing around hard edges, blotchy flat colour fills) even at
    quality=95. Lossless PNG costs more disk space but actually looks
    right.
    """
    if prefer_lossless:
        if _has_alpha(img):
            return img.convert("RGBA"), "png"
        return img.convert("RGB"), "png"

    if _has_alpha(img) and PRESERVE_TRANSPARENCY:
        return img.convert("RGBA"), "png"

    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")
    return img, "jpg"