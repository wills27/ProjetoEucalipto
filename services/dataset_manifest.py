from pathlib import Path

from services.conversion_scan import IMAGE_EXTENSIONS
from services.dataset_plan import load_plan, save_plan
from services.paths import (
    active_project_dir,
    dataset_images_dir,
    dataset_masks_dir,
    dataset_plan_path,
)


MASK_SUFFIXES = ["_seg.npy", "_masks.tif", "_masks.tiff"]


def image_mask_path(image_path):
    for folder in [dataset_masks_dir_from_image(image_path), image_path.parent]:
        for suffix in MASK_SUFFIXES:
            mask_path = folder / f"{image_path.stem}{suffix}"
            if mask_path.exists():
                return mask_path
    return None


def dataset_masks_dir_from_image(image_path):
    data_dir = image_path.parent.parent if image_path.parent.name == "images" else None
    if data_dir is not None:
        return data_dir / "masks"
    return image_path.parent


def conversion_image_path(config, image_name):
    image_stem = Path(image_name).stem
    folder = dataset_images_dir(config)
    named_path = folder / image_name
    if named_path.exists():
        return named_path
    for suffix in IMAGE_EXTENSIONS:
        image_path = folder / f"{image_stem}{suffix}"
        if image_path.exists():
            return image_path
    return None


def manifest_image_path(config, entry):
    explicit_path = entry.get("image_path")
    if explicit_path:
        image_path = Path(explicit_path)
        if not image_path.is_absolute():
            image_path = active_project_dir(config) / image_path
        if image_path.exists():
            return image_path

    image_name = entry.get("image", "")
    image_path = conversion_image_path(config, image_name)
    return image_path


def manifest_mask_path(config, entry, image_path=None):
    explicit_path = entry.get("mask_path")
    if explicit_path:
        mask_path = Path(explicit_path)
        if not mask_path.is_absolute():
            mask_path = active_project_dir(config) / mask_path
        if mask_path.exists():
            return mask_path

    image_path = image_path or manifest_image_path(config, entry)
    if image_path is not None:
        for folder in [dataset_masks_dir(config), image_path.parent]:
            for suffix in MASK_SUFFIXES:
                mask_path = folder / f"{image_path.stem}{suffix}"
                if mask_path.exists():
                    return mask_path
    return None


def image_has_mask(config, entry, image_path=None):
    return manifest_mask_path(config, entry, image_path=image_path) is not None


def update_plan_entry_group(config, image_stem, group, include=True, status=None):
    plan_path = dataset_plan_path(config)
    plan = load_plan(plan_path)
    target_key = None
    for image_name in plan:
        if Path(image_name).stem == image_stem:
            target_key = image_name
            break

    if target_key is None:
        image_path = conversion_image_path(config, f"{image_stem}.tif")
        if image_path is None:
            return None
        target_key = image_path.name
        plan[target_key] = {"image": target_key}

    entry = plan[target_key]
    entry["image"] = target_key
    entry["include"] = include
    entry["group"] = group
    if status is None:
        image_path = manifest_image_path(config, entry)
        status = "Com mascara" if image_has_mask(config, entry, image_path=image_path) else "Sem mascara"
    entry["status"] = status
    save_plan(plan_path, list(plan.values()))
    return entry


def plan_entries_for_group(config, group, include_only=True, require_mask=False):
    entries = []
    for entry in load_plan(dataset_plan_path(config)).values():
        if include_only and not entry.get("include", True):
            continue
        if entry.get("group", "uncategorized") != group:
            continue
        image_path = manifest_image_path(config, entry)
        if image_path is None:
            continue
        mask_path = manifest_mask_path(config, entry, image_path=image_path)
        if require_mask and mask_path is None:
            continue
        entries.append(
            {
                "entry": entry,
                "image_path": image_path,
                "mask_path": mask_path,
                "stem": image_path.stem,
            }
        )
    return entries
