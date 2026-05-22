import json
import random


def load_plan(path):
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as plan_file:
            data = json.load(plan_file)
    except (json.JSONDecodeError, OSError):
        return {}
    return {entry["image"]: entry for entry in data.get("images", [])}


def save_plan(path, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as plan_file:
        json.dump({"images": entries}, plan_file, indent=2)


def summarize_table_entries(entries):
    total = len(entries)
    selected = 0
    valid = 0
    problems = 0
    groups = {"train": 0, "val": 0, "test": 0, "auto": 0}

    for entry in entries:
        if entry.get("status") == "OK":
            valid += 1
        else:
            problems += 1
        if entry.get("include"):
            selected += 1
            group = entry.get("group", "auto")
            groups[group] = groups.get(group, 0) + 1

    return {
        "total": total,
        "selected": selected,
        "valid": valid,
        "problems": problems,
        "groups": groups,
    }


def auto_split_indices(entries, seed=42, train_ratio=0.7, val_ratio=0.15):
    rows = [
        index
        for index, entry in enumerate(entries)
        if entry.get("status") == "OK" and entry.get("include")
    ]
    random.seed(seed)
    random.shuffle(rows)

    total = len(rows)
    n_train = int(total * train_ratio)
    n_val = int(total * val_ratio)

    assignments = {}
    for row in rows[:n_train]:
        assignments[row] = "train"
    for row in rows[n_train:n_train + n_val]:
        assignments[row] = "val"
    for row in rows[n_train + n_val:]:
        assignments[row] = "test"
    for index, entry in enumerate(entries):
        if entry.get("status") == "Sem mascara" and entry.get("include"):
            assignments[index] = "test"
    return assignments
