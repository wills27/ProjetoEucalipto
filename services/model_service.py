import shutil

from services.paths import model_outputs_dir, project_models_dir, shared_models_dir


def list_shared_model_paths(config):
    d = shared_models_dir(config)
    d.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in d.iterdir() if p.is_file())


def list_project_model_paths(config):
    d = project_models_dir(config)
    d.mkdir(parents=True, exist_ok=True)
    return sorted(p for p in d.iterdir() if p.is_file())


def list_available_model_paths(config, image_set_name=None):
    """
    Retorna modelos disponíveis para o conjunto de imagens ativo.
    Conjunto normal (ou None): só shared_models.
    Conjunto de teste: shared_models + modelos do projeto de origem.
    """
    shared = list_shared_model_paths(config)
    if image_set_name is None:
        return shared

    from services.image_set_service import is_test_image_set
    if is_test_image_set(config, image_set_name):
        project = list_project_model_paths(config)
        shared_names = {p.name for p in shared}
        extra = [p for p in project if p.name not in shared_names]
        return shared + extra
    return shared


def list_available_model_names(config, image_set_name=None):
    return [p.name for p in list_available_model_paths(config, image_set_name)]


# Mantido para compatibilidade: aba de treinamento lista só modelos do projeto
def list_model_names(config):
    return [p.name for p in list_project_model_paths(config)]


def list_model_paths(config):
    return list_project_model_paths(config)


def first_model_name(config, image_set_name=None):
    models = list_available_model_names(config, image_set_name)
    return models[0] if models else ""


def promote_model_to_shared(config, model_name):
    """Copia um modelo treinado no projeto para shared_models."""
    src = project_models_dir(config) / model_name
    if not src.exists():
        raise ValueError(f"Modelo nao encontrado: {model_name!r}")
    dst_dir = shared_models_dir(config)
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / model_name
    shutil.copy2(src, dst)
    return dst


def delete_model(config, model_name):
    """Remove permanentemente um modelo do projeto e seus outputs do disco."""
    models_dir = project_models_dir(config)
    path = models_dir / model_name
    if path.parent != models_dir or not path.exists():
        raise ValueError(f"Modelo desconhecido: {model_name!r}")
    path.unlink()
    outputs = model_outputs_dir(config, model_name)
    if outputs.exists():
        shutil.rmtree(outputs, ignore_errors=True)


def delete_shared_model(config, model_name):
    """Remove permanentemente um modelo compartilhado do disco."""
    d = shared_models_dir(config)
    path = d / model_name
    if path.parent != d or not path.exists():
        raise ValueError(f"Modelo compartilhado desconhecido: {model_name!r}")
    path.unlink()
