import os
from concurrent.futures import ThreadPoolExecutor

from services.annotation import validate_mask_file
from services.paths import dataset_images_dir, dataset_masks_dir
from services.constants import IMAGE_EXTENSIONS


_VALIDATION_CACHE = {}


def path_signature(path):
    try:
        stat = path.stat()
    except OSError:
        return str(path), False, 0, 0
    return str(path), True, stat.st_mtime_ns, stat.st_size


def cached_validate_mask_file(seg_path, mask_path):
    cache_key = (path_signature(seg_path), path_signature(mask_path))
    cached = _VALIDATION_CACHE.get(cache_key)
    if cached is not None:
        return dict(cached)
    validation = validate_mask_file(seg_path, mask_path)
    _VALIDATION_CACHE[cache_key] = dict(validation)
    return validation


def conversion_row_for_image_path(image_path, masks_dir=None):
    masks_dir = masks_dir or image_path.parent
    seg_path = masks_dir / f"{image_path.stem}_seg.npy"
    tif_mask_path = masks_dir / f"{image_path.stem}_masks.tif"
    tiff_mask_path = masks_dir / f"{image_path.stem}_masks.tiff"
    mask_path = tif_mask_path if tif_mask_path.exists() else tiff_mask_path
    had_mask_file = seg_path.exists() or mask_path.exists()
    validation = cached_validate_mask_file(seg_path, mask_path)
    has_mask = validation["valid"]
    removed_invalid_mask = False
    if had_mask_file and not has_mask and validation["status"] in {"Mascara vazia", "Mascara pequena"}:
        for path in {seg_path, tif_mask_path, tiff_mask_path}:
            if path.exists():
                try:
                    path.unlink()
                    removed_invalid_mask = True
                except OSError:
                    pass
        mask_path = tif_mask_path if tif_mask_path.exists() else tiff_mask_path
        validation = cached_validate_mask_file(seg_path, mask_path)
        has_mask = validation["valid"]
    status = "Com mascara" if has_mask else "Sem mascara"
    return {
        "image": image_path.name,
        "status": status,
        "image_path": str(image_path),
        "seg_path": str(seg_path),
        "tif_mask_path": str(mask_path),
        "mask_pixels": validation["pixel_count"],
        "mask_objects": validation["object_count"],
        "removed_invalid_mask": removed_invalid_mask,
        "validation_status": validation["status"],
    }


def scan_conversion_input_rows(config):
    input_dir = dataset_images_dir(config)
    masks_dir = dataset_masks_dir(config)
    input_dir.mkdir(parents=True, exist_ok=True)
    masks_dir.mkdir(parents=True, exist_ok=True)
    image_files = []
    for ext in IMAGE_EXTENSIONS:
        image_files.extend(input_dir.glob(f"*{ext}"))

    image_files = sorted(
        {path.resolve(): path for path in image_files}.values(),
        key=lambda path: path.name.lower(),
    )
    image_files = [
        path
        for path in image_files
        if not path.stem.endswith("_masks") and not path.stem.endswith("_pred_mask")
    ]
    if len(image_files) <= 1:
        return [
            conversion_row_for_image_path(image_path, masks_dir)
            for image_path in image_files
        ]

    max_workers = min(8, len(image_files), os.cpu_count() or 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        return list(
            executor.map(
                lambda image_path: conversion_row_for_image_path(image_path, masks_dir),
                image_files,
            )
        )
