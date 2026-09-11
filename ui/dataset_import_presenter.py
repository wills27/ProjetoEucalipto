from pathlib import Path

from PyQt6.QtWidgets import QFileDialog

from services.config import save_config
from services.dataset_import import (
    convert_dataset_images_to_tif as convert_dataset_folder_to_tif,
    import_dataset_folder_contents,
    convert_seg_npy_masks_in_dir,
)
from services.paths import PROJECT_DIR, dataset_images_dir, dataset_masks_dir
from ui.dialogs.import_images_dialog import ImportImagesDialog


class DatasetImportPresenterMixin:
    def import_dataset_folder(self):
        dialog = ImportImagesDialog(
            self,
            allow_files=False,
            show_prefix=True,
            defaults={
                "recursive": self.config.get("import_dataset_recursive", True),
                "skip_keyword": self.config.get("import_dataset_skip_keyword", ""),
                "prefix": self.config.get("import_dataset_prefix_folders", False),
                "grayscale": self.config.get("import_dataset_grayscale", False),
            },
        )
        dialog.setWindowTitle("Importar imagens e mascaras")
        if dialog.exec() != ImportImagesDialog.DialogCode.Accepted:
            return

        opts = dialog.result_options()
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens e _seg.npy", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = dataset_images_dir(self.config)
        mask_target_dir = dataset_masks_dir(self.config)

        self.start_task_progress("Importar dataset", detail="Importando imagens e mascaras...")
        result = import_dataset_folder_contents(
            source_dir,
            target_dir,
            mask_target_dir,
            convert_to_grayscale=opts["grayscale"],
            recursive=opts["recursive"],
            keyword=opts["keyword"],
            use_folder_prefix=opts["prefix"],
            progress_callback=self.update_task_progress,
        )
        self.config["import_dataset_recursive"] = opts["recursive"]
        self.config["import_dataset_skip_keyword"] = opts["keyword"]
        self.config["import_dataset_prefix_folders"] = opts["prefix"]
        self.config["import_dataset_grayscale"] = opts["grayscale"]
        save_config(self.config)

        self.start_task_progress("Converter imagens", detail="Convertendo imagens para TIFF...")
        convert_result = convert_dataset_folder_to_tif(
            target_dir,
            progress_callback=self.update_task_progress,
        )
        masks_dir = dataset_masks_dir(self.config)
        masks_result = convert_seg_npy_masks_in_dir(masks_dir)

        self.append_log(
            f"\n>>> Importar imagens e _seg.npy\n"
            f"Origem: {source_dir}\n"
            f"Destino imagens: {target_dir}\n"
            f"Destino mascaras: {mask_target_dir}\n"
            f"Copiados: {result['copied']}\n"
            f"Convertidos para TIFF: {result['converted']}\n"
            f"Mascaras convertidas de _seg.npy: {result.get('masks_converted', 0)}\n"
            f"Recursiva: {'sim' if opts['recursive'] else 'nao'}\n"
            f"Filtro: {opts['keyword'] or '-'}\n"
            f"Prefixo de pastas: {'sim' if opts['prefix'] else 'nao'}\n"
            f"Cinza: {'sim' if opts['grayscale'] else 'nao'}\n"
            f"Pulados por ja existirem: {result['skipped']}\n"
        )
        self.finish_task_progress(
            "Importacao de dataset finalizada.",
            success=not (result["errors"] or convert_result["errors"] or masks_result["errors"]),
        )
        all_errors = result["errors"] + convert_result["errors"] + masks_result["errors"]
        if all_errors:
            self.show_error(
                "Erro ao importar dataset",
                f"{len(all_errors)} arquivo(s) nao puderam ser processados.",
                "\n".join(all_errors),
            )
        self.refresh_dataset_import()
        self.refresh_project()

    def convert_dataset_images_to_tif(self, folder=None, progress_callback=None):
        input_dir = Path(folder) if folder else dataset_images_dir(self.config)
        result = convert_dataset_folder_to_tif(input_dir, progress_callback=progress_callback)

        # Also ensure any existing _seg.npy in masks dir are converted to TIFF
        masks_dir = dataset_masks_dir(self.config)
        masks_result = convert_seg_npy_masks_in_dir(masks_dir)

        self.append_log(
            f"\n>>> Converter para TIFF\n"
            f"Pasta: {input_dir}\n"
            f"Convertidos: {result['converted']}\n"
            f"Ja eram TIFF: {result['skipped']}\n"
            f"Falhas: {result['failed']}\n"
            f"Mascara _seg.npy convertidas: {masks_result.get('converted', 0)}\n"
        )
        if result["errors"]:
            self.show_error(
                "Erro ao converter para TIFF",
                f"{len(result['errors'])} arquivo(s) nao puderam ser convertidos.",
                "\n".join(result["errors"]),
            )
