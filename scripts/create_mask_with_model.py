from pathlib import Path
import argparse

import numpy as np
import tifffile as tiff
from PIL import Image
from cellpose import core, models


def parse_args():
    parser = argparse.ArgumentParser(description="Cria _seg.npy para uma imagem usando um modelo Cellpose.")
    parser.add_argument("--model", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--padding", type=int, default=64)
    parser.add_argument("--diameter", type=float, default=0.0)
    parser.add_argument("--cellprob-threshold", type=float, default=0.0)
    parser.add_argument("--flow-threshold", type=float, default=0.4)
    return parser.parse_args()


def read_image(image_path):
    suffix = image_path.suffix.lower()
    if suffix in [".tif", ".tiff"]:
        return tiff.imread(image_path)
    return np.array(Image.open(image_path))


def pad_image(image, padding):
    if padding <= 0:
        return image
    if image.ndim == 2:
        return np.pad(image, ((padding, padding), (padding, padding)), mode="reflect")
    if image.ndim == 3:
        return np.pad(image, ((padding, padding), (padding, padding), (0, 0)), mode="reflect")
    raise ValueError(f"Formato de imagem nao suportado: {image.shape}")


def crop_mask(mask, padding):
    if padding <= 0:
        return mask
    return mask[padding:-padding, padding:-padding]


def main():
    args = parse_args()
    image_path = Path(args.image)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    use_gpu = core.use_gpu()
    model = models.CellposeModel(gpu=use_gpu, pretrained_model=str(Path(args.model)))
    diameter = None if args.diameter <= 0 else args.diameter

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
    masks = crop_mask(eval_result[0], args.padding).astype(np.uint16)
    np.save(output_path, {"masks": masks})
    tif_path = output_path.with_name(f"{output_path.stem.replace('_seg', '')}_masks.tif")
    tiff.imwrite(tif_path, masks)
    print(f"Mascara criada: {output_path}", flush=True)
    print(f"Mascara TIFF criada: {tif_path}", flush=True)


if __name__ == "__main__":
    main()
