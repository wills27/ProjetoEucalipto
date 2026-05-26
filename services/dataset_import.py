import shutil

import numpy as np
import tifffile as tiff
from PIL import Image

from services.conversion_scan import IMAGE_EXTENSIONS


SUPPORTED_CONVERSION_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}


def import_dataset_folder_contents(source_dir, target_dir, mask_target_dir=None):
    target_dir.mkdir(parents=True, exist_ok=True)
    mask_target_dir = mask_target_dir or target_dir
    mask_target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    converted = 0
    skipped = 0
    errors = []
    image_candidates = {}

    for src in sorted(source_dir.iterdir()):
        if not src.is_file():
            continue

        if src.name.endswith("_seg.npy"):
            dst = mask_target_dir / src.name
            if dst.exists():
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
            continue

        if src.stem.endswith("_masks"):
            if src.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            dst = mask_target_dir / src.name
            if dst.exists():
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
            continue

        if src.stem.endswith("_pred_mask"):
            continue

        if src.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        current = image_candidates.get(src.stem)
        if current is None:
            image_candidates[src.stem] = src
            continue

        current_is_tif = current.suffix.lower() in {".tif", ".tiff"}
        src_is_tif = src.suffix.lower() in {".tif", ".tiff"}
        if src_is_tif and not current_is_tif:
            image_candidates[src.stem] = src

    for src in sorted(image_candidates.values()):
        if src.suffix.lower() in {".tif", ".tiff"}:
            dst = target_dir / src.name
            if dst.exists():
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
            continue

        dst = target_dir / f"{src.stem}.tif"
        if dst.exists():
            skipped += 1
            continue

        try:
            with Image.open(src) as image:
                if image.mode == "P":
                    image = image.convert("RGB")
                tiff.imwrite(dst, np.asarray(image), compression="zlib")
            converted += 1
        except Exception as exc:
            skipped += 1
            errors.append(f"{src}: {exc}")

    return {
        "copied": copied,
        "converted": converted,
        "skipped": skipped,
        "errors": errors,
    }


def convert_dataset_images_to_tif(input_dir):
    input_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped = 0
    failed = 0
    errors = []

    for image_path in sorted(input_dir.iterdir()):
        if not image_path.is_file():
            continue
        if image_path.name.endswith("_seg.npy") or image_path.stem.endswith("_masks") or image_path.stem.endswith("_pred_mask"):
            continue

        suffix = image_path.suffix.lower()
        if suffix not in SUPPORTED_CONVERSION_EXTENSIONS:
            continue

        if suffix in {".tif", ".tiff"}:
            skipped += 1
            continue

        tif_path = image_path.with_suffix(".tif")
        if tif_path.exists():
            if image_path.exists():
                image_path.unlink()
            skipped += 1
            continue

        try:
            with Image.open(image_path) as image:
                if image.mode == "P":
                    image = image.convert("RGB")
                tiff.imwrite(tif_path, np.asarray(image), compression="zlib")
            image_path.unlink()
            converted += 1
        except Exception as exc:
            failed += 1
            errors.append(f"{image_path}: {exc}")

    return {
        "converted": converted,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
    }
