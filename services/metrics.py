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


def parse_decimal(value):
    if isinstance(value, str):
        value = value.replace(",", ".")
    return float(value)


def read_metrics(path):
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as csv_file:
        sample = csv_file.readline()
        csv_file.seek(0)
        delimiter = ";" if ";" in sample else ","
        return list(csv.DictReader(csv_file, delimiter=delimiter))


METRIC_LEGACY_ALIASES = {"precisao": "precision", "revocacao": "recall"}


def summarize_metrics(rows):
    if not rows:
        return {}
    summary = {"images": len(rows)}
    for metric in ["dice", "iou", "precisao", "revocacao"]:
        legacy_key = METRIC_LEGACY_ALIASES.get(metric)
        values = [parse_decimal(row[metric] if metric in row else row[legacy_key]) for row in rows]
        summary[metric] = sum(values) / len(values)
    return summary
