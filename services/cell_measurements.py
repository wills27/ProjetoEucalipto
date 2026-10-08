from dataclasses import dataclass
import os

import numpy as np
import pandas as pd
from skimage.measure import regionprops


MEASUREMENT_COLUMNS = [
    "imagem",
    "id_vaso",
    "area_px",
    "diametro_menor_px",
    "diametro_cruzado_px",
    "area_calibrada",
    "diametro_menor_calibrado",
    "diametro_cruzado_calibrado",
    "unidade",
]

SUMMARY_COLUMNS = [
    "imagem",
    "quantidade_vasos",
    "freq_vaso_50pct",
    "freq_vaso_inteiros",
    "pixels_area_ocupada",
    "percentual_area_ocupada",
    "media_area_px",
    "media_diametro_menor_px",
    "media_diametro_cruzado_px",
    "media_area_calibrada",
    "media_diametro_menor_calibrado",
    "media_diametro_cruzado_calibrado",
    "unidade",
]

WHOLE_CELL_BORDER_EXCLUSION = 2

# Fatores de conversao pra mm, usados so pra expressar "vasos por mm2" (ver
# vessel_frequency_per_mm2) sempre no mesmo padrao, nao importa a unidade de
# calibracao configurada (um/mm/nm).
_UNIT_TO_MM = {"mm": 1.0, "um": 0.001, "µm": 0.001, "nm": 1e-6}


def vessel_frequency_per_mm2(count, area_total_img_px, unit, unit_per_pixel):
    """'Vessel frequency' no sentido padrao da anatomia da madeira (IAWA):
    vasos por mm2 da area TOTAL da imagem examinada (nao da area pintada
    pelos vasos) - isso que torna o numero comparavel entre imagens de
    tamanhos/ampliacoes diferentes, e com a literatura. Sempre em mm2,
    convertendo a partir da unidade de calibracao configurada, pra o numero
    nao depender de ter calibrado em um, mm ou nm. Sem calibracao (ou unidade
    nao reconhecida, ja que a unidade e um campo livre) nao da pra converter
    pixel em area real, entao retorna None em vez de arriscar um numero
    errado."""
    has_calibration = unit and unit_per_pixel and unit_per_pixel > 0
    if not has_calibration:
        return None
    mm_per_unit = _UNIT_TO_MM.get(unit.strip().lower())
    if mm_per_unit is None:
        return None
    area_mm2 = area_total_img_px * (unit_per_pixel ** 2) * (mm_per_unit ** 2)
    if area_mm2 <= 0:
        return None
    return count / area_mm2


@dataclass(frozen=True)
class EllipseMinorAxisResult:
    label: int
    minor_axis_length: float
    centroid_rc: tuple[float, float]
    axis_start_rc: tuple[float, float]
    axis_end_rc: tuple[float, float]
    major_axis_length: float = 0.0
    major_axis_start_rc: tuple[float, float] = (0.0, 0.0)
    major_axis_end_rc: tuple[float, float] = (0.0, 0.0)
    diametro_cruzado: float = 0.0


def filtrar_celulas_borda_proporcional(
    masks,
    area_minima=0,
    max_borda_diametro_ratio=1.5,
    borda_expandida=8,
    min_fracao_area_util=0.75,
):
    H, W = masks.shape
    regions = regionprops(masks)
    labels_a_manter = []

    area_util_mask = np.zeros_like(masks, dtype=bool)
    area_util_mask[
        borda_expandida : H - borda_expandida,
        borda_expandida : W - borda_expandida,
    ] = True

    for r in regions:
        coords = r.coords
        ys = coords[:, 0]
        xs = coords[:, 1]
        area = r.area

        if area < area_minima:
            continue

        mask_celula = masks == r.label
        pixels_area_util = (mask_celula & area_util_mask).sum()
        fracao_util = pixels_area_util / mask_celula.sum()

        if fracao_util < min_fracao_area_util:
            continue

        bordas = []

        if (ys < borda_expandida).any():
            bordas.append("topo")
        if (ys >= H - borda_expandida).any():
            bordas.append("base")
        if (xs < borda_expandida).any():
            bordas.append("esquerda")
        if (xs >= W - borda_expandida).any():
            bordas.append("direita")

        diametro_h = xs.max() - xs.min() + 1
        diametro_v = ys.max() - ys.min() + 1

        if len(bordas) > 0:
            diametro_aprox = (diametro_h + diametro_v) / 2

            linha_borda = 0

            if "topo" in bordas:
                xs_topo = xs[ys < borda_expandida]
                linha_borda += len(np.unique(xs_topo)) if xs_topo.size > 0 else 0

            if "base" in bordas:
                xs_base = xs[ys >= H - borda_expandida]
                linha_borda += len(np.unique(xs_base)) if xs_base.size > 0 else 0

            if "esquerda" in bordas:
                ys_esq = ys[xs < borda_expandida]
                linha_borda += len(np.unique(ys_esq)) if ys_esq.size > 0 else 0

            if "direita" in bordas:
                ys_dir = ys[xs >= W - borda_expandida]
                linha_borda += len(np.unique(ys_dir)) if ys_dir.size > 0 else 0

            if linha_borda > max_borda_diametro_ratio * diametro_aprox:
                continue

        labels_a_manter.append(r.label)

    return np.where(np.isin(masks, labels_a_manter), masks, 0)


def compute_ellipse_axes_by_label(mask):
    """Para cada vaso, ajusta uma elipse (mesmos momentos de 2a ordem que a
    regiao) e devolve os dois eixos: o menor (ja usado no modo 'Diametro') e
    o maior (novo, usado no 'Diametro cruzado'). 'diametro_cruzado' e a media
    dos dois - uma aproximacao mais robusta que o eixo menor sozinho pra
    vasos alongados/ovais, onde o eixo menor sozinho subestima o diametro."""
    results = {}

    for p in regionprops(mask):
        minor = float(getattr(p, "axis_minor_length", 0.0) or 0.0)
        major = float(getattr(p, "axis_major_length", 0.0) or 0.0)

        if minor <= 0.0:
            continue

        cy, cx = float(p.centroid[0]), float(p.centroid[1])
        theta = float(p.orientation)
        half_minor = 0.5 * minor

        dx_minor = np.cos(theta) * half_minor
        dy_minor = -np.sin(theta) * half_minor

        x1, y1 = cx - dx_minor, cy - dy_minor
        x2, y2 = cx + dx_minor, cy + dy_minor

        major_start = (0.0, 0.0)
        major_end = (0.0, 0.0)
        diametro_cruzado = 0.0
        if major > 0.0:
            half_major = 0.5 * major
            # Perpendicular ao eixo menor (mesma formula canonica do skimage
            # pra desenhar os dois eixos da elipse a partir de 'orientation').
            dx_major = -np.sin(theta) * half_major
            dy_major = -np.cos(theta) * half_major
            mx1, my1 = cx - dx_major, cy - dy_major
            mx2, my2 = cx + dx_major, cy + dy_major
            major_start = (my1, mx1)
            major_end = (my2, mx2)
            diametro_cruzado = (minor + major) / 2.0

        results[int(p.label)] = EllipseMinorAxisResult(
            label=int(p.label),
            minor_axis_length=minor,
            centroid_rc=(cy, cx),
            axis_start_rc=(y1, x1),
            axis_end_rc=(y2, x2),
            major_axis_length=major,
            major_axis_start_rc=major_start,
            major_axis_end_rc=major_end,
            diametro_cruzado=diametro_cruzado,
        )

    return results


def remove_labels_near_image_border(mask, border_width=2):
    if border_width <= 0:
        return mask

    H, W = mask.shape
    border = np.zeros_like(mask, dtype=bool)
    border[:border_width, :] = True
    border[H - border_width :, :] = True
    border[:, :border_width] = True
    border[:, W - border_width :] = True

    labels_to_remove = np.unique(mask[border])
    labels_to_remove = labels_to_remove[labels_to_remove != 0]
    if labels_to_remove.size == 0:
        return mask

    return np.where(np.isin(mask, labels_to_remove), 0, mask)


def build_mask_inteiros(mask):
    filtered = filtrar_celulas_borda_proporcional(
        mask,
        area_minima=0,
        max_borda_diametro_ratio=0,
        borda_expandida=1,
        min_fracao_area_util=0.9,
    )
    return remove_labels_near_image_border(filtered, border_width=WHOLE_CELL_BORDER_EXCLUSION)


def build_measurement_rows(filename, props_inteiros, ellipse_by_label, unit="", unit_per_pixel=0.0):
    rows = []
    has_calibration = unit and unit_per_pixel and unit_per_pixel > 0

    for i, p in enumerate(props_inteiros, start=1):
        ellipse = ellipse_by_label.get(p.label)
        area_px = float(p.area)
        diameter_px = float(ellipse.minor_axis_length) if ellipse else None
        diametro_cruzado_px = float(ellipse.diametro_cruzado) if ellipse and ellipse.diametro_cruzado else None

        rows.append(
            {
                "imagem": filename,
                "id_vaso": i,
                "area_px": round(area_px, 2),
                "diametro_menor_px": round(diameter_px, 2) if diameter_px is not None else None,
                "diametro_cruzado_px": round(diametro_cruzado_px, 2) if diametro_cruzado_px is not None else None,
                "area_calibrada": round(area_px * (unit_per_pixel ** 2), 2) if has_calibration else None,
                "diametro_menor_calibrado": round(diameter_px * unit_per_pixel, 2) if has_calibration and diameter_px is not None else None,
                "diametro_cruzado_calibrado": round(diametro_cruzado_px * unit_per_pixel, 2) if has_calibration and diametro_cruzado_px is not None else None,
                "unidade": unit if has_calibration else "",
            }
        )

    return rows


def build_summary_row(
    filename,
    props_inteiros,
    ellipse_by_label,
    area_total_vasos,
    area_total_img,
    freq_vaso_50pct_count,
    total_vasos_count,
    unit="",
    unit_per_pixel=0.0,
):
    areas_inteiros = [p.area for p in props_inteiros]
    diametros_inteiros = [
        ellipse_by_label[p.label].minor_axis_length
        for p in props_inteiros
        if p.label in ellipse_by_label
    ]
    diametros_cruzados_inteiros = [
        ellipse_by_label[p.label].diametro_cruzado
        for p in props_inteiros
        if p.label in ellipse_by_label and ellipse_by_label[p.label].diametro_cruzado
    ]

    media_area = np.mean(areas_inteiros) if areas_inteiros else 0
    media_diametro = np.mean(diametros_inteiros) if diametros_inteiros else 0
    media_diametro_cruzado = np.mean(diametros_cruzados_inteiros) if diametros_cruzados_inteiros else 0
    fracao_area_vasos = area_total_vasos / area_total_img
    has_calibration = unit and unit_per_pixel and unit_per_pixel > 0

    # "Frequencia de vasos" e densidade (vasos/mm2 de area total da imagem),
    # nao contagem bruta - ver vessel_frequency_per_mm2. A contagem bruta de
    # vasos continua disponivel em "quantidade_vasos" (todos os vasos,
    # inteiros ou nao).
    freq_vaso_50pct = vessel_frequency_per_mm2(freq_vaso_50pct_count, area_total_img, unit, unit_per_pixel)
    freq_vaso_inteiros = vessel_frequency_per_mm2(len(props_inteiros), area_total_img, unit, unit_per_pixel)

    return {
        "imagem": filename,
        "quantidade_vasos": total_vasos_count,
        "pixels_area_ocupada": int(area_total_vasos),
        "percentual_area_ocupada": float(round(fracao_area_vasos * 100, 2)),
        "freq_vaso_50pct": round(freq_vaso_50pct, 2) if freq_vaso_50pct is not None else None,
        "freq_vaso_inteiros": round(freq_vaso_inteiros, 2) if freq_vaso_inteiros is not None else None,
        "media_area_px": round(float(media_area), 2),
        "media_diametro_menor_px": round(float(media_diametro), 2),
        "media_diametro_cruzado_px": round(float(media_diametro_cruzado), 2),
        "media_area_calibrada": round(float(media_area * (unit_per_pixel ** 2)), 2) if has_calibration else None,
        "media_diametro_menor_calibrado": round(float(media_diametro * unit_per_pixel), 2) if has_calibration else None,
        "media_diametro_cruzado_calibrado": round(float(media_diametro_cruzado * unit_per_pixel), 2) if has_calibration else None,
        "unidade": unit if has_calibration else "",
    }


def process_mask_for_csv(mask, filename, output_dir=None, unit="", unit_per_pixel=0.0):
    H, W = mask.shape

    mask_50pct = filtrar_celulas_borda_proporcional(
        mask,
        area_minima=0,
        max_borda_diametro_ratio=1.5,
        borda_expandida=8,
    )
    props_50pct = regionprops(mask_50pct)
    freq_vaso_50pct = len(props_50pct)

    mask_inteiros = build_mask_inteiros(mask)
    props_inteiros = regionprops(mask_inteiros)
    ellipse_by_label_inteiros = compute_ellipse_axes_by_label(mask_inteiros)

    props_todos = regionprops(mask)
    ellipse_by_label_todos = compute_ellipse_axes_by_label(mask)
    area_total_vasos = sum(p.area for p in props_todos)
    area_total_img = H * W

    measurements = build_measurement_rows(filename, props_todos, ellipse_by_label_todos, unit, unit_per_pixel)
    summary = build_summary_row(
        filename,
        props_inteiros,
        ellipse_by_label_inteiros,
        area_total_vasos,
        area_total_img,
        freq_vaso_50pct,
        len(props_todos),
        unit,
        unit_per_pixel,
    )

    return measurements, summary


def save_csv_measurements(output_dir, rows):
    df = pd.DataFrame(rows, columns=MEASUREMENT_COLUMNS).round(2)
    path = os.path.join(output_dir, "cell_measurements.csv")
    df.to_csv(path, index=False, sep=";", decimal=",")
    return path


def save_csv_summary(output_dir, rows):
    df = pd.DataFrame(rows, columns=SUMMARY_COLUMNS).round(2)
    path = os.path.join(output_dir, "cell_counts.csv")
    df.to_csv(path, index=False, sep=";", decimal=",")
    return path
