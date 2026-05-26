from services.annotation import validate_mask_file
from services.paths import dataset_images_dir, dataset_masks_dir


IMAGE_EXTENSIONS = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]


def conversion_row_for_image_path(image_path, masks_dir=None):
    masks_dir = masks_dir or image_path.parent
    seg_path = masks_dir / f"{image_path.stem}_seg.npy"
    tif_mask_path = masks_dir / f"{image_path.stem}_masks.tif"
    tiff_mask_path = masks_dir / f"{image_path.stem}_masks.tiff"
    mask_path = tif_mask_path if tif_mask_path.exists() else tiff_mask_path
    had_mask_file = seg_path.exists() or mask_path.exists()
    validation = validate_mask_file(seg_path, mask_path)
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
        validation = validate_mask_file(seg_path, mask_path)
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
    return [
        conversion_row_for_image_path(image_path, masks_dir)
        for image_path in image_files
    ]
