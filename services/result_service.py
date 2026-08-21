import shutil
from pathlib import Path

from services.conversion_scan import IMAGE_EXTENSIONS
from services.csv_files import load_semicolon_csv
from services.dataset_manifest import manifest_image_path
from services.metrics import read_metrics
from services.paths import (
    cell_counts_csv_path,
    cell_measurements_csv_path,
    dataset_images_dir,
    metrics_csv_path,
    model_outputs_dir,
    overlays_dir,
    predictions_dir,
)
from services.process_output import stem_from_result_path


OVERLAY_SUFFIXES = [".png", ".tif", ".tiff"]
PREDICTION_SUFFIXES = [".tif", ".tiff"]
MASK_SUFFIXES = ["_seg.npy", "_masks.tif", "_masks.tiff"]


def result_overlay_path(config, stem):
    return overlays_dir(config) / f"{stem}_overlay_pred.png"


def legacy_result_overlay_paths(config, stem):
    return [
        overlays_dir(config) / f"{stem}_overlay_pred.tif",
        overlays_dir(config) / f"{stem}_overlay_pred.tiff",
    ]


def result_output_removal_targets(config, image_stem):
    output_removed_dir = model_outputs_dir(config) / "removed"
    targets = []
    for suffix in PREDICTION_SUFFIXES:
        targets.append((predictions_dir(config) / f"{image_stem}_pred_masks{suffix}", output_removed_dir / "predictions"))
        targets.append((predictions_dir(config) / f"{image_stem}_pred_padded_masks{suffix}", output_removed_dir / "predictions"))
    for suffix in OVERLAY_SUFFIXES:
        targets.append((overlays_dir(config) / f"{image_stem}_overlay_pred{suffix}", output_removed_dir / "overlays"))
    return targets


def move_to_removed_folder(source_path, removed_dir):
    removed_dir.mkdir(parents=True, exist_ok=True)
    destination = removed_dir / source_path.name
    if destination.exists():
        counter = 1
        while True:
            candidate = removed_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
            if not candidate.exists():
                destination = candidate
                break
            counter += 1
    shutil.move(str(source_path), str(destination))
    return destination


def conversion_input_image_for_stem(config, image_stem):
    input_dir = dataset_images_dir(config)
    for suffix in IMAGE_EXTENSIONS:
        image_path = input_dir / f"{image_stem}{suffix}"
        if image_path.exists():
            return image_path
    return None


def image_mask_exists(image_path):
    return any(
        (folder / f"{image_path.stem}{suffix}").exists()
        for folder in [dataset_masks_dir_from_image_path(image_path), image_path.parent]
        for suffix in MASK_SUFFIXES
    )


def dataset_masks_dir_from_image_path(image_path):
    if image_path.parent.name == "images":
        return image_path.parent.parent / "masks"
    return image_path.parent


def result_conversion_input_images(config):
    image_files = []
    input_dir = dataset_images_dir(config)
    for ext in IMAGE_EXTENSIONS:
        image_files.extend(input_dir.glob(f"*{ext}"))
    return sorted(
        (
            path
            for path in {path.resolve(): path for path in image_files}.values()
            if not path.stem.endswith("_masks")
            and not path.stem.endswith("_pred_mask")
            and not path.stem.endswith("_pred_masks")
        ),
        key=lambda path: path.name.lower(),
    )


def result_image_entries(config, dataset_plan):
    entries = {}
    plan_by_stem = {Path(image_name).stem: saved for image_name, saved in dataset_plan.items()}
    images_dir = dataset_images_dir(config)
    if images_dir.exists():
        for ext in IMAGE_EXTENSIONS:
            for path in sorted(images_dir.glob(f"*{ext}")):
                if path.stem.endswith("_masks") or path.stem.endswith("_pred_mask") or path.stem.endswith("_pred_masks"):
                    continue
                saved = plan_by_stem.get(path.stem)
                if saved is not None and saved.get("group") != "test":
                    continue
                entries.setdefault(path.stem, path)

    for saved in dataset_plan.values():
        if saved.get("group") != "test":
            continue
        image_path = manifest_image_path(config, saved)
        if image_path is not None:
            entries[image_path.stem] = image_path

    for image_path in result_conversion_input_images(config):
        saved = dataset_plan.get(image_path.name, {})
        if saved.get("group") == "uncategorized":
            continue
        is_prediction_only = not image_mask_exists(image_path)
        is_test_image = is_prediction_only or saved.get("group") == "test"
        if is_test_image:
            entries.setdefault(image_path.stem, image_path)

    return dict(sorted(entries.items()))


def result_overlay_exists(config, stem, status_index=None, runtime_overlay_ready_stems=None, preferred_only=False):
    runtime_overlay_ready_stems = runtime_overlay_ready_stems or set()
    status_index = status_index or {}
    if stem in runtime_overlay_ready_stems:
        return True
    if preferred_only:
        return result_overlay_path(config, stem).exists()
    overlay_stems = status_index.get("overlays")
    if overlay_stems is not None:
        return stem in overlay_stems
    return any(
        (overlays_dir(config) / f"{stem}_overlay_pred{suffix}").exists()
        for suffix in OVERLAY_SUFFIXES
    )


def result_prediction_exists(config, stem, status_index=None):
    status_index = status_index or {}
    prediction_stems = status_index.get("predictions")
    if prediction_stems is not None:
        return stem in prediction_stems
    return any(
        (predictions_dir(config) / f"{stem}_pred_masks{suffix}").exists()
        for suffix in PREDICTION_SUFFIXES
    )


def result_metrics_exists(config, stem, status_index=None, runtime_metrics_ready_stems=None):
    runtime_metrics_ready_stems = runtime_metrics_ready_stems or set()
    status_index = status_index or {}
    if stem in runtime_metrics_ready_stems:
        return True
    metric_stems = status_index.get("metrics")
    if metric_stems is not None:
        return stem in metric_stems
    for row in read_metrics(metrics_csv_path(config)):
        if row.get("image") == stem:
            return True
    for row in load_semicolon_csv(cell_counts_csv_path(config))[1:]:
        if row and row[0] == stem:
            return True
    for row in load_semicolon_csv(cell_measurements_csv_path(config))[1:]:
        if row and row[0] == stem:
            return True
    return False


def build_result_status_index(config, entries=None, runtime_overlay_ready_stems=None, runtime_metrics_ready_stems=None):
    runtime_overlay_ready_stems = runtime_overlay_ready_stems or set()
    runtime_metrics_ready_stems = runtime_metrics_ready_stems or set()

    overlay_stems = {
        stem_from_result_path(path.name, "_overlay_pred")
        for suffix in OVERLAY_SUFFIXES
        for path in overlays_dir(config).glob(f"*_overlay_pred{suffix}")
    }
    overlay_stems.update(runtime_overlay_ready_stems)

    prediction_stems = {
        stem_from_result_path(path.name, "_pred_masks")
        for suffix in PREDICTION_SUFFIXES
        for path in predictions_dir(config).glob(f"*_pred_masks{suffix}")
    }

    metric_stems = set(runtime_metrics_ready_stems)
    metric_stems.update(row.get("image", "") for row in read_metrics(metrics_csv_path(config)))
    metric_stems.update(row[0] for row in load_semicolon_csv(cell_counts_csv_path(config))[1:] if row)
    metric_stems.update(row[0] for row in load_semicolon_csv(cell_measurements_csv_path(config))[1:] if row)
    metric_stems.discard("")

    if entries is not None:
        entry_stems = set(entries)
        overlay_stems &= entry_stems
        prediction_stems &= entry_stems
        metric_stems &= entry_stems

    return {
        "overlays": overlay_stems,
        "predictions": prediction_stems,
        "metrics": metric_stems,
    }
