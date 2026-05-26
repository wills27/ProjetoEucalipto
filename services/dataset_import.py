import shutil

import numpy as np
import tifffile as tiff
from PIL import Image

from services.conversion_scan import IMAGE_EXTENSIONS
from services.constants import SUPPORTED_CONVERSION_EXTENSIONS


def import_dataset_folder_contents(source_dir, target_dir, mask_target_dir=None):
    target_dir.mkdir(parents=True, exist_ok=True)
    mask_target_dir = mask_target_dir or target_dir
    mask_target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    converted = 0
    masks_converted = 0
    skipped = 0
    errors = []
    image_candidates = {}

    for src in sorted(source_dir.iterdir()):
        if not src.is_file():
            continue

        if src.name.endswith("_seg.npy"):
            # convert _seg.npy (dict with 'masks') to _masks.tif
            try:
                data = np.load(src, allow_pickle=True)
                # data may be an array or a dict-like object
                masks = None
                if hasattr(data, "item"):
                    try:
                        obj = data.item() if data.size == 1 else data
                    except Exception:
                        obj = data
                    if isinstance(obj, dict) and "masks" in obj:
                        masks = obj.get("masks")
                if masks is None:
                    # fallback: try to interpret the file as a plain array
                    try:
                        masks = np.asarray(data)
                    except Exception:
                        masks = None

                if masks is None:
                    skipped += 1
                    errors.append(f"{src}: no 'masks' found")
                    continue

                base_stem = src.stem[:-4] if src.stem.endswith("_seg") else src.stem
                dst = mask_target_dir / f"{base_stem}_masks.tif"
                if dst.exists():
                    # already have a tif mask, remove seg if present
                    try:
                        src.unlink()
                    except Exception:
                        pass
                    skipped += 1
                    continue

                # ensure array type
                mask_arr = np.asarray(masks).astype(np.uint16)
                tiff.imwrite(dst, mask_arr, compression="zlib")
                # remove original seg file to enforce TIFF standard
                try:
                    src.unlink()
                except Exception:
                    pass
                masks_converted += 1
            except Exception as exc:
                skipped += 1
                errors.append(f"{src}: {exc}")
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
        "masks_converted": masks_converted,
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


def convert_seg_npy_masks_in_dir(masks_dir):
    masks_dir.mkdir(parents=True, exist_ok=True)
    converted = 0
    skipped = 0
    errors = []
    for seg_path in sorted(masks_dir.glob("*_seg.npy")):
        try:
            data = np.load(seg_path, allow_pickle=True)
            masks = None
            if hasattr(data, "item"):
                try:
                    obj = data.item() if data.size == 1 else data
                except Exception:
                    obj = data
                if isinstance(obj, dict) and "masks" in obj:
                    masks = obj.get("masks")
            if masks is None:
                try:
                    masks = np.asarray(data)
                except Exception:
                    masks = None
            if masks is None:
                skipped += 1
                errors.append(f"{seg_path}: no 'masks' found")
                continue
            base_stem = seg_path.stem[:-4] if seg_path.stem.endswith("_seg") else seg_path.stem
            dst = masks_dir / f"{base_stem}_masks.tif"
            if dst.exists():
                try:
                    seg_path.unlink()
                except Exception:
                    pass
                skipped += 1
                continue
            mask_arr = np.asarray(masks).astype(np.uint16)
            tiff.imwrite(dst, mask_arr, compression="zlib")
            try:
                seg_path.unlink()
            except Exception:
                pass
            converted += 1
        except Exception as exc:
            errors.append(f"{seg_path}: {exc}")
    return {"converted": converted, "skipped": skipped, "errors": errors}
