from pathlib import Path
import argparse
import json
import random
import shutil
import sys

import numpy as np
import tifffile as tiff
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.annotation import validate_mask_content


IMAGE_EXTENSIONS = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]

TRAIN_RATIO = 0.7
VAL_RATIO = 0.15
TEST_RATIO = 0.15

RANDOM_SEED = 42
SAVE_CONVERTED_COPY = True
CONVERT_IMAGES_TO_TIF = True


def log_progress(current, total, detail):
    print(f"PROGRESS {current} {max(1, total)} {detail}", flush=True)


def parse_args():
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Prepara dataset em train/val/test.")
    parser.add_argument("--project-dir", default=str(project_dir))
    parser.add_argument("--plan", default=None, help="JSON opcional com inclusao e grupo de cada imagem.")
    return parser.parse_args()


def dataset_paths(project_dir):
    data_dir = Path(project_dir) / "data"
    return {
        "input": data_dir / "conversion" / "input",
        "converted": data_dir / "conversion" / "converted",
        "train": data_dir / "train",
        "val": data_dir / "val",
        "test": data_dir / "test",
    }


def ensure_dirs(paths):
    folders = [
        paths["converted"] / "images",
        paths["converted"] / "masks",
        paths["train"] / "images",
        paths["train"] / "masks",
        paths["val"] / "images",
        paths["val"] / "masks",
        paths["test"] / "images",
        paths["test"] / "masks",
    ]

    for folder in folders:
        folder.mkdir(parents=True, exist_ok=True)


def clear_split_dirs(paths):
    for split in ["train", "val", "test"]:
        for kind in ["images", "masks"]:
            folder = paths[split] / kind
            if folder.exists():
                for path in folder.iterdir():
                    if path.is_file():
                        path.unlink()


def find_image_files(input_dir):
    files = []

    for ext in IMAGE_EXTENSIONS:
        files.extend(list(input_dir.glob(f"*{ext}")))

    files = [
        path
        for path in files
        if not path.stem.endswith("_masks") and not path.stem.endswith("_pred_mask")
    ]

    return sorted(files)


def load_seg_mask(seg_path):
    data = np.load(seg_path, allow_pickle=True).item()

    if "masks" not in data:
        raise ValueError(f"Arquivo {seg_path} nao contem a chave 'masks'.")

    mask = data["masks"]

    if mask is None:
        raise ValueError(f"Mascara em {seg_path} e None.")

    return mask.astype(np.uint16)


def read_image(image_path):
    suffix = image_path.suffix.lower()

    if suffix in [".tif", ".tiff"]:
        return tiff.imread(image_path)

    return np.array(Image.open(image_path))


def save_image_as_tif(image_path, output_path):
    img = read_image(image_path)
    tiff.imwrite(output_path, img, compression="zlib")


def copy_or_convert_image(image_path, output_path):
    if CONVERT_IMAGES_TO_TIF:
        save_image_as_tif(image_path, output_path)
    else:
        shutil.copy2(image_path, output_path)


def get_output_image_name(image_path):
    if CONVERT_IMAGES_TO_TIF:
        return f"{image_path.stem}.tif"
    return image_path.name


def prepare_pair(image_path):
    seg_path = image_path.with_name(f"{image_path.stem}_seg.npy")
    tif_mask_path = image_path.with_name(f"{image_path.stem}_masks.tif")
    tiff_mask_path = image_path.with_name(f"{image_path.stem}_masks.tiff")

    if seg_path.exists():
        mask = load_seg_mask(seg_path)
    elif tif_mask_path.exists():
        with Image.open(tif_mask_path) as image:
            mask = np.array(image).astype(np.uint16)
    elif tiff_mask_path.exists():
        with Image.open(tiff_mask_path) as image:
            mask = np.array(image).astype(np.uint16)
    else:
        print(f"[TESTE] Sem mascara correspondente: {image_path.name}")
        return image_path, None

    validation = validate_mask_content(mask)
    if not validation["valid"]:
        print(
            f"[IGNORADO] {validation['status']}: {image_path.name} "
            f"({validation['pixel_count']} pixels, {validation['object_count']} objetos)"
        )
        return None

    return image_path, mask


def split_dataset(pairs):
    random.seed(RANDOM_SEED)
    pairs = pairs.copy()
    random.shuffle(pairs)

    total = len(pairs)
    n_train = int(total * TRAIN_RATIO)
    n_val = int(total * VAL_RATIO)

    train_pairs = pairs[:n_train]
    val_pairs = pairs[n_train:n_train + n_val]
    test_pairs = pairs[n_train + n_val:]

    return train_pairs, val_pairs, test_pairs


def load_plan(plan_path):
    if not plan_path:
        return {}
    path = Path(plan_path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as plan_file:
        data = json.load(plan_file)
    return {entry["image"]: entry for entry in data.get("images", [])}


def split_dataset_from_plan(pairs, plan):
    selected = {"train": [], "val": [], "test": []}
    automatic = []

    for image_path, mask in pairs:
        entry = plan.get(image_path.name, {})
        if not entry.get("include", True):
            continue
        group = entry.get("group", "auto")
        if group == "uncategorized":
            continue
        if mask is None:
            selected["test"].append((image_path, mask))
            continue
        if group in selected:
            selected[group].append((image_path, mask))
        else:
            automatic.append((image_path, mask))

    if automatic:
        auto_train, auto_val, auto_test = split_dataset(automatic)
        selected["train"].extend(auto_train)
        selected["val"].extend(auto_val)
        selected["test"].extend(auto_test)

    return selected["train"], selected["val"], selected["test"]


def save_pair_to_folder(image_path, mask, target_dir):
    image_output_name = get_output_image_name(image_path)
    image_output_path = target_dir / "images" / image_output_name

    copy_or_convert_image(image_path, image_output_path)
    if mask is None:
        return image_output_path, None

    mask_output_name = f"{Path(image_output_name).stem}_masks.tif"
    mask_output_path = target_dir / "masks" / mask_output_name
    tiff.imwrite(mask_output_path, mask, compression="zlib")
    return image_output_path, mask_output_path


def save_converted_pair(image_path, mask, converted_dir):
    image_output_name = get_output_image_name(image_path)
    image_output_path = converted_dir / "images" / image_output_name
    mask_output_path = converted_dir / "masks" / f"{Path(image_output_name).stem}_masks.tif"

    copy_or_convert_image(image_path, image_output_path)
    tiff.imwrite(mask_output_path, mask, compression="zlib")


def main():
    args = parse_args()
    project_dir = Path(args.project_dir)
    paths = dataset_paths(project_dir)
    plan = load_plan(args.plan)

    ensure_dirs(paths)

    image_files = find_image_files(paths["input"])

    if not image_files:
        print(f"Nenhuma imagem encontrada em {paths['input']}.")
        return

    valid_pairs = []
    test_only_pairs = []

    print("Procurando pares imagem + _seg.npy...")

    total_steps = len(image_files)
    progress = 0
    for image_path in image_files:
        log_progress(progress, total_steps, f"Validando: {image_path.name}")
        result = prepare_pair(image_path)
        progress += 1
        log_progress(progress, total_steps, f"Validado: {image_path.name}")

        if result is None:
            continue

        image_path, mask = result
        if mask is None:
            test_only_pairs.append((image_path, mask))
            continue

        valid_pairs.append((image_path, mask))

        if SAVE_CONVERTED_COPY:
            log_progress(progress, total_steps, f"Convertendo copia: {image_path.name}")
            save_converted_pair(image_path, mask, paths["converted"])

    if not valid_pairs and not test_only_pairs:
        print("Nenhuma imagem valida encontrada.")
        return

    if plan:
        train_pairs, val_pairs, test_pairs = split_dataset_from_plan(valid_pairs, plan)
        _ignored_train, _ignored_val, planned_test_only_pairs = split_dataset_from_plan(test_only_pairs, plan)
        test_pairs.extend(planned_test_only_pairs)
    else:
        train_pairs, val_pairs, test_pairs = split_dataset(valid_pairs)
        test_pairs.extend(test_only_pairs)

    print()
    print("Divisao do dataset:")
    print(f"Treino: {len(train_pairs)}")
    print(f"Validacao: {len(val_pairs)}")
    print(f"Teste: {len(test_pairs)}")
    if test_only_pairs:
        print(f"Teste sem mascara: {len(test_only_pairs)}")
    print()

    clear_split_dirs(paths)

    split_pairs = train_pairs + val_pairs + test_pairs
    total_steps = max(1, len(split_pairs))
    progress = 0
    for image_path, mask in train_pairs:
        log_progress(progress, total_steps, f"Salvando treino: {image_path.name}")
        save_pair_to_folder(image_path, mask, paths["train"])
        progress += 1
        log_progress(progress, total_steps, f"Treino salvo: {image_path.name}")

    for image_path, mask in val_pairs:
        log_progress(progress, total_steps, f"Salvando validacao: {image_path.name}")
        save_pair_to_folder(image_path, mask, paths["val"])
        progress += 1
        log_progress(progress, total_steps, f"Validacao salva: {image_path.name}")

    for image_path, mask in test_pairs:
        log_progress(progress, total_steps, f"Salvando teste: {image_path.name}")
        save_pair_to_folder(image_path, mask, paths["test"])
        progress += 1
        log_progress(progress, total_steps, f"Teste salvo: {image_path.name}")

    print("Dataset preparado com sucesso.")


if __name__ == "__main__":
    main()
