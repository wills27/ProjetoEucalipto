from pathlib import Path

import numpy as np
from PIL import Image


def build_dataset_preview_image(row_data, preview_size):
    image_path = Path(row_data.get("image_path", ""))
    seg_path = Path(row_data.get("seg_path", ""))
    tif_mask_path = Path(row_data.get("tif_mask_path", ""))
    if not image_path.exists():
        return None

    with Image.open(image_path) as source_image:
        image = source_image.convert("RGB")
        image.thumbnail(preview_size, Image.Resampling.BILINEAR)

    mask = None
    if seg_path.exists():
        mask = np.load(seg_path, allow_pickle=True).item().get("masks")
    elif tif_mask_path.exists():
        with Image.open(tif_mask_path) as mask_image:
            mask_image = mask_image.resize(image.size, Image.Resampling.NEAREST)
            mask = np.array(mask_image)

    if mask is not None and np.max(mask) > 0:
        mask_image = Image.fromarray((np.asarray(mask) > 0).astype(np.uint8) * 120)
        if seg_path.exists():
            mask_image = mask_image.resize(image.size, Image.Resampling.NEAREST)
        color = Image.new("RGBA", image.size, (22, 107, 92, 0))
        color.putalpha(mask_image)
        image = Image.alpha_composite(image.convert("RGBA"), color).convert("RGB")

    return image
