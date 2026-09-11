from pathlib import Path
import argparse
import csv

import numpy as np
import tifffile as tiff


def parse_args():
    project_dir = Path(__file__).resolve().parents[1] / "projects" / "eucalipto"
    default_model = "cpsam_vasos_eucalipto_v1"
    parser = argparse.ArgumentParser(description="Avalia predicoes contra mascaras reais.")
    parser.add_argument("--masks", default=str(project_dir / "data" / "test" / "masks"))
    parser.add_argument("--mask-files", nargs="*", default=None, help="Arquivos de mascara especificos para avaliar.")
    parser.add_argument("--predictions", default=str(project_dir / "outputs" / default_model / "predictions"))
    parser.add_argument("--output-csv", default=str(project_dir / "outputs" / default_model / "metrics.csv"))
    parser.add_argument("--images", nargs="*", default=None, help="Stems das imagens que devem ser avaliadas.")
    return parser.parse_args()


def safe_divide(numerator, denominator):
    if denominator == 0:
        return 1.0 if numerator == 0 else 0.0
    return numerator / denominator


def binary_metrics(gt_mask, pred_mask):
    gt = gt_mask > 0
    pred = pred_mask > 0

    true_positive = np.logical_and(gt, pred).sum()
    false_positive = np.logical_and(~gt, pred).sum()
    false_negative = np.logical_and(gt, ~pred).sum()

    dice = safe_divide(2 * true_positive, (2 * true_positive) + false_positive + false_negative)
    iou = safe_divide(true_positive, true_positive + false_positive + false_negative)
    precision = safe_divide(true_positive, true_positive + false_positive)
    recall = safe_divide(true_positive, true_positive + false_negative)

    return {
        "dice": dice,
        "iou": iou,
        "precisao": precision,
        "revocacao": recall,
        "objetos_reais": int(gt_mask.max()),
        "objetos_preditos": int(pred_mask.max()),
    }


def parse_decimal(value):
    if isinstance(value, str):
        value = value.replace(",", ".")
    return float(value)


LEGACY_METRIC_ALIASES = {
    "imagem": "image",
    "precisao": "precision",
    "revocacao": "recall",
    "objetos_reais": "gt_objects",
    "objetos_preditos": "pred_objects",
}


def normalize_metric_row(row):
    normalized = dict(row)
    for new_key, legacy_key in LEGACY_METRIC_ALIASES.items():
        if new_key not in normalized and legacy_key in normalized:
            normalized[new_key] = normalized[legacy_key]
    for metric in ["dice", "iou", "precisao", "revocacao"]:
        normalized[metric] = round(parse_decimal(normalized.get(metric, 0) or 0), 2)
    for field in ["objetos_reais", "objetos_preditos"]:
        normalized[field] = int(parse_decimal(normalized.get(field, 0) or 0))
    return normalized


def format_metric_row(row):
    formatted = dict(row)
    for metric in ["dice", "iou", "precisao", "revocacao"]:
        formatted[metric] = f"{row[metric]:.2f}".replace(".", ",")
    return formatted


def load_mask(mask_path):
    if mask_path.suffix.lower() == ".npy":
        data = np.load(mask_path, allow_pickle=True).item()
        if "masks" not in data or data["masks"] is None:
            raise ValueError(f"Mascara invalida em {mask_path}")
        return data["masks"]
    return tiff.imread(mask_path)


def stem_from_mask_path(mask_path):
    name = mask_path.name
    if name.endswith("_seg.npy"):
        return name.removesuffix("_seg.npy")
    if name.endswith("_masks.tiff"):
        return name.removesuffix("_masks.tiff")
    return name.removesuffix("_masks.tif")


def main():
    args = parse_args()

    masks_dir = Path(args.masks)
    predictions_dir = Path(args.predictions)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    selected_stems = set(args.images or [])
    if args.mask_files:
        gt_files = sorted(Path(path) for path in args.mask_files)
    else:
        gt_files = sorted(masks_dir.glob("*_masks.tif"))
    if selected_stems:
        gt_files = [path for path in gt_files if stem_from_mask_path(path) in selected_stems]

    if not gt_files:
        raise RuntimeError(f"Nenhuma mascara encontrada em: {masks_dir}")

    rows = []
    total = len(gt_files)
    print(f"PROGRESS 0 {total} Iniciando avaliacao", flush=True)

    for index, gt_path in enumerate(gt_files, start=1):
        image_stem = stem_from_mask_path(gt_path)
        pred_path = predictions_dir / f"{image_stem}_pred_masks.tif"

        if not pred_path.exists():
            print(f"Predicao nao encontrada para {image_stem}: {pred_path}", flush=True)
            print(f"PROGRESS {index} {total} Avaliacao: {image_stem}", flush=True)
            continue

        gt_mask = load_mask(gt_path)
        pred_mask = tiff.imread(pred_path)

        if gt_mask.shape != pred_mask.shape:
            print(f"Formato diferente para {image_stem}: GT {gt_mask.shape}, pred {pred_mask.shape}", flush=True)
            print(f"PROGRESS {index} {total} Avaliacao: {image_stem}", flush=True)
            continue

        metrics = binary_metrics(gt_mask, pred_mask)
        rows.append({"imagem": image_stem, **metrics})
        print(f"METRICS {image_stem}", flush=True)
        print(f"PROGRESS {index} {total} Avaliacao: {image_stem}", flush=True)

    if not rows:
        raise RuntimeError("Nenhuma predicao valida foi encontrada para avaliar.")

    fieldnames = ["imagem", "dice", "iou", "precisao", "revocacao", "objetos_reais", "objetos_preditos"]
    if selected_stems and output_csv.exists():
        with output_csv.open("r", newline="", encoding="utf-8-sig") as csv_file:
            sample = csv_file.readline()
            csv_file.seek(0)
            delimiter = ";" if ";" in sample else ","
            existing_rows = [
                row
                for row in csv.DictReader(csv_file, delimiter=delimiter)
                if row.get("imagem", row.get("image")) not in selected_stems
            ]
        rows = existing_rows + rows

    rows = [normalize_metric_row(row) for row in rows]

    with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        writer.writerows(format_metric_row(row) for row in rows)

    print("\nMetricas por imagem:", flush=True)
    for row in rows:
        print(
            f"{row['imagem']}: "
            f"Dice={row['dice']:.4f}, "
            f"IoU={row['iou']:.4f}, "
            f"Precisao={row['precisao']:.4f}, "
            f"Revocacao={row['revocacao']:.4f}, "
            f"GT={row['objetos_reais']}, "
            f"Pred={row['objetos_preditos']}",
            flush=True,
        )

    print("\nMedia:", flush=True)
    for metric in ["dice", "iou", "precisao", "revocacao"]:
        mean_value = np.mean([row[metric] for row in rows])
        print(f"{metric}: {mean_value:.4f}", flush=True)

    print(f"\nCSV salvo em: {output_csv}", flush=True)


if __name__ == "__main__":
    main()
