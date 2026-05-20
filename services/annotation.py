import numpy as np
import tifffile as tiff
from PIL import Image, ImageDraw
from skimage.measure import label


def load_mask(seg_path, tif_mask_path, image_size):
    mask = None
    if seg_path.exists():
        mask = np.load(seg_path, allow_pickle=True).item().get("masks")
    elif tif_mask_path.exists():
        mask = np.array(Image.open(tif_mask_path))
    if mask is None:
        return np.zeros((image_size[1], image_size[0]), dtype=np.uint16)
    mask = np.asarray(mask).astype(np.uint16)
    if mask.shape[:2] != (image_size[1], image_size[0]):
        mask_image = Image.fromarray(mask).resize(image_size, Image.Resampling.NEAREST)
        mask = np.array(mask_image).astype(np.uint16)
    return mask


def overlay_mask(image, mask, color=(22, 107, 92), alpha=110):
    if mask is None or np.max(mask) == 0:
        return image
    mask_image = Image.fromarray((np.asarray(mask) > 0).astype(np.uint8) * alpha).resize(image.size)
    color_image = Image.new("RGBA", image.size, (*color, 0))
    color_image.putalpha(mask_image)
    return Image.alpha_composite(image.convert("RGBA"), color_image).convert("RGB")


def draw_contour_preview(image, points):
    preview = image.convert("RGBA")
    draw = ImageDraw.Draw(preview)
    line_color = (49, 95, 159, 105)
    start_color = (190, 54, 48, 145)
    if len(points) > 1:
        draw.line(smooth_points(points), fill=line_color, width=5, joint="curve")
    elif points:
        x, y = points[0]
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=start_color)
    if points:
        x, y = points[0]
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), outline=start_color, width=3)
    return preview.convert("RGB")


def draw_stroke_preview(image, points, radius, tool):
    preview = image.convert("RGBA")
    draw = ImageDraw.Draw(preview)
    color = (22, 107, 92, 180) if tool == "brush" else (180, 60, 50, 180)
    if len(points) > 1:
        draw.line(points, fill=color, width=max(1, radius * 2))
    for x, y in points:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    return preview.convert("RGB")


def smooth_points(points, iterations=2, closed=False):
    if len(points) < 3:
        return points
    smoothed = [(float(x), float(y)) for x, y in points]
    for _iteration in range(iterations):
        source = smoothed if closed else [smoothed[0], *smoothed, smoothed[-1]]
        next_points = []
        limit = len(source) if closed else len(source) - 1
        for index in range(limit):
            p0 = source[index]
            p1 = source[(index + 1) % len(source)]
            q = (0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1])
            r = (0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1])
            next_points.extend([q, r])
        smoothed = next_points
    return [(int(round(x)), int(round(y))) for x, y in smoothed]


def contour_area(shape, points):
    mask_image = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(mask_image)
    draw.polygon(smooth_points(points, closed=True), fill=1)
    return np.array(mask_image, dtype=bool)


def next_label_value(mask):
    return int(np.max(mask)) + 1


def add_non_overlapping_area(mask, area, value=None):
    if value is None:
        value = next_label_value(mask)
    mask[np.logical_and(area, mask == 0)] = value
    return mask


def connected_component_at(mask, point):
    image_x, image_y = point
    label_value = int(mask[image_y, image_x])
    if label_value == 0:
        return None, 0
    same_label = mask == label_value
    components = label(same_label, connectivity=2)
    component_id = int(components[image_y, image_x])
    if component_id == 0:
        return None, label_value
    return components == component_id, label_value


def apply_brush(mask, point, radius, tool, value=None):
    image_x, image_y = point
    y_indices, x_indices = np.ogrid[: mask.shape[0], : mask.shape[1]]
    area = (x_indices - image_x) ** 2 + (y_indices - image_y) ** 2 <= radius ** 2
    if tool == "brush":
        add_non_overlapping_area(mask, area, value)
    else:
        mask[area] = 0
    return mask


def save_mask(seg_path, tif_path, mask):
    seg_path.parent.mkdir(parents=True, exist_ok=True)
    mask = mask.astype(np.uint16)
    np.save(seg_path, {"masks": mask})
    tiff.imwrite(tif_path, mask)
