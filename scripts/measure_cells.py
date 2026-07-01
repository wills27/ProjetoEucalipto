import argparse
import csv
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import numpy as np
import tifffile as tiff

from services.cell_measurements import (
    process_mask_for_csv,
    save_csv_measurements,
    save_csv_summary,
)


def parse_args():
    project_dir = Path(__file__).resolve().parents[1] / "projects" / "eucalipto"
    default_model = "cpsam_vasos_eucalipto_v1"
    parser = argparse.ArgumentParser(description="Gera CSVs de medidas de vasos/celulas segmentados.")
    parser.add_argument("--masks-dir", default=str(project_dir / "outputs" / default_model / "predictions"))
    parser.add_argument("--output-dir", default=str(project_dir / "outputs" / default_model))
    parser.add_argument("--pattern", default="*_pred_masks.tif")
    parser.add_argument("--images", nargs="*", default=None, help="Stems das imagens que devem ser medidas.")
    parser.add_argument("--unit", default="")
    parser.add_argument("--unit-per-pixel", type=float, default=0.0)
    return parser.parse_args()


def filename_from_mask_path(mask_path):
    name = mask_path.name
    for suffix in ["_pred_masks.tif", "_pred_masks.tiff", "_masks.tif", "_masks.tiff"]:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return mask_path.stem


def load_2d_mask(mask_path):
    mask = np.asarray(tiff.imread(mask_path)).astype(np.uint16)
    if mask.ndim > 2:
        mask = mask.squeeze()
    if mask.ndim != 2:
        raise ValueError(f"Mascara nao bidimensional: {mask_path.name} shape={mask.shape}")
    return mask


def main():
    args = parse_args()
    masks_dir = Path(args.masks_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    selected_stems = set(args.images or [])
    mask_paths = sorted(masks_dir.glob(args.pattern))
    if selected_stems:
        mask_paths = [path for path in mask_paths if filename_from_mask_path(path) in selected_stems]
    if not mask_paths:
        raise RuntimeError(f"Nenhuma mascara encontrada em {masks_dir} com padrao {args.pattern}.")

    all_measurements = []
    all_summaries = []
    total = len(mask_paths)
    print(f"PROGRESS 0 {total} Iniciando medidas", flush=True)

    for index, mask_path in enumerate(mask_paths, start=1):
        filename = filename_from_mask_path(mask_path)
        try:
            mask = load_2d_mask(mask_path)
        except ValueError as exc:
            print(f"[IGNORADO] {exc}", flush=True)
            print(f"PROGRESS {index} {total} Medidas: {filename}", flush=True)
            continue

        measurements, summary = process_mask_for_csv(
            mask,
            filename,
            output_dir,
            unit=args.unit,
            unit_per_pixel=args.unit_per_pixel,
        )
        all_measurements.extend(measurements)
        all_summaries.append(summary)
        print(f"MEASUREMENTS {filename}", flush=True)
        print(f"{filename}: {summary['cell_count']} vasos no total, {summary['freq_vaso_50pct']} objetos 50pct+", flush=True)
        print(f"PROGRESS {index} {total} Medidas: {filename}", flush=True)

    if not all_summaries:
        raise RuntimeError("Nenhuma mascara valida foi processada.")

    if selected_stems:
        measurements_csv = output_dir / "cell_measurements.csv"
        if measurements_csv.exists():
            with measurements_csv.open("r", encoding="utf-8-sig", newline="") as file:
                existing_measurements = [
                    row
                    for row in csv.DictReader(file, delimiter=";")
                    if row.get("filename") not in selected_stems
                ]
            all_measurements = existing_measurements + all_measurements

        summary_csv = output_dir / "cell_counts.csv"
        if summary_csv.exists():
            with summary_csv.open("r", encoding="utf-8-sig", newline="") as file:
                existing_summaries = [
                    row
                    for row in csv.DictReader(file, delimiter=";")
                    if row.get("filename") not in selected_stems
                ]
            all_summaries = existing_summaries + all_summaries

    measurements_path = save_csv_measurements(output_dir, all_measurements)
    summary_path = save_csv_summary(output_dir, all_summaries)

    print(f"\nCSV de medicoes salvo em: {measurements_path}", flush=True)
    print(f"CSV de contagens salvo em: {summary_path}", flush=True)


if __name__ == "__main__":
    main()
