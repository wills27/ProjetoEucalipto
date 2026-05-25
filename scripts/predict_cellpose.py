from pathlib import Path
import argparse
import numpy as np
import tifffile as tiff
from cellpose import models, core


def parse_args():
    project_dir = Path(__file__).resolve().parents[1] / "projects" / "eucalipto"
    parser = argparse.ArgumentParser(description="Gera predicoes com um modelo Cellpose treinado.")
    default_model = "cpsam_vasos_eucalipto_v1"
    parser.add_argument("--model", default=str(project_dir / "models" / default_model))
    parser.add_argument("--input", default=str(project_dir / "data" / "test" / "images"))
    parser.add_argument("--output", default=str(project_dir / "outputs" / default_model / "predictions"))
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


def main():
    args = parse_args()

    model_path = Path(args.model)
    input_dir = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    use_gpu = core.use_gpu()

    model = models.CellposeModel(
        gpu=use_gpu,
        pretrained_model=str(model_path)
    )
    diameter = None if args.diameter <= 0 else args.diameter

    images_files = sorted(list(input_dir.glob("*.tif")))

    total = len(images_files)
    print(f"PROGRESS 0 {total} Iniciando predicao", flush=True)

    for index, img_path in enumerate(images_files, start=1):
        img = tiff.imread(img_path)
        padded_img = pad_image(img, args.padding)

        eval_result = model.eval(
            padded_img,
            diameter=diameter,
            channel_axis=None,
            normalize=True,
            cellprob_threshold=args.cellprob_threshold,
            flow_threshold=args.flow_threshold
        )
        padded_masks = eval_result[0].astype("uint16")
        masks = crop_mask(padded_masks, args.padding, img.shape)

        output_path = output_dir / f"{img_path.stem}_pred_masks.tif"
        tiff.imwrite(output_path, masks.astype("uint16"), compression="zlib")
        padded_output_path = output_dir / f"{img_path.stem}_pred_padded_masks.tif"
        tiff.imwrite(padded_output_path, padded_masks, compression="zlib")
        print(f"PROGRESS {index} {total} Predicao: {img_path.name}", flush=True)

        print(f"Predição salva: {output_path}")

if __name__ == "__main__":
    main()
