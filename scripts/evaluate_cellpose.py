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
        "precision": precision,
        "recall": recall,
        "gt_objects": int(gt_mask.max()),
        "pred_objects": int(pred_mask.max()),
    }


def normalize_metric_row(row):
    normalized = dict(row)
    for metric in ["dice", "iou", "precision", "recall"]:
        normalized[metric] = float(normalized.get(metric, 0) or 0)
    for field in ["gt_objects", "pred_objects"]:
        normalized[field] = int(float(normalized.get(field, 0) or 0))
    return normalized


def main():
    args = parse_args()

    test_masks_dir = Path(args.masks)
    predictions_dir = Path(args.predictions)
    output_csv = Path(args.output_csv)
    output_csv.parent.mkdir(parents=True, exist_ok=True)

    selected_stems = set(args.images or [])
    gt_files = sorted(test_masks_dir.glob("*_masks.tif"))
    if selected_stems:
        gt_files = [path for path in gt_files if path.name.removesuffix("_masks.tif") in selected_stems]

    if not gt_files:
        raise RuntimeError(f"Nenhuma mascara de teste encontrada em: {test_masks_dir}")

    rows = []
    total = len(gt_files)
    print(f"PROGRESS 0 {total} Iniciando avaliacao", flush=True)

    for index, gt_path in enumerate(gt_files, start=1):
        image_stem = gt_path.name.removesuffix("_masks.tif")
        pred_path = predictions_dir / f"{image_stem}_pred_masks.tif"

        if not pred_path.exists():
            print(f"Predicao nao encontrada para {image_stem}: {pred_path}", flush=True)
            print(f"PROGRESS {index} {total} Avaliacao: {image_stem}", flush=True)
            continue

        gt_mask = tiff.imread(gt_path)
        pred_mask = tiff.imread(pred_path)

        if gt_mask.shape != pred_mask.shape:
            print(f"Formato diferente para {image_stem}: GT {gt_mask.shape}, pred {pred_mask.shape}", flush=True)
            print(f"PROGRESS {index} {total} Avaliacao: {image_stem}", flush=True)
            continue

        metrics = binary_metrics(gt_mask, pred_mask)
        rows.append({"image": image_stem, **metrics})
        print(f"METRICS {image_stem}", flush=True)
        print(f"PROGRESS {index} {total} Avaliacao: {image_stem}", flush=True)

    if not rows:
        raise RuntimeError("Nenhuma predicao valida foi encontrada para avaliar.")

    fieldnames = ["image", "dice", "iou", "precision", "recall", "gt_objects", "pred_objects"]
    if selected_stems and output_csv.exists():
        with output_csv.open("r", newline="", encoding="utf-8-sig") as csv_file:
            existing_rows = [
                row
                for row in csv.DictReader(csv_file)
                if row.get("image") not in selected_stems
            ]
        rows = existing_rows + rows

    rows = [normalize_metric_row(row) for row in rows]

    with output_csv.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("\nMetricas por imagem:", flush=True)
    for row in rows:
        print(
            f"{row['image']}: "
            f"Dice={row['dice']:.4f}, "
            f"IoU={row['iou']:.4f}, "
            f"Precision={row['precision']:.4f}, "
            f"Recall={row['recall']:.4f}, "
            f"GT={row['gt_objects']}, "
            f"Pred={row['pred_objects']}",
            flush=True,
        )

    print("\nMedia:", flush=True)
    for metric in ["dice", "iou", "precision", "recall"]:
        mean_value = np.mean([row[metric] for row in rows])
        print(f"{metric}: {mean_value:.4f}", flush=True)

    print(f"\nCSV salvo em: {output_csv}", flush=True)


if __name__ == "__main__":
    main()
