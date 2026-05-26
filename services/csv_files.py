import csv


def load_semicolon_csv(path):
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.reader(file, delimiter=";"))


def remove_rows_from_csv(path, column_name, image_stem):
    if not path.exists():
        return 0

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        sample = file.read(2048)
        file.seek(0)
        first_line = sample.splitlines()[0] if sample.splitlines() else ""
        delimiter = ";" if ";" in first_line else ","
        rows = list(csv.reader(file, delimiter=delimiter))

    if not rows or column_name not in rows[0]:
        return 0

    column_index = rows[0].index(column_name)
    kept_rows = [rows[0]]
    removed = 0
    for row in rows[1:]:
        if len(row) > column_index and row[column_index] == image_stem:
            removed += 1
        else:
            kept_rows.append(row)

    if removed == 0:
        return 0

    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file, delimiter=delimiter)
        writer.writerows(kept_rows)
    return 1
