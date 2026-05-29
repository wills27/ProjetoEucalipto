import shutil
from pathlib import Path

import numpy as np
import tifffile as tiff
from PIL import Image

from services.conversion_scan import IMAGE_EXTENSIONS
from services.constants import SUPPORTED_CONVERSION_EXTENSIONS
from services.prediction_import import available_import_destination, clean_import_name_part, image_array_to_grayscale, path_matches_keyword


def dataset_import_output_stem(source_path, source_root=None, use_folder_prefix=False):
    source_path = Path(source_path)
    stem = source_path.stem[:-4] if source_path.stem.endswith("_seg") else source_path.stem
    if not use_folder_prefix or source_root is None:
        return clean_import_name_part(stem)

    parts = []
    try:
        relative_parent = source_path.parent.relative_to(source_root)
        parts = [part for part in relative_parent.parts if part not in {"", "."}]
    except ValueError:
        parts = []
    parts.append(stem)
    return "_".join(clean_import_name_part(part) for part in parts if part)


def import_dataset_folder_contents(
    source_dir,
    target_dir,
    mask_target_dir=None,
    convert_to_grayscale=False,
    recursive=True,
    keyword="",
    use_folder_prefix=False,
    progress_callback=None,
):
    target_dir.mkdir(parents=True, exist_ok=True)
    mask_target_dir = mask_target_dir or target_dir
    mask_target_dir.mkdir(parents=True, exist_ok=True)

    copied = 0
    converted = 0
    masks_converted = 0
    skipped = 0
    errors = []
    image_candidates = {}
    mask_sources = []

    source_paths = list(source_dir.rglob("*") if recursive else source_dir.iterdir())
    for src in sorted(source_paths, key=lambda path: str(path).lower()):
        if not src.is_file():
            continue
        if path_matches_keyword(src, keyword):
            skipped += 1
            continue

        if src.name.endswith("_seg.npy"):
            mask_sources.append(src)
            continue

        if src.stem.endswith("_masks"):
            if src.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            mask_sources.append(src)
            continue

        if src.stem.endswith("_pred_mask"):
            continue

        if src.suffix.lower() not in IMAGE_EXTENSIONS:
            continue

        dst_stem = dataset_import_output_stem(src, source_dir, use_folder_prefix)
        current = image_candidates.get(dst_stem)
        if current is None:
            image_candidates[dst_stem] = src
            continue

        current_is_tif = current.suffix.lower() in {".tif", ".tiff"}
        src_is_tif = src.suffix.lower() in {".tif", ".tiff"}
        if src_is_tif and not current_is_tif:
            image_candidates[dst_stem] = src

    total_steps = len(mask_sources) + len(image_candidates)
    current_step = 0

    def report_progress(detail):
        if progress_callback:
            progress_callback(current_step, total_steps or 1, detail)

    for src in sorted(mask_sources, key=lambda path: str(path).lower()):
        current_step += 1
        report_progress(f"Importando mascara: {src.name}")
        try:
            if src.name.endswith("_seg.npy"):
                data = np.load(src, allow_pickle=True)
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
                    errors.append(f"{src}: no 'masks' found")
                    continue

                dst_stem = dataset_import_output_stem(src, source_dir, use_folder_prefix)
                dst = mask_target_dir / f"{dst_stem}_masks.tif"
                if dst.exists():
                    try:
                        src.unlink()
                    except Exception:
                        pass
                    skipped += 1
                    continue

                mask_arr = np.asarray(masks).astype(np.uint16)
                tiff.imwrite(dst, mask_arr, compression="zlib")
                try:
                    src.unlink()
                except Exception:
                    pass
                masks_converted += 1
                continue

            dst_stem = dataset_import_output_stem(src, source_dir, use_folder_prefix)
            dst = mask_target_dir / f"{dst_stem}{src.suffix.lower()}"
            if dst.exists():
                skipped += 1
                continue
            shutil.copy2(src, dst)
            copied += 1
        except Exception as exc:
            skipped += 1
            errors.append(f"{src}: {exc}")

    used_destinations = set()
    for dst_stem, src in sorted(image_candidates.items(), key=lambda item: str(item[1]).lower()):
        current_step += 1
        report_progress(f"Importando imagem: {src.name}")
        destination = available_import_destination(target_dir, dst_stem, used_destinations)
        used_destinations.add(destination.name.lower())

        try:
            if src.suffix.lower() in {".tif", ".tiff"}:
                if convert_to_grayscale:
                    image_array = tiff.imread(src)
                    image_array = image_array_to_grayscale(image_array)
                    tiff.imwrite(destination, image_array, compression="zlib")
                else:
                    shutil.copy2(src, destination)
                copied += 1
                continue

            with Image.open(src) as image:
                if convert_to_grayscale:
                    image = image.convert("L")
                elif image.mode == "P":
                    image = image.convert("RGB")
                tiff.imwrite(destination, np.asarray(image), compression="zlib")
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


def convert_dataset_images_to_tif(input_dir, progress_callback=None):
    input_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    skipped = 0
    failed = 0
    errors = []

    image_paths = [
        image_path
        for image_path in sorted(input_dir.iterdir())
        if image_path.is_file()
        and image_path.suffix.lower() in SUPPORTED_CONVERSION_EXTENSIONS
        and image_path.suffix.lower() not in {".tif", ".tiff"}
        and not image_path.name.endswith("_seg.npy")
        and not image_path.stem.endswith("_masks")
        and not image_path.stem.endswith("_pred_mask")
    ]

    total = len(image_paths)
    for index, image_path in enumerate(image_paths, start=1):
        if progress_callback:
            progress_callback(index, total or 1, f"Convertendo imagem: {image_path.name}")

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
