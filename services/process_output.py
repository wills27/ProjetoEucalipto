from pathlib import Path
import re


ERROR_MARKERS = [
    "Traceback",
    "Error:",
    "Exception",
    "RuntimeError",
    "FileNotFoundError",
    "CUDA out of memory",
]


def parse_progress_line(line):
    match = re.match(r"^PROGRESS\s+(\d+)\s+(\d+)\s*(.*)$", line.strip())
    if not match:
        return None
    return {
        "current": int(match.group(1)),
        "total": int(match.group(2)),
        "detail": match.group(3).strip(),
    }


def process_error_summary(text, max_lines=8):
    if not any(marker in text for marker in ERROR_MARKERS):
        return ""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    tail_lines = lines[-max_lines:]
    diagnostic_lines = [
        line
        for line in lines
        if (line.startswith("Warning:") or line.startswith("Plano:")) and line not in tail_lines
    ]
    return "\n".join(diagnostic_lines + tail_lines)


def stem_from_result_path(text, suffix):
    stem = Path(text).stem
    return stem[: -len(suffix)] if stem.endswith(suffix) else stem


def result_status_stem_from_line(line):
    line = line.strip()
    if not line:
        return None
    if "Overlay salvo:" in line:
        return stem_from_result_path(line.split("Overlay salvo:", 1)[1].strip(), "_overlay_pred")
    if "Predicao salva:" in line:
        return stem_from_result_path(line.split("Predicao salva:", 1)[1].strip(), "_pred_masks")

    progress_match = re.match(r"^PROGRESS\s+\d+\s+\d+\s+Resultados:\s+(.+)$", line)
    if progress_match:
        return Path(progress_match.group(1).strip()).stem

    metrics_match = re.match(r"^METRICS\s+(.+)$", line)
    if metrics_match:
        return metrics_match.group(1).strip()

    measurements_match = re.match(r"^MEASUREMENTS\s+(.+)$", line)
    if measurements_match:
        return measurements_match.group(1).strip()
    return None
