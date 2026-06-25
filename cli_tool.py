# cli_tool.py
import os
import argparse
import glob

from PIL import Image

from config import TARGET_SIZES, MODE, AUTO_TRIM, JPEG_QUALITY, JPEG_PROGRESSIVE, PAD_COLOR, ASPECT_LABELS
from resize_core import (
    resize_to_target,
    finalize_for_save,
    extract_foreground_mask,
    compose_background
)


def process_image(input_path, output_dir, do_trim, backgrounds):
    os.makedirs(output_dir, exist_ok=True)

    with Image.open(input_path) as img:
        img.load()
        base_name = os.path.splitext(os.path.basename(input_path))[0]

        if "all" in backgrounds:
            backgrounds = ["original", "transparent", "white", "black"]

        # Mode is always smart_fit
        mode = "smart_fit"

        for bg_name in backgrounds:
            if bg_name == "transparent":
                working = extract_foreground_mask(img, bg_color=PAD_COLOR)
                if working.getbbox():
                    working = working.crop(working.getbbox())
                trim_flag = False
                pad_color = (0, 0, 0, 0)
            elif bg_name == "white":
                working = extract_foreground_mask(img, bg_color=PAD_COLOR)
                if working.getbbox():
                    working = working.crop(working.getbbox())
                working = compose_background(working, (255, 255, 255))
                trim_flag = False
                pad_color = (255, 255, 255)
            elif bg_name == "black":
                working = extract_foreground_mask(img, bg_color=PAD_COLOR)
                if working.getbbox():
                    working = working.crop(working.getbbox())
                working = compose_background(working, (0, 0, 0))
                trim_flag = False
                pad_color = (0, 0, 0)
            else:  # "original"
                working = img
                trim_flag = do_trim
                pad_color = PAD_COLOR

            for w, h in TARGET_SIZES:
                label = ASPECT_LABELS.get((w, h), f"{w}x{h}")
                resized = resize_to_target(
                    working, w, h, mode,
                    do_trim=trim_flag,
                    pad_color=pad_color,
                    trim_color=PAD_COLOR
                )
                final_img, ext = finalize_for_save(resized)

                if bg_name != "original":
                    out_name = f"{base_name}_{bg_name}_{label}.{ext}"
                else:
                    out_name = f"{base_name}_{label}.{ext}"

                out_path = os.path.join(output_dir, out_name)

                if ext == "png":
                    final_img.save(out_path, optimize=True)
                else:
                    final_img.save(
                        out_path,
                        quality=JPEG_QUALITY,
                        subsampling=0,
                        optimize=True,
                        progressive=JPEG_PROGRESSIVE,
                    )

                print(f"✅ Saved {out_path}  ({label}, {ext}, bg:{bg_name})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Resize an image using smart_fit to exact target sizes defined in config.py."
    )
    parser.add_argument("image", nargs="?", help="Path to a single high-resolution source image")
    parser.add_argument("-i", "--input-dir", help="Process all images in a folder (ignores single image)")
    parser.add_argument("-o", "--output", default="output", help="Output folder (default: output)")
    parser.add_argument(
        "--no-trim",
        action="store_true",
        help="Disable auto-trimming of existing solid-colour borders before resizing"
    )
    parser.add_argument(
        "--bg", "--backgrounds",
        nargs="+",
        choices=["original", "transparent", "white", "black", "all"],
        default=["original"],
        help=(
            "Background variants to generate. Use 'all' to generate original, transparent, white, and black. "
            "Note: For transparent/white/black to work correctly, set PAD_COLOR in config.py to your source image's background colour."
        )
    )

    args = parser.parse_args()

    # Determine which images to process
    if args.input_dir:
        image_exts = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.bmp", "*.tiff")
        image_files = []
        for ext in image_exts:
            image_files.extend(glob.glob(os.path.join(args.input_dir, ext)))
        image_files = sorted(set(image_files))  # deduplicate and sort
        if not image_files:
            print(f"No images found in {args.input_dir}")
            exit(1)
        print(f"Found {len(image_files)} image(s) in {args.input_dir}")
    else:
        if not args.image:
            parser.error("Either a single image path or --input-dir must be provided")
        image_files = [args.image]

    # Process each image
    for img_path in image_files:
        print(f"\n--- Processing: {img_path} ---")
        try:
            # Use a per‑image subfolder to avoid name collisions
            base_name = os.path.splitext(os.path.basename(img_path))[0]
            per_image_output = os.path.join(args.output, base_name)

            process_image(
                img_path,
                per_image_output,
                do_trim=(AUTO_TRIM and not args.no_trim),
                backgrounds=args.bg
            )
        except Exception as e:
            print(f"❌ Failed to process {img_path}: {e}")