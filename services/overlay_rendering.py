import numpy as np
from PIL import Image, ImageDraw, ImageFont
from skimage.measure import regionprops
from skimage.segmentation import find_boundaries

from services.cell_measurements import (
    build_mask_inteiros,
    compute_ellipse_minor_axis_by_label,
    filtrar_celulas_borda_proporcional,
)


def vessel_label_color(label_value):
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
    return palette[(int(label_value) - 1) % len(palette)]


def transparent_overlay_from_mask(mask, alpha=118):
    mask = np.asarray(mask)
    if mask.ndim > 2:
        mask = np.squeeze(mask)
    height, width = mask.shape[:2]
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    labels = mask.astype(np.int64)
    positive = labels > 0
    palette = np.asarray([vessel_label_color(index + 1) for index in range(8)], dtype=np.uint8)
    overlay[..., :3] = palette[(labels - 1) % len(palette)]
    overlay[..., 3] = np.where(positive, alpha, 0).astype(np.uint8)
    return Image.fromarray(overlay, "RGBA")


def overlay_mask_on_image(image, mask, color, alpha):
    overlay_alpha = Image.fromarray((np.asarray(mask) > 0).astype(np.uint8) * alpha).resize(image.size)
    color_image = Image.new("RGBA", image.size, (*color, 0))
    color_image.putalpha(overlay_alpha)
    return Image.alpha_composite(image.convert("RGBA"), color_image).convert("RGB")


def overlay_colored_mask_on_image(image, mask, selected_label=None, alpha=118):
    mask = np.asarray(mask)
    if mask.ndim != 2 or mask.max() == 0:
        return image.convert("RGB")

    if mask.shape[:2] != (image.height, image.width):
        mask_image = Image.fromarray(mask.astype(np.uint16)).resize(image.size, Image.Resampling.NEAREST)
        mask = np.asarray(mask_image)

    base = np.asarray(image.convert("RGB")).astype(np.float32)
    labels = [int(label) for label in np.unique(mask) if int(label) > 0]
    for label_value in labels:
        pixels = mask == label_value
        color = np.array(vessel_label_color(label_value), dtype=np.float32)
        blend = alpha / 255.0
        if selected_label and label_value == int(selected_label):
            color = np.array((255, 214, 74), dtype=np.float32)
            blend = 0.72
        base[pixels] = (base[pixels] * (1 - blend)) + (color * blend)

    if selected_label:
        selected_pixels = mask == int(selected_label)
        if selected_pixels.any():
            boundary = find_boundaries(selected_pixels, mode="outer")
            base[boundary] = np.array((255, 255, 255), dtype=np.float32)
            inner_boundary = find_boundaries(selected_pixels, mode="inner")
            base[inner_boundary] = np.array((255, 230, 90), dtype=np.float32)

    return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))


def overlay_id_font(image):
    size = max(11, min(22, int(min(image.size) / 42)))
    for font_name in ["arialbd.ttf", "arial.ttf"]:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_mask_ids(image, mask, selected_label=None, label_texts=None):
    draw = ImageDraw.Draw(image)
    font = overlay_id_font(image)
    selected_label = int(selected_label) if selected_label else None
    for region in regionprops(mask):
        y, x = region.centroid
        label = str(label_texts.get(int(region.label), region.label)) if label_texts else str(region.label)
        fill = (0, 46, 40) if region.label != selected_label else (84, 49, 0)
        stroke = (255, 255, 255)
        draw.text(
            (x + 3, y + 3),
            label,
            fill=fill,
            font=font,
            stroke_width=3,
            stroke_fill=stroke,
        )


def render_colored_id_overlay(image, mask, selected_label=None, label_texts=None):
    image = overlay_colored_mask_on_image(image, mask, selected_label=selected_label)
    draw_mask_ids(image, mask, selected_label=selected_label, label_texts=label_texts)
    return image


def render_measurement_overlay(base_image, mask, mode):
    if mode == "overlay_50pct":
        filtered = filtrar_celulas_borda_proporcional(
            mask,
            area_minima=0,
            max_borda_diametro_ratio=1.5,
            borda_expandida=8,
        )
        return overlay_colored_mask_on_image(base_image, filtered)

    filtered = build_mask_inteiros(mask)
    image = overlay_colored_mask_on_image(base_image, filtered)
    if mode == "overlay_diametro":
        image = draw_minor_axes(image, filtered)
    return image


def draw_minor_axes(image, mask):
    draw = ImageDraw.Draw(image)
    axes = compute_ellipse_minor_axis_by_label(mask)
    for ellipse in axes.values():
        y1, x1 = ellipse.axis_start_rc
        y2, x2 = ellipse.axis_end_rc
        cy, cx = ellipse.centroid_rc
        draw.line((x1, y1, x2, y2), fill=(255, 235, 59), width=3)
        draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(255, 235, 59))
    return image
