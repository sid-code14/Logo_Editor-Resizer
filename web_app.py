import io
import os
import zipfile
import threading
import time
from datetime import datetime

import streamlit as st
from PIL import Image

from config import TARGET_SIZES, AUTO_TRIM, JPEG_QUALITY, JPEG_PROGRESSIVE, PAD_COLOR, ASPECT_LABELS
from resize_core import (
    resize_to_target,
    finalize_for_save,
    extract_foreground_mask,
    compose_background,
    detect_background_color,
    remove_background_ai,
)


def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip("#")
    return tuple(int(hex_str[i:i+2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def log_message(msg):
    """Append a timestamped message to the session log."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    if "logs" not in st.session_state:
        st.session_state.logs = []
    st.session_state.logs.append(f"[{timestamp}] {msg}")
    if len(st.session_state.logs) > 1000:
        st.session_state.logs = st.session_state.logs[-1000:]


def process_with_ai(image, log_func):
    """Run rembg background removal with a progress bar."""
    home = os.path.expanduser("~")
    cache_dir = os.path.join(home, ".u2net")
    model_path = os.path.join(cache_dir, "u2net.onnx")
    if os.path.exists(model_path):
        log_func(f"🧠 AI model 'u2net' loaded from cache: {model_path}")
    else:
        log_func(f"🧠 AI model 'u2net' not cached - will download (~176MB) on first use.")

    status_placeholder = st.empty()
    progress_bar = st.progress(0, text="Initializing AI...")
    result_container = []
    error_container = []
    start_time = time.time()

    log_func(f"🧠 Starting AI background removal on {image.size[0]}×{image.size[1]} image...")

    def ai_thread():
        try:
            result = remove_background_ai(image)
            result_container.append(result)
        except Exception as e:
            error_container.append(str(e))

    thread = threading.Thread(target=ai_thread)
    thread.start()

    i = 0
    while thread.is_alive():
        i = (i % 99) + 1
        elapsed = time.time() - start_time
        progress_bar.progress(i, text=f"🧠 AI processing... {elapsed:.1f}s")
        time.sleep(0.1)

    if error_container:
        log_func(f"❌ AI failed: {error_container[0]}")
        st.error(f"AI failed: {error_container[0]}")
        st.stop()

    elapsed_total = time.time() - start_time
    log_func(f"✅ AI complete in {elapsed_total:.1f} seconds")
    progress_bar.progress(100, text="✅ AI complete! ({:.1f}s)".format(elapsed_total))
    time.sleep(0.3)
    status_placeholder.empty()
    progress_bar.empty()

    return result_container[0]


def get_settings_hash(use_ai, bg_options, do_trim, source_bg_hex):
    """Hash of settings to detect changes (used for logging only)."""
    return hash((use_ai, tuple(sorted(bg_options)), do_trim, source_bg_hex))


def display_results():
    """Show generated images and download buttons from session state."""
    if "generated_images" not in st.session_state or not st.session_state.generated_images:
        st.info("No results yet. Press 'Generate All Sizes' to start.")
        return

    # Group by source filename, then by background type
    grouped = {}
    for item in st.session_state.generated_images:
        # item structure: (final_img, img_bytes, label, ext, mime, bg_name, zip_filename, source_file_name)
        source = item[7] if len(item) > 7 else "unknown"
        bg_name = item[5]
        if source not in grouped:
            grouped[source] = {}
        if bg_name not in grouped[source]:
            grouped[source][bg_name] = []
        grouped[source][bg_name].append(item)

    # Display per source image
    for source_name, bg_dict in grouped.items():
        st.subheader(f"Source: {source_name}")
        for bg_name, items in bg_dict.items():
            st.markdown(f"**Background: {bg_name.capitalize()}**")
            cols = st.columns(len(TARGET_SIZES))
            for i, item in enumerate(items):
                with cols[i]:
                    final_img, img_bytes, label, ext, mime, _, zip_filename, _ = item
                    st.image(final_img, caption=label, use_container_width=True)
                    st.download_button(
                        label=f"⬇️ {label}",
                        data=img_bytes,
                        file_name=zip_filename,
                        mime=mime,
                        key=f"dl_{source_name}_{bg_name}_{label}_{ext}_{i}"
                    )
        st.divider()

    if "generated_zip" in st.session_state:
        zip_buffer = st.session_state.generated_zip
        st.download_button(
            label="📦 Download All as ZIP",
            data=zip_buffer,
            file_name=f"{st.session_state.generated_base_name}_all_resized.zip",
            mime="application/zip",
        )


# ---------- Page Config ----------
st.set_page_config(page_title="Image Resizer", page_icon="📐")

st.title("📐 Image Resizer – Exact Sizes")
st.write("Upload one or more high-resolution images and get them in 5 fixed sizes using **smart_fit** mode – content‑aware scaling that minimizes padding and protects your artwork.")

# Initialize session state
if "logs" not in st.session_state:
    st.session_state.logs = ["Awaiting image upload..."]
if "generated_images" not in st.session_state:
    st.session_state.generated_images = []
if "generated_zip" not in st.session_state:
    st.session_state.generated_zip = None
if "generated_base_name" not in st.session_state:
    st.session_state.generated_base_name = ""

# ---------- File Upload (multiple files) ----------
uploaded_files = st.file_uploader(
    "Choose one or more images",
    type=["jpg", "jpeg", "png", "webp"],
    accept_multiple_files=True
)

if uploaded_files:
    # Show thumbnails of uploaded images
    st.caption(f"{len(uploaded_files)} image(s) uploaded")
    thumb_cols = st.columns(min(4, len(uploaded_files)))
    for idx, file in enumerate(uploaded_files):
        with thumb_cols[idx % 4]:
            img = Image.open(file)
            st.image(img, caption=file.name, use_container_width=True)

    # Mode fixed to smart_fit
    mode = "smart_fit"
    st.info(f"🔄 Resize mode: **{mode}** (content‑aware, auto‑adjusts to fit each aspect ratio)")

    do_trim = st.checkbox(
        "Auto-trim existing borders before resizing",
        value=AUTO_TRIM,
        help="Turn this on if your source images already have solid-colour padding baked in."
    )

    use_ai = st.checkbox(
        "Use AI background removal (slower, but handles complex images where foreground and background share colours)",
        value=False,
        help="When generating Transparent/White/Black backgrounds, use a deep-learning model."
    )

    st.subheader("Background variants")
    bg_options = st.multiselect(
        "Generate these backgrounds",
        options=["Original", "Transparent", "White", "Black"],
        default=["Original"]
    )

    # Use the first uploaded image to auto-detect background colour (the setting applies to all)
    with Image.open(uploaded_files[0]) as first_img:
        first_img.load()
        default_hex = rgb_to_hex(detect_background_color(first_img))
    source_bg_hex = st.color_picker(
        "Source background colour to remove (for Transparent / White / Black variants, used only if AI is off)",
        default_hex,
        help="Auto-detected from the first image's edges. Override if it picked the wrong colour."
    )
    source_bg_rgb = hex_to_rgb(source_bg_hex)

    # (Optional: log when settings change, but do NOT clear results)
    current_hash = get_settings_hash(use_ai, tuple(bg_options), do_trim, source_bg_hex)
    if "last_settings_hash" not in st.session_state:
        st.session_state.last_settings_hash = None
    if st.session_state.last_settings_hash != current_hash:
        if st.session_state.generated_images:
            log_message("⚙️ Settings changed – existing results remain. Press 'Generate All Sizes' to update them.")
        st.session_state.last_settings_hash = current_hash

    if st.button("Generate All Sizes"):
        # Start fresh logs for this run
        st.session_state.logs = []
        log_message(f"🚀 Starting batch generation for {len(uploaded_files)} image(s)")
        log_message(f"📐 Resize mode: {mode}")
        log_message(f"🎨 Backgrounds: {', '.join(bg_options)}")
        if use_ai:
            log_message("🧠 AI background removal enabled")

        # Collect all generated images and a master ZIP
        all_resized_images = []
        master_zip_buffer = io.BytesIO()
        used_folder_names = {}  # Track folder names to avoid ZIP collisions

        with zipfile.ZipFile(master_zip_buffer, "w", zipfile.ZIP_DEFLATED) as master_zf:
            for file_idx, uploaded_file in enumerate(uploaded_files, start=1):
                file_name = uploaded_file.name
                orig_base = os.path.splitext(file_name)[0]

                # Create a unique folder name inside the ZIP
                if orig_base in used_folder_names:
                    used_folder_names[orig_base] += 1
                    folder_name = f"{orig_base}_{used_folder_names[orig_base]}"
                else:
                    used_folder_names[orig_base] = 0
                    folder_name = orig_base

                log_message(f"\n{'='*40}")
                log_message(f"📷 Processing image {file_idx}/{len(uploaded_files)}: {file_name} → ZIP folder: {folder_name}/")

                try:
                    original = Image.open(uploaded_file)
                    original.load()
                except Exception as e:
                    log_message(f"❌ Failed to open {file_name}: {e}")
                    continue

                # Process each background variant
                for bg_label in bg_options:
                    bg_name = bg_label.lower()
                    log_message(f"--- Background: {bg_name.capitalize()} ---")

                    # Prepare working image for this background
                    if bg_name == "transparent":
                        if use_ai:
                            working = process_with_ai(original, log_message)
                        else:
                            log_message(f"Removing background colour {source_bg_hex} using colour‑based extraction...")
                            working = extract_foreground_mask(original, bg_color=source_bg_rgb)
                        if working.getbbox():
                            old_size = working.size
                            working = working.crop(working.getbbox())
                            log_message(f"Cropped transparent margins: {old_size[0]}×{old_size[1]} → {working.size[0]}×{working.size[1]}")
                        else:
                            log_message("⚠️ No non‑transparent content found – image may be entirely transparent.")
                        trim_flag = False
                        pad_color = (0, 0, 0, 0)

                    elif bg_name == "white":
                        if use_ai:
                            working = process_with_ai(original, log_message)
                            if working.getbbox():
                                old_size = working.size
                                working = working.crop(working.getbbox())
                                log_message(f"Cropped transparent margins: {old_size[0]}×{old_size[1]} → {working.size[0]}×{working.size[1]}")
                            log_message("Composing onto white background...")
                            working = compose_background(working, (255, 255, 255))
                        else:
                            log_message(f"Removing background colour {source_bg_hex} using colour‑based extraction...")
                            working = extract_foreground_mask(original, bg_color=source_bg_rgb)
                            if working.getbbox():
                                old_size = working.size
                                working = working.crop(working.getbbox())
                                log_message(f"Cropped transparent margins: {old_size[0]}×{old_size[1]} → {working.size[0]}×{working.size[1]}")
                            log_message("Composing onto white background...")
                            working = compose_background(working, (255, 255, 255))
                        trim_flag = False
                        pad_color = (255, 255, 255)

                    elif bg_name == "black":
                        if use_ai:
                            working = process_with_ai(original, log_message)
                            if working.getbbox():
                                old_size = working.size
                                working = working.crop(working.getbbox())
                                log_message(f"Cropped transparent margins: {old_size[0]}×{old_size[1]} → {working.size[0]}×{working.size[1]}")
                            log_message("Composing onto black background...")
                            working = compose_background(working, (0, 0, 0))
                        else:
                            log_message(f"Removing background colour {source_bg_hex} using colour‑based extraction...")
                            working = extract_foreground_mask(original, bg_color=source_bg_rgb)
                            if working.getbbox():
                                old_size = working.size
                                working = working.crop(working.getbbox())
                                log_message(f"Cropped transparent margins: {old_size[0]}×{old_size[1]} → {working.size[0]}×{working.size[1]}")
                            log_message("Composing onto black background...")
                            working = compose_background(working, (0, 0, 0))
                        trim_flag = False
                        pad_color = (0, 0, 0)

                    else:  # "original"
                        log_message("Using original image as‑is (no background removal).")
                        working = original
                        trim_flag = do_trim
                        pad_color = PAD_COLOR
                        if trim_flag:
                            log_message("Auto‑trim enabled – will trim solid borders before resizing.")

                    # Resize to each target size
                    for w, h in TARGET_SIZES:
                        label = ASPECT_LABELS.get((w, h), f"{w}x{h}")
                        log_message(f"  Resizing to {w}×{h} ({label}) with mode '{mode}'...")
                        resized = resize_to_target(
                            working, w, h, mode,
                            do_trim=trim_flag,
                            pad_color=pad_color,
                            trim_color=PAD_COLOR
                        )
                        final_img, ext = finalize_for_save(resized, prefer_lossless=(bg_name != "original"))

                        img_bytes = io.BytesIO()
                        if ext == "png":
                            final_img.save(img_bytes, format="PNG", optimize=True)
                            mime = "image/png"
                        else:
                            final_img.save(
                                img_bytes,
                                format="JPEG",
                                quality=JPEG_QUALITY,
                                subsampling=0,
                                optimize=True,
                                progressive=JPEG_PROGRESSIVE,
                            )
                            mime = "image/jpeg"
                        img_bytes.seek(0)

                        # Determine ZIP path: folder_name / file_name
                        if bg_name != "original":
                            zip_filename = f"{orig_base}_{bg_name}_{label}.{ext}"
                        else:
                            zip_filename = f"{orig_base}_{label}.{ext}"

                        zip_path = f"{folder_name}/{zip_filename}"
                        master_zf.writestr(zip_path, img_bytes.getvalue())
                        log_message(f"    ✅ Saved {zip_path} ({img_bytes.getbuffer().nbytes / 1024:.1f} KB)")

                        img_bytes.seek(0)
                        # Store with source file name for display grouping
                        all_resized_images.append(
                            (final_img, img_bytes, label, ext, mime, bg_name, zip_filename, file_name)
                        )

        master_zip_buffer.seek(0)
        log_message(f"\n📦 Master ZIP archive created with {len(all_resized_images)} images (organised in subfolders).")

        # Update session state
        st.session_state.generated_images = all_resized_images
        st.session_state.generated_zip = master_zip_buffer
        st.session_state.generated_base_name = "batch"  # generic name for the master ZIP
        st.session_state.last_settings_hash = current_hash

        log_message("✅ All done!")

    # Display results (if any)
    display_results()

else:
    # No files uploaded – clear results and show waiting message
    st.session_state.generated_images = []
    st.session_state.generated_zip = None
    st.session_state.generated_base_name = ""
    if not st.session_state.logs:
        st.session_state.logs = ["Awaiting image upload..."]

