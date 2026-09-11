import json

from services.paths import image_set_metadata_path


# type: "normal" | "test"
# source_project: nome do projeto de origem (apenas type == "test")
DEFAULT_METADATA = {"type": "normal"}


def read_image_set_metadata(config, name):
    path = image_set_metadata_path(config, name)
    if not path.exists():
        return DEFAULT_METADATA.copy()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if "type" not in data:
            data["type"] = "normal"
        return data
    except (OSError, json.JSONDecodeError):
        return DEFAULT_METADATA.copy()


def write_image_set_metadata(config, name, metadata):
    path = image_set_metadata_path(config, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)


def is_test_image_set(config, name):
    return read_image_set_metadata(config, name).get("type") == "test"


def get_source_project(config, name):
    """Retorna o projeto de origem de um conjunto de teste, ou None se normal."""
    meta = read_image_set_metadata(config, name)
    if meta.get("type") != "test":
        return None
    return meta.get("source_project")
