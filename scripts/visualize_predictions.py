from pathlib import Path
import argparse

import numpy as np
import tifffile as tiff


def parse_args():
    project_dir = Path(__file__).resolve().parents[1] / "projects" / "eucalipto"
    default_model = "cpsam_vasos_eucalipto_v1"
    parser = argparse.ArgumentParser(description="Cria overlays das predicoes sobre as imagens originais.")
    parser.add_argument("--images", default=str(project_dir / "data" / "test" / "images"))
    parser.add_argument("--predictions", default=str(project_dir / "outputs" / default_model / "predictions"))
    parser.add_argument("--output", default=str(project_dir / "outputs" / default_model / "overlays"))
    return parser.parse_args()


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


def create_overlay(image, mask, color=(255, 0, 0), alpha=0.45):
    rgb = to_rgb(image).astype(np.float32)
    vessel_pixels = mask > 0

    overlay_color = np.array(color, dtype=np.float32)
    rgb[vessel_pixels] = ((1 - alpha) * rgb[vessel_pixels]) + (alpha * overlay_color)

    return rgb.astype(np.uint8)


def main():
    args = parse_args()

    images_dir = Path(args.images)
    predictions_dir = Path(args.predictions)
    overlays_dir = Path(args.output)
    overlays_dir.mkdir(parents=True, exist_ok=True)

    image_files = sorted(images_dir.glob("*.tif"))

    if not image_files:
        raise RuntimeError(f"Nenhuma imagem encontrada em: {images_dir}")

    saved_count = 0

    total = len(image_files)
    print(f"PROGRESS 0 {total} Iniciando overlays", flush=True)

    for index, image_path in enumerate(image_files, start=1):
        pred_path = predictions_dir / f"{image_path.stem}_pred_masks.tif"

        if not pred_path.exists():
            print(f"Predicao nao encontrada para {image_path.name}: {pred_path}")
            continue

        image = tiff.imread(image_path)
        pred_mask = tiff.imread(pred_path)

        if image.shape[:2] != pred_mask.shape[:2]:
            print(f"Formato diferente para {image_path.name}: imagem {image.shape}, predicao {pred_mask.shape}")
            continue

        overlay = create_overlay(image, pred_mask)
        output_path = overlays_dir / f"{image_path.stem}_overlay_pred.tif"
        tiff.imwrite(output_path, overlay, photometric="rgb")

        saved_count += 1
        print(f"Overlay salvo: {output_path}")
        print(f"PROGRESS {index} {total} Overlay: {image_path.name}", flush=True)

    if saved_count == 0:
        raise RuntimeError("Nenhum overlay foi gerado.")

    print(f"\nTotal de overlays gerados: {saved_count}")
    print(f"Pasta de saida: {overlays_dir}")


if __name__ == "__main__":
    main()
