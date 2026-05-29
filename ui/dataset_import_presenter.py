from pathlib import Path

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QLineEdit,
    QVBoxLayout,
)

from services.config import save_config
from services.dataset_import import (
    convert_dataset_images_to_tif as convert_dataset_folder_to_tif,
    import_dataset_folder_contents,
    convert_seg_npy_masks_in_dir,
)
from services.paths import PROJECT_DIR, dataset_images_dir, dataset_masks_dir


class DatasetImportPresenterMixin:
    def import_dataset_folder(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Importar imagens e mascaras")
        dialog.setModal(True)
        dialog.setMinimumWidth(360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        recursive_check = QCheckBox("Incluir subpastas")
        recursive_check.setChecked(bool(self.config.get("import_dataset_recursive", True)))

        skip_keyword = QLineEdit(str(self.config.get("import_dataset_skip_keyword", "")))
        skip_keyword.setPlaceholderText("mask, overlay, temp")

        grayscale_check = QCheckBox("Converter imagens para cinza")
        grayscale_check.setChecked(bool(self.config.get("import_dataset_grayscale", False)))

        form.addRow("Ignorar contendo", skip_keyword)
        form.addRow("", recursive_check)
        form.addRow("", grayscale_check)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens e _seg.npy", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = dataset_images_dir(self.config)
        mask_target_dir = dataset_masks_dir(self.config)
        result = import_dataset_folder_contents(
            source_dir,
            target_dir,
            mask_target_dir,
            convert_to_grayscale=grayscale_check.isChecked(),
            recursive=recursive_check.isChecked(),
            keyword=skip_keyword.text().strip().lower(),
        )
        self.config["import_dataset_recursive"] = recursive_check.isChecked()
        self.config["import_dataset_skip_keyword"] = skip_keyword.text().strip().lower()
        self.config["import_dataset_grayscale"] = grayscale_check.isChecked()
        save_config(self.config)

        self.append_log(
            f"\n>>> Importar imagens e _seg.npy\n"
            f"Origem: {source_dir}\n"
            f"Destino imagens: {target_dir}\n"
            f"Destino mascaras: {mask_target_dir}\n"
            f"Copiados: {result['copied']}\n"
            f"Convertidos para TIFF: {result['converted']}\n"
            f"Mascaras convertidas de _seg.npy: {result.get('masks_converted', 0)}\n"
            f"Recursiva: {'sim' if recursive_check.isChecked() else 'nao'}\n"
            f"Filtro: {skip_keyword.text().strip().lower() or '-'}\n"
            f"Cinza: {'sim' if grayscale_check.isChecked() else 'nao'}\n"
            f"Pulados por ja existirem: {result['skipped']}\n"
        )
        if result["errors"]:
            self.show_error(
                "Erro ao importar dataset",
                f"{len(result['errors'])} imagem(ns) nao puderam ser convertidas.",
                "\n".join(result["errors"]),
            )
        self.convert_dataset_images_to_tif(target_dir)
        self.refresh_dataset_import()
        self.refresh_project()

    def convert_dataset_images_to_tif(self, folder=None):
        input_dir = Path(folder) if folder else dataset_images_dir(self.config)
        result = convert_dataset_folder_to_tif(input_dir)

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
