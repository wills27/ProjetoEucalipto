import gc
import time

import numpy as np
import tifffile as tiff
from PIL import Image, ImageDraw
from skimage.measure import label

MIN_MASK_PIXELS = 20


def load_mask_file(seg_path, tif_mask_path):
    if seg_path.exists():
        data = np.load(seg_path, allow_pickle=True).item()
        return data.get("masks")
    if tif_mask_path.exists():
        with Image.open(tif_mask_path) as image:
            return np.array(image)
    for suffix in [".tif", ".tiff"]:
        alternate_path = seg_path.with_name(f"{seg_path.stem.replace('_seg', '')}_masks{suffix}")
        if alternate_path.exists():
            with Image.open(alternate_path) as image:
                return np.array(image)
    return None


def validate_mask_content(mask, min_pixels=MIN_MASK_PIXELS, min_objects=1):
    if mask is None:
        return {
            "valid": False,
            "status": "Sem mascara",
            "pixel_count": 0,
            "object_count": 0,
            "reason": "arquivo ausente",
        }

    mask = np.asarray(mask)
    if mask.size == 0:
        return {
            "valid": False,
            "status": "Mascara vazia",
            "pixel_count": 0,
            "object_count": 0,
            "reason": "sem pixels",
        }

    positive = mask > 0
    pixel_count = int(np.count_nonzero(positive))
    object_count = int(len([value for value in np.unique(mask) if int(value) > 0]))
    if object_count < min_objects or pixel_count == 0:
        return {
            "valid": False,
            "status": "Mascara vazia",
            "pixel_count": pixel_count,
            "object_count": object_count,
            "reason": "sem objeto desenhado",
        }
    if pixel_count < min_pixels:
        return {
            "valid": False,
            "status": "Mascara pequena",
            "pixel_count": pixel_count,
            "object_count": object_count,
            "reason": f"menos de {min_pixels} pixels",
        }
    return {
        "valid": True,
        "status": "OK",
        "pixel_count": pixel_count,
        "object_count": object_count,
        "reason": "",
    }


def validate_mask_file(seg_path, tif_mask_path, min_pixels=MIN_MASK_PIXELS):
    try:
        mask = load_mask_file(seg_path, tif_mask_path)
    except Exception as exc:
        return {
            "valid": False,
            "status": "Mascara invalida",
            "pixel_count": 0,
            "object_count": 0,
            "reason": str(exc),
        }
    return validate_mask_content(mask, min_pixels=min_pixels)


def load_mask(seg_path, tif_mask_path, image_size):
    mask = load_mask_file(seg_path, tif_mask_path)
    if mask is None:
        return np.zeros((image_size[1], image_size[0]), dtype=np.uint16)
    mask = np.asarray(mask).astype(np.uint16)
    if mask.shape[:2] != (image_size[1], image_size[0]):
        mask_image = Image.fromarray(mask).resize(image_size, Image.Resampling.NEAREST)
        mask = np.array(mask_image).astype(np.uint16)
    return mask


MASK_PALETTE = [
    (22, 107, 92),
    (208, 89, 75),
    (48, 111, 181),
    (214, 162, 58),
    (127, 88, 175),
    (59, 145, 112),
    (202, 96, 139),
    (80, 137, 170),
    (178, 119, 48),
    (100, 119, 204),
]


def color_for_label(label_value):
    label_value = int(label_value)
    if label_value <= 0:
        return 0, 0, 0
    return MASK_PALETTE[(label_value - 1) % len(MASK_PALETTE)]


def overlay_mask(image, mask, color=(22, 107, 92), alpha=110, per_label=False):
    if mask is None or np.max(mask) == 0:
        return image
    mask = np.asarray(mask)
    if mask.shape[:2] != (image.height, image.width):
        mask_image = Image.fromarray(mask.astype(np.uint16)).resize(image.size, Image.Resampling.NEAREST)
        mask = np.asarray(mask_image)

    color_image = Image.new("RGBA", image.size, (*color, 0))
    if per_label:
        palette = np.asarray(MASK_PALETTE, dtype=np.uint8)
        positive = mask > 0
        color_array = np.zeros((image.height, image.width, 4), dtype=np.uint8)
        color_array[..., :3] = palette[(mask.astype(np.int64) - 1) % len(palette)]
        color_array[..., 3] = np.where(positive, alpha, 0).astype(np.uint8)
        color_image = Image.fromarray(color_array, "RGBA")
    else:
        mask_image = Image.fromarray((mask > 0).astype(np.uint8) * alpha)
        color_image.putalpha(mask_image)
    return Image.alpha_composite(image.convert("RGBA"), color_image).convert("RGB")


def draw_contour_preview(image, points, marker_radius=9, line_width=5, smooth=True, smooth_iterations=2):
    preview = image.convert("RGBA")
    layer = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    line_color = (0, 210, 96, 210)
    start_fill = (0, 210, 96, 170)
    start_outline = (0, 150, 68, 230)
    marker_radius = max(3, int(marker_radius))
    inner_radius = max(2, int(marker_radius * 0.55))
    line_width = max(1, int(line_width))
    preview_points = (
        smooth_points(points, iterations=smooth_iterations, closed=False)
        if smooth and len(points) > 3
        else points
    )
    if len(preview_points) > 1:
        draw.line(preview_points, fill=line_color, width=line_width, joint="curve")
    elif points:
        x, y = points[0]
        draw.ellipse((x - inner_radius, y - inner_radius, x + inner_radius, y + inner_radius), fill=start_fill)
    if points:
        x, y = points[0]
        outline_width = max(2, min(6, int(round(marker_radius / 3))))
        draw.ellipse((x - marker_radius, y - marker_radius, x + marker_radius, y + marker_radius), outline=start_outline, width=outline_width)
    return Image.alpha_composite(preview, layer).convert("RGB")


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


def contour_area(shape, points, smooth=False):
    mask_image = Image.new("L", (shape[1], shape[0]), 0)
    draw = ImageDraw.Draw(mask_image)
    polygon_points = close_contour_through_image_border(shape, points)
    polygon_points = smooth_points(polygon_points, iterations=3, closed=True) if smooth else polygon_points
    draw.polygon(polygon_points, fill=1)
    return np.array(mask_image, dtype=bool)


def close_contour_through_image_border(shape, points):
    if len(points) < 3:
        return points
    height, width = shape
    start = points[0]
    end = points[-1]
    if not is_border_point(start, width, height) or not is_border_point(end, width, height):
        return points
    border_points = shortest_border_path(end, start, width, height)
    if not border_points:
        return points
    return [*points, *border_points]


def is_border_point(point, width, height):
    x, y = point
    return x <= 0 or y <= 0 or x >= width - 1 or y >= height - 1


def shortest_border_path(start, end, width, height):
    perimeter = image_border_perimeter(width, height)
    if not perimeter:
        return []
    start_index = closest_border_index(start, perimeter)
    end_index = closest_border_index(end, perimeter)
    if start_index == end_index:
        return []

    forward = walk_border(perimeter, start_index, end_index, 1)
    backward = walk_border(perimeter, start_index, end_index, -1)
    return forward if len(forward) <= len(backward) else backward


def walk_border(perimeter, start_index, end_index, direction):
    points = []
    index = start_index
    while index != end_index:
        index = (index + direction) % len(perimeter)
        points.append(perimeter[index])
    return points


def image_border_perimeter(width, height):
    if width <= 0 or height <= 0:
        return []
    top = [(x, 0) for x in range(width)]
    right = [(width - 1, y) for y in range(1, height)]
    bottom = [(x, height - 1) for x in range(width - 2, -1, -1)] if height > 1 else []
    left = [(0, y) for y in range(height - 2, 0, -1)] if width > 1 else []
    return top + right + bottom + left


def closest_border_index(point, perimeter):
    x, y = point
    return min(
        range(len(perimeter)),
        key=lambda index: (perimeter[index][0] - x) ** 2 + (perimeter[index][1] - y) ** 2,
    )


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


def replace_file_with_retries(temp_path, target_path, attempts=8):
    last_error = None
    for _attempt in range(attempts):
        try:
            temp_path.replace(target_path)
            return
        except OSError as exc:
            last_error = exc

        gc.collect()
        try:
            if target_path.exists():
                target_path.chmod(0o666)
                target_path.unlink()
            temp_path.replace(target_path)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.25)

    raise last_error


def save_mask(seg_path, tif_path, mask):
    tif_path.parent.mkdir(parents=True, exist_ok=True)
    mask = mask.astype(np.uint16)
    temp_path = tif_path.with_name(f"{tif_path.stem}.tmp{tif_path.suffix}")
    tiff.imwrite(temp_path, mask, compression="zlib")
    replace_file_with_retries(temp_path, tif_path)
    if seg_path.exists():
        seg_path.unlink()
