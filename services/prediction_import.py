from pathlib import Path
import re
import shutil

import numpy as np
import tifffile as tiff
from PIL import Image


SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}


def path_matches_keyword(path, keyword):
    return bool(keyword and keyword in str(path).lower())


def collect_image_paths_from_folder(source_dir, keyword="", recursive=True):
    image_paths = []
    for root, dirs, files in __import__("os").walk(source_dir):
        dirs[:] = [
            dirname
            for dirname in dirs
            if not path_matches_keyword(Path(root) / dirname, keyword)
        ]
        for file_name in files:
            source_path = Path(root) / file_name
            if path_matches_keyword(source_path, keyword):
                continue
            image_paths.append(source_path)
        if not recursive:
            dirs[:] = []
    return image_paths


def image_array_to_grayscale(array):
    array = np.asarray(array)
    if array.ndim < 3:
        return array
    if array.shape[-1] >= 3:
        rgb = array[..., :3].astype(np.float32)
        gray = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
        if np.issubdtype(array.dtype, np.integer):
            gray = np.clip(gray, np.iinfo(array.dtype).min, np.iinfo(array.dtype).max)
            return gray.astype(array.dtype)
        return gray.astype(array.dtype)
    return np.squeeze(array)


def clean_import_name_part(value):
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
    value = re.sub(r"_+", "_", value).strip("._ ")
    return value or "imagem"


def prediction_import_output_stem(source_path, source_root=None):
    source_path = Path(source_path)
    parts = []
    if source_root is not None:
        try:
            relative_parent = source_path.parent.relative_to(source_root)
            parts = [part for part in relative_parent.parts if part not in {"", "."}]
        except ValueError:
            parts = []
    parts.append(source_path.stem)
    return "_".join(clean_import_name_part(part) for part in parts if part)


def available_import_destination(target_dir, stem, used_destinations=None):
    used_destinations = used_destinations or set()
    destination = target_dir / f"{stem}.tif"
    if not destination.exists() and destination.name.lower() not in used_destinations:
        return destination

    counter = 1
    while True:
        candidate = target_dir / f"{stem}_{counter}.tif"
        if not candidate.exists() and candidate.name.lower() not in used_destinations:
            return candidate
        counter += 1


def collect_prediction_image_candidates(paths, keyword=""):
    skipped = 0
    image_candidates = []
    for src in sorted({Path(path) for path in paths}, key=lambda path: str(path).lower()):
        if not src.is_file():
            skipped += 1
            continue
        if path_matches_keyword(src, keyword):
            skipped += 1
            continue
        if src.stem.endswith("_masks") or src.stem.endswith("_pred_mask") or src.stem.endswith("_pred_masks"):
            skipped += 1
            continue
        if src.name.endswith("_seg.npy"):
            skipped += 1
            continue

        suffix = src.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            skipped += 1
            continue

        image_candidates.append(src)
    return image_candidates, skipped


def import_prediction_image(src, dst, convert_to_grayscale=False):
    suffix = src.suffix.lower()
    if suffix == ".tif" and not convert_to_grayscale:
        shutil.copy2(src, dst)
        return "copied"
    if suffix in {".tif", ".tiff"}:
        image_array = tiff.imread(src)
        if convert_to_grayscale:
            image_array = image_array_to_grayscale(image_array)
        tiff.imwrite(dst, image_array, compression="zlib")
        return "converted"

    with Image.open(src) as image:
        if convert_to_grayscale:
            image = image.convert("L")
        elif image.mode == "P":
            image = image.convert("RGB")
        tiff.imwrite(dst, np.asarray(image), compression="zlib")
    return "converted"
