import shutil

from services.paths import model_outputs_dir, project_models_dir


def list_model_names(config):
    return sorted(path.name for path in project_models_dir(config).glob("*") if path.is_file())


def list_model_paths(config):
    models_dir = project_models_dir(config)
    models_dir.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in models_dir.iterdir() if path.is_file())


def first_model_name(config):
    models = list_model_names(config)
    return models[0] if models else ""


def delete_model(config, model_name):
    """Permanently removes a model file and its outputs (predictions/overlays/metrics) from disk."""
    models_dir = project_models_dir(config)
    path = models_dir / model_name
    if path.parent != models_dir or not path.exists():
        raise ValueError(f"Modelo desconhecido: {model_name!r}")
    path.unlink()
    outputs = model_outputs_dir(config, model_name)
    if outputs.exists():
        shutil.rmtree(outputs, ignore_errors=True)
