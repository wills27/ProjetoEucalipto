from pathlib import Path
import argparse

import numpy as np
import tifffile as tiff
from cellpose import core, models
from PIL import Image


DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[1] / "projects" / "eucalipto"


def parse_args():
    parser = argparse.ArgumentParser(description="Gera predicoes e overlays em uma unica passada.")
    parser.add_argument("--model", default=str(DEFAULT_PROJECT_DIR / "models" / "cpsam_vasos_eucalipto_v1"))
    parser.add_argument("--input", default=str(DEFAULT_PROJECT_DIR / "data" / "test" / "images"))
    parser.add_argument("--images", nargs="*", default=None, help="Lista opcional de imagens especificas para processar.")
    parser.add_argument("--predictions-output", default=str(DEFAULT_PROJECT_DIR / "outputs" / "cpsam_vasos_eucalipto_v1" / "predictions"))
    parser.add_argument("--overlays-output", default=str(DEFAULT_PROJECT_DIR / "outputs" / "cpsam_vasos_eucalipto_v1" / "overlays"))
    parser.add_argument("--padding", type=int, default=64)
    parser.add_argument("--diameter", type=float, default=0.0)
    parser.add_argument("--cellprob-threshold", type=float, default=0.0)
    parser.add_argument("--flow-threshold", type=float, default=0.4)
    return parser.parse_args()


def pad_image(image, padding):
    if padding <= 0:
        return image

    if image.ndim == 2:
        return np.pad(image, ((padding, padding), (padding, padding)), mode="reflect")

    if image.ndim == 3:
        return np.pad(image, ((padding, padding), (padding, padding), (0, 0)), mode="reflect")

    raise ValueError(f"Formato de imagem nao suportado: {image.shape}")


def crop_mask(mask, padding, original_shape=None):
    if padding <= 0:
        if original_shape is None:
            return mask
        height, width = original_shape[:2]
        return mask[:height, :width]

    if original_shape is None:
        return mask[padding:-padding, padding:-padding]
    height, width = original_shape[:2]
    return mask[padding : padding + height, padding : padding + width]


def normalize_to_uint8(image):
    image = image.astype(np.float32)
    min_value = np.percentile(image, 1)
    max_value = np.percentile(image, 99)

    if max_value <= min_value:
        return np.zeros(image.shape, dtype=np.uint8)

    image = np.clip((image - min_value) / (max_value - min_value), 0, 1)
    return (image * 255).astype(np.uint8)


def to_rgb(image):
    image_8bit = normalize_to_uint8(image)

    if image_8bit.ndim == 2:
        return np.stack([image_8bit, image_8bit, image_8bit], axis=-1)

    if image_8bit.ndim == 3 and image_8bit.shape[-1] >= 3:
        return image_8bit[..., :3]

    if image_8bit.ndim == 3:
        image_2d = image_8bit[..., 0]
        return np.stack([image_2d, image_2d, image_2d], axis=-1)

    raise ValueError(f"Formato de imagem nao suportado: {image.shape}")


def read_image(image_path):
    if image_path.suffix.lower() in {".tif", ".tiff"}:
        return tiff.imread(image_path)

    with Image.open(image_path) as image:
        return np.asarray(image)


def label_color(label_value):
    palette = [
        (230, 92, 58),
        (22, 107, 92),
        (71, 125, 210),
        (174, 92, 179),
        (218, 154, 48),
        (64, 156, 178),
        (122, 144, 57),
        (202, 84, 123),
    ]
    return np.array(palette[(int(label_value) - 1) % len(palette)], dtype=np.float32)


def create_overlay(mask, alpha=118):
    mask = np.asarray(mask)
    height, width = mask.shape[:2]
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    for label_value in np.unique(mask):
        if label_value == 0:
            continue
        vessel_pixels = mask == label_value
        overlay[vessel_pixels, :3] = label_color(label_value).astype(np.uint8)
        overlay[vessel_pixels, 3] = alpha

    return overlay


def main():
    args = parse_args()

    model_path = Path(args.model)
    input_dir = Path(args.input)
    predictions_output = Path(args.predictions_output)
    overlays_output = Path(args.overlays_output)
    predictions_output.mkdir(parents=True, exist_ok=True)
    overlays_output.mkdir(parents=True, exist_ok=True)

    use_gpu = core.use_gpu()
    model = models.CellposeModel(gpu=use_gpu, pretrained_model=str(model_path))
    diameter = None if args.diameter <= 0 else args.diameter

    if args.images:
        image_files = sorted(Path(path) for path in args.images)
    else:
        image_files = sorted(input_dir.glob("*.tif"))
    if not image_files:
        raise RuntimeError(f"Nenhuma imagem encontrada em: {input_dir}")
    missing_files = [path for path in image_files if not path.exists()]
    if missing_files:
        missing_text = "\n".join(str(path) for path in missing_files)
        raise RuntimeError(f"Imagem(ns) nao encontrada(s):\n{missing_text}")

    total = len(image_files)
    print(f"PROGRESS 0 {total} Iniciando resultados", flush=True)

    for index, image_path in enumerate(image_files, start=1):
        image = read_image(image_path)
        padded_image = pad_image(image, args.padding)

        eval_result = model.eval(
            padded_image,
            diameter=diameter,
            channel_axis=None,
            normalize=True,
            cellprob_threshold=args.cellprob_threshold,
            flow_threshold=args.flow_threshold,
        )
        padded_masks = eval_result[0].astype(np.uint16)
        masks = crop_mask(padded_masks, args.padding, image.shape).astype(np.uint16)

        pred_path = predictions_output / f"{image_path.stem}_pred_masks.tif"
        padded_pred_path = predictions_output / f"{image_path.stem}_pred_padded_masks.tif"
        overlay_path = overlays_output / f"{image_path.stem}_overlay_pred.png"

        tiff.imwrite(pred_path, masks, compression="zlib")
        tiff.imwrite(padded_pred_path, padded_masks, compression="zlib")
        overlay = create_overlay(masks)
        Image.fromarray(overlay, "RGBA").save(overlay_path, format="PNG", optimize=True)
        for legacy_suffix in [".tif", ".tiff"]:
            legacy_path = overlays_output / f"{image_path.stem}_overlay_pred{legacy_suffix}"
            if legacy_path.exists():
                legacy_path.unlink()

        print(f"PROGRESS {index} {total} Resultados: {image_path.name}", flush=True)
        print(f"Predicao salva: {pred_path}")
        print(f"Overlay salvo: {overlay_path}")


if __name__ == "__main__":
    main()
