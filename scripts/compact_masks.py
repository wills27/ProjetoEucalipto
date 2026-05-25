from pathlib import Path
import argparse

import numpy as np
import tifffile as tiff


def parse_args():
    parser = argparse.ArgumentParser(description="Converte mascaras _seg.npy para TIFF comprimido e remove duplicatas.")
    parser.add_argument("--project-dir", required=True)
    return parser.parse_args()


def target_tif_path(seg_path):
    name = seg_path.name
    if name.endswith("_pred_seg.npy"):
        return seg_path.with_name(name.replace("_pred_seg.npy", "_pred_masks.tif"))
    if name.endswith("_seg.npy"):
        return seg_path.with_name(name.replace("_seg.npy", "_masks.tif"))
    return seg_path.with_suffix(".tif")


def load_seg_mask(seg_path):
    data = np.load(seg_path, allow_pickle=True).item()
    mask = data.get("masks")
    if mask is None:
        raise ValueError("arquivo nao contem a chave 'masks'")
    mask = np.asarray(mask).astype(np.uint16)
    if mask.ndim > 2:
        mask = np.squeeze(mask)
    if mask.ndim != 2:
        raise ValueError(f"mascara com dimensoes invalidas: {mask.shape}")
    return mask


def load_tif_mask(tif_path):
    mask = np.asarray(tiff.imread(tif_path)).astype(np.uint16)
    if mask.ndim > 2:
        mask = np.squeeze(mask)
    if mask.ndim != 2:
        raise ValueError(f"TIFF com dimensoes invalidas: {mask.shape}")
    return mask


def write_mask(tif_path, mask):
    tif_path.parent.mkdir(parents=True, exist_ok=True)
    tiff.imwrite(tif_path, mask.astype(np.uint16), compression="zlib")


def compact_one(seg_path):
    tif_path = target_tif_path(seg_path)
    seg_mask = load_seg_mask(seg_path)

    if tif_path.exists():
        tif_mask = load_tif_mask(tif_path)
        if tif_mask.shape == seg_mask.shape and np.array_equal(tif_mask, seg_mask):
            seg_path.unlink()
            return "removido_npy_duplicado", tif_path

        if tif_path.stat().st_mtime >= seg_path.stat().st_mtime:
            seg_path.unlink()
            return "mantido_tiff_mais_recente", tif_path

    write_mask(tif_path, seg_mask)
    written_mask = load_tif_mask(tif_path)
    if written_mask.shape != seg_mask.shape or not np.array_equal(written_mask, seg_mask):
        raise ValueError("validacao falhou apos escrever TIFF")

    seg_path.unlink()
    return "convertido", tif_path


def main():
    args = parse_args()
    project_dir = Path(args.project_dir)
    seg_files = sorted(project_dir.rglob("*_seg.npy"))

    total = len(seg_files)
    print(f"PROGRESS 0 {max(1, total)} Iniciando compactacao de mascaras", flush=True)

    converted = 0
    removed_duplicates = 0
    kept_newer_tiffs = 0
    failed = []

    for index, seg_path in enumerate(seg_files, start=1):
        try:
            status, tif_path = compact_one(seg_path)
            if status == "convertido":
                converted += 1
            elif status == "removido_npy_duplicado":
                removed_duplicates += 1
            elif status == "mantido_tiff_mais_recente":
                kept_newer_tiffs += 1
            print(f"COMPACT {status} {seg_path} -> {tif_path}", flush=True)
        except Exception as exc:
            failed.append(f"{seg_path}: {exc}")
            print(f"COMPACT erro {seg_path}: {exc}", flush=True)

        print(f"PROGRESS {index} {max(1, total)} Compactando: {seg_path.name}", flush=True)

    print(
        "\nResumo da compactacao:\n"
        f"Convertidos para TIFF: {converted}\n"
        f"NPY duplicados removidos: {removed_duplicates}\n"
        f"TIFFs mais recentes mantidos: {kept_newer_tiffs}\n"
        f"Falhas: {len(failed)}\n",
        flush=True,
    )
    if failed:
        print("Falhas:", flush=True)
        print("\n".join(failed[:50]), flush=True)


if __name__ == "__main__":
    main()
