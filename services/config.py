import json
import shutil

from services.paths import CONFIG_PATH, LEGACY_CONFIG_PATH, default_projects_dir


DEFAULT_CONFIG = {
    "active_project": "eucalipto",
    "projects_dir": str(default_projects_dir()),
    "active_model": "cpsam_vasos_eucalipto_v1",
    "padding_pixels": 64,
    "diameter": 0.0,
    "cellprob_threshold": 0.0,
    "flow_threshold": 0.4,
    "test_images_dir": "data/test/images",
    "test_masks_dir": "data/test/masks",
    "predictions_dir": "outputs/cpsam_vasos_eucalipto_v1/predictions",
    "overlays_dir": "outputs/cpsam_vasos_eucalipto_v1/overlays",
}


def load_config():
    migrate_legacy_config()
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with CONFIG_PATH.open("r", encoding="utf-8-sig") as config_file:
        config = json.load(config_file)

    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    return merged


def save_config(config):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)


def migrate_legacy_config():
    if CONFIG_PATH.exists() or not LEGACY_CONFIG_PATH.exists() or CONFIG_PATH == LEGACY_CONFIG_PATH:
        return
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(LEGACY_CONFIG_PATH, CONFIG_PATH)
