from services.paths import project_models_dir


def list_model_names(config):
    return sorted(path.name for path in project_models_dir(config).glob("*") if path.is_file())


def list_model_paths(config):
    models_dir = project_models_dir(config)
    models_dir.mkdir(parents=True, exist_ok=True)
    return sorted(path for path in models_dir.iterdir() if path.is_file())


def first_model_name(config):
    models = list_model_names(config)
    return models[0] if models else ""
