import csv
from pathlib import Path


def count_files(folder, pattern):
    folder = Path(folder)
    if not folder.exists():
        return 0
    return len(list(folder.glob(pattern)))


def format_size(size):
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def read_metrics(path):
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as csv_file:
        return list(csv.DictReader(csv_file))


def summarize_metrics(rows):
    if not rows:
        return {}
    summary = {"images": len(rows)}
    for metric in ["dice", "iou", "precision", "recall"]:
        values = [float(row[metric]) for row in rows]
        summary[metric] = sum(values) / len(values)
    return summary
