import json
import shutil
from pathlib import Path

from services.paths import CONFIG_PATH, LEGACY_CONFIG_PATH, default_projects_dir


DEFAULT_CONFIG = {
    "active_project": "eucalipto",
    "projects_dir": str(default_projects_dir()),
    "active_model": "cpsam_vasos_eucalipto_v1",
    "padding_pixels": 64,
    "diameter": 0.0,
    "cellprob_threshold": 0.0,
    "flow_threshold": 0.4,
    "calibration": {
        "unit": "um",
        "unit_per_pixel": 0.0,
        "pixel_distance": 0.0,
        "real_distance": 0.0,
        "source": "",
        "source_image": "",
    },
    "import_dataset_prefix_folders": False,
}


DERIVED_CONFIG_KEYS = {"predictions_dir", "overlays_dir"}


def with_derived_paths(config):
    from services.paths import overlays_dir, predictions_dir, relative_to_project

    normalized = config.copy()
    normalized["predictions_dir"] = relative_to_project(predictions_dir(normalized), normalized)
    normalized["overlays_dir"] = relative_to_project(overlays_dir(normalized), normalized)
    return normalized


def persistent_config(config):
    return {
        key: value
        for key, value in config.items()
        if key not in DERIVED_CONFIG_KEYS
    }


def load_config():
    migrate_legacy_config()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return with_derived_paths(DEFAULT_CONFIG)

    with CONFIG_PATH.open("r", encoding="utf-8-sig") as config_file:
        config = json.load(config_file)

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    calibration = DEFAULT_CONFIG["calibration"].copy()
    calibration.update(config.get("calibration", {}))
    merged["calibration"] = calibration
    projects_dir = Path(str(merged.get("projects_dir", ""))).expanduser()
    if projects_dir and projects_dir.is_absolute() and not projects_dir.exists():
        merged["projects_dir"] = str(default_projects_dir())
        save_config(merged)
    return with_derived_paths(merged)


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
        json.dump(persistent_config(config), config_file, indent=2)


def migrate_legacy_config():
    if CONFIG_PATH.exists() or not LEGACY_CONFIG_PATH.exists() or CONFIG_PATH == LEGACY_CONFIG_PATH:
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_CONFIG_PATH, CONFIG_PATH)
