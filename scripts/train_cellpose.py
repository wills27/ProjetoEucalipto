from pathlib import Path
import argparse
import logging
import os
import shutil
import sys

import numpy as np
import tifffile as tiff

from cellpose import core, models, train


def parse_args():
    project_dir = Path(__file__).resolve().parents[1] / "projects" / "eucalipto"
    parser = argparse.ArgumentParser(description="Treina um modelo Cellpose para vasos.")
    parser.add_argument("--project-dir", default=str(project_dir))
    parser.add_argument("--model-name", default="cpsam_vasos_eucalipto_v1")
    parser.add_argument("--base-model", default="cpsam")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--learning-rate", type=float, default=1e-5)
    parser.add_argument("--weight-decay", type=float, default=0.1)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--require-gpu", action="store_true")
    return parser.parse_args()


def log(message):
    print(message, flush=True)


def setup_cellpose_logging():
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        stream=sys.stdout,
        force=True,
    )


def latest_loss_value(losses):
    values = np.asarray(losses, dtype=float)
    finite_values = values[np.isfinite(values)]
    nonzero_values = finite_values[finite_values != 0]
    if len(nonzero_values) > 0:
        return float(nonzero_values[-1])
    if len(finite_values) > 0:
        return float(finite_values[-1])
    return 0.0


def load_dataset(images_dir, masks_dir):
    images_dir = Path(images_dir)
    masks_dir = Path(masks_dir)

    log(f"  Procurando imagens em: {images_dir.absolute()}")
    log(f"  Diretorio existe: {images_dir.exists()}")

    if not images_dir.exists():
        log("  Diretorio nao encontrado.")
        return [], [], []

    images_files = sorted(
        list(images_dir.glob("*.tif"))
        + list(images_dir.glob("*.tiff"))
        + list(images_dir.glob("*.png"))
        + list(images_dir.glob("*.jpg"))
    )

    log(f"  Arquivos de imagem encontrados: {len(images_files)}")
    if images_files:
        for file_path in images_files[:3]:
            log(f"    - {file_path.name}")

    images = []
    masks = []
    used_files = []

    for img_path in images_files:
        mask_path = masks_dir / f"{img_path.stem}_masks.tif"

        if not mask_path.exists():
            log(f"Warning: No corresponding mask found for {img_path}")
            continue

        img = tiff.imread(img_path)
        mask = tiff.imread(mask_path)

        if mask.max() == 0:
            log(f"Warning: Mask for {img_path} is empty, skipping.")
            continue

        images.append(img)
        masks.append(mask.astype(np.uint16))
        used_files.append(img_path.stem)

    return images, masks, used_files


def main():
    setup_cellpose_logging()
    args = parse_args()
    project_dir = Path(args.project_dir).resolve()
    data_dir = project_dir / "data"

    train_images_dir = data_dir / "train" / "images"
    train_masks_dir = data_dir / "train" / "masks"
    val_images_dir = data_dir / "val" / "images"
    val_masks_dir = data_dir / "val" / "masks"

    models_dir = project_dir / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    training_flows_dir = project_dir / "outputs" / args.model_name / "training_flows"
    training_flows_dir.mkdir(parents=True, exist_ok=True)

    log("ETAPA: carregando dados de treino")
    train_images, train_masks, train_files = load_dataset(train_images_dir, train_masks_dir)

    log("ETAPA: carregando dados de validacao")
    val_images, val_masks, val_files = load_dataset(val_images_dir, val_masks_dir)

    log(f"Imagens de treino: {len(train_images)}")
    log(f"Imagens de validacao: {len(val_images)}")

    if len(train_images) == 0:
        raise RuntimeError("Nenhuma imagem de treino valida encontrada.")

    use_gpu = core.use_gpu()
    log(f"Usando GPU: {use_gpu}")
    if args.require_gpu and not use_gpu:
        raise RuntimeError("GPU obrigatoria, mas o Cellpose nao detectou CUDA/GPU disponivel.")
    log("ETAPA: inicializando modelo")

    model = models.CellposeModel(gpu=use_gpu, pretrained_model=args.base_model)

    original_cwd = Path.cwd()
    os.chdir(training_flows_dir)
    try:
        log("ETAPA: treinamento principal iniciado")
        log("Observacao: barras 100% do Cellpose podem indicar apenas subetapas internas.")
        model_path, train_losses, val_losses = train.train_seg(
            model.net,
            train_data=train_images,
            train_labels=train_masks,
            train_files=train_files,
            test_data=val_images if len(val_images) > 0 else None,
            test_labels=val_masks if len(val_masks) > 0 else None,
            test_files=val_files if len(val_files) > 0 else None,
            normalize=True,
            learning_rate=args.learning_rate,
            weight_decay=args.weight_decay,
            n_epochs=args.epochs,
            batch_size=args.batch_size,
            save_path=str(project_dir),
            model_name=args.model_name,
        )
    finally:
        os.chdir(original_cwd)

    final_epoch_index = args.epochs - 1
    final_epoch_logged_by_cellpose = final_epoch_index == 5 or final_epoch_index % 10 == 0
    if not final_epoch_logged_by_cellpose:
        final_train_loss = latest_loss_value(train_losses)
        final_val_loss = latest_loss_value(val_losses)
        log(
            f"{final_epoch_index}, train_loss={final_train_loss:.4f}, "
            f"test_loss={final_val_loss:.4f}, LR={args.learning_rate:.6f}, time 0.00s"
        )

    log("ETAPA: treinamento finalizado")
    log(f"Modelo salvo em: {model_path}")
    if training_flows_dir.exists():
        log("ETAPA: limpando arquivos temporarios")
        shutil.rmtree(training_flows_dir)
        log(f"Training flows apagados: {training_flows_dir}")


if __name__ == "__main__":
    main()
