from pathlib import Path
import os
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT_DIR / "scripts"
APP_NAME = "CellposeLineofCode"
LEGACY_CONFIG_PATH = PROJECT_DIR / "app_config.json"


def app_config_dir():
    if getattr(sys, "frozen", False):
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / APP_NAME
        return Path.home() / f".{APP_NAME}"
    return PROJECT_DIR


CONFIG_PATH = app_config_dir() / "app_config.json"


def default_projects_dir():
    documents = Path.home() / "Documents"
    if documents.exists():
        return documents / "CellposeProjects"
    return Path.home() / "CellposeProjects"


def projects_dir(config):
    path = Path(config.get("projects_dir", "projects"))
    if path.is_absolute():
        return path
    return PROJECT_DIR / path


def active_project_dir(config):
    return projects_dir(config) / config.get("active_project", "eucalipto")


def project_models_dir(config):
    return active_project_dir(config) / "models"


def model_outputs_dir(config, model_name=None):
    model = Path(model_name or config.get("active_model") or "__no_model_selected__").name
    return active_project_dir(config) / "outputs" / model


def predictions_dir(config, model_name=None):
    return model_outputs_dir(config, model_name) / "predictions"


def overlays_dir(config, model_name=None):
    return model_outputs_dir(config, model_name) / "overlays"


def conversion_excluded_dir(config):
    return active_project_dir(config) / "data" / "excluded"


def dataset_images_dir(config):
    return active_project_dir(config) / "data" / "images"


def dataset_masks_dir(config):
    return active_project_dir(config) / "data" / "masks"


def dataset_plan_path(config):
    return active_project_dir(config) / "data" / "dataset_plan.json"


def relative_to_project(path, config):
    try:
        return str(Path(path).relative_to(active_project_dir(config)))
    except ValueError:
        return str(path)


def ensure_project_structure(project_dir):
    folders = [
        project_dir / "data" / "images",
        project_dir / "data" / "masks",
        project_dir / "data" / "excluded",
        project_dir / "models",
        project_dir / "outputs",
    ]
    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def list_projects(config):
    root = projects_dir(config)
    root.mkdir(parents=True, exist_ok=True)
    return sorted(path.name for path in root.iterdir() if path.is_dir())


def project_path(value, config=None):
    from services.config import load_config

    path = Path(value)
    if path.is_absolute():
        return path
    config = config or load_config()
    return active_project_dir(config) / path


def active_model_path(config):
    if not config.get("active_model"):
        return project_models_dir(config) / "__no_model_selected__"
    model = Path(config["active_model"])
    if model.is_absolute():
        return model
    return project_models_dir(config) / model


def metrics_csv_path(config, model_name=None):
    return model_outputs_dir(config, model_name) / "metrics.csv"


def cell_measurements_csv_path(config, model_name=None):
    return model_outputs_dir(config, model_name) / "cell_measurements.csv"


def cell_counts_csv_path(config, model_name=None):
    return model_outputs_dir(config, model_name) / "cell_counts.csv"
