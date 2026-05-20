import argparse
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

    mask_paths = sorted(masks_dir.glob(args.pattern))
    if not mask_paths:
        raise RuntimeError(f"Nenhuma mascara encontrada em {masks_dir} com padrao {args.pattern}.")

    all_measurements = []
    all_summaries = []

    for mask_path in mask_paths:
        try:
            mask = load_2d_mask(mask_path)
        except ValueError as exc:
            print(f"[IGNORADO] {exc}")
            continue

        filename = filename_from_mask_path(mask_path)
        measurements, summary = process_mask_for_csv(mask, filename, output_dir)
        all_measurements.extend(measurements)
        all_summaries.append(summary)
        print(f"{filename}: {summary['cell_count']} objetos inteiros, {summary['freq_vaso_50pct']} objetos 50pct+")

    if not all_summaries:
        raise RuntimeError("Nenhuma mascara valida foi processada.")

    measurements_path = save_csv_measurements(output_dir, all_measurements)
    summary_path = save_csv_summary(output_dir, all_summaries)

    print(f"\nCSV de medicoes salvo em: {measurements_path}")
    print(f"CSV de contagens salvo em: {summary_path}")


if __name__ == "__main__":
    main()
