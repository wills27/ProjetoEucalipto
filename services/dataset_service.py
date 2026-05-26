from pathlib import Path

from services.dataset_plan import load_plan, save_plan, summarize_table_entries


def dataset_plan_entry(image, include, group, status):
    return {
        "image": image,
        "include": include,
        "group": group or "uncategorized",
        "status": status,
    }


def dataset_row_matches_filters(row_number, row_data, group_text, group_value, selected, filters):
    text = filters.get("text", "")
    status_filter = filters.get("status", "")
    group_filter = filters.get("group", "")
    include_filter = filters.get("include", "")
    haystack = " ".join(
        [
            str(row_number),
            row_data.get("image", ""),
            row_data.get("validation_status", ""),
            group_text,
            group_value,
        ]
    ).lower()
    if text and text not in haystack:
        return False
    if status_filter and row_data.get("status") != status_filter:
        return False
    if group_filter and group_value != group_filter:
        return False
    if include_filter == "selected" and not selected:
        return False
    if include_filter == "unselected" and selected:
        return False
    return True


def dataset_selection_summary_text(entries, visible_count):
    summary = summarize_table_entries(entries)
    groups = summary["groups"]
    return (
        f"Imagens: {summary['total']}\n"
        f"Visiveis: {visible_count}\n"
        f"Pares validos: {summary['valid']}\n"
        f"Selecionadas: {summary['selected']}\n"
        f"Sem cat./Treino/Val/Teste/Auto: "
        f"{groups['uncategorized']}/{groups['train']}/{groups['val']}/{groups['test']}/{groups['auto']}\n"
        f"Sem mascara: {summary['problems']}"
    )


def dataset_pair_removal_targets(row_data):
    if not row_data:
        return []

    image_path = Path(row_data["image_path"])
    targets = {
        image_path,
        Path(row_data["seg_path"]),
        Path(row_data["tif_mask_path"]),
        image_path.with_name(f"{image_path.stem}_masks.tif"),
        image_path.with_name(f"{image_path.stem}_masks.tiff"),
    }
    return sorted(targets, key=lambda path: path.name.lower())


def remove_dataset_plan_entries(plan_path, image_names):
    plan = load_plan(plan_path)
    filtered_entries = [entry for image, entry in plan.items() if image not in image_names]
    if len(filtered_entries) == len(plan):
        return 0
    save_plan(plan_path, filtered_entries)
    return len(plan) - len(filtered_entries)
