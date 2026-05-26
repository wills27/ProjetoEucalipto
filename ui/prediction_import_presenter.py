from pathlib import Path

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QRadioButton,
    QVBoxLayout,
)

from services.config import save_config, with_derived_paths
from services.dataset_manifest import update_plan_entry_group
from services.paths import (
    PROJECT_DIR,
    dataset_images_dir,
    project_models_dir,
    relative_to_project,
)
from services.prediction_import import (
    available_import_destination,
    collect_image_paths_from_folder,
    collect_prediction_image_candidates,
    import_prediction_image,
    prediction_import_output_stem,
)
from workers.file_copy_worker import FileCopyWorker


class PredictionImportPresenterMixin:
    def import_prediction_model(self):
        if self.model_import_thread is not None:
            QMessageBox.information(self, "Importar modelo", "A importacao de modelo ainda esta em andamento.")
            return

        files, _filter = QFileDialog.getOpenFileNames(
            self,
            "Escolher modelos para importar",
            str(project_models_dir(self.config)),
            "Arquivos de modelo (*.*)",
        )
        if not files:
            return

        target_dir = project_models_dir(self.config)
        self.append_log(
            f"\n>>> Importar modelos\n"
            f"Destino: {target_dir}\n"
            f"Arquivos selecionados: {len(files)}\n"
        )
        self.start_task_progress("Importar modelo", detail="Importando modelo...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)

        self.model_import_thread = QThread(self)
        self.model_import_worker = FileCopyWorker(files, target_dir)
        self.model_import_worker.moveToThread(self.model_import_thread)
        self.model_import_thread.started.connect(self.model_import_worker.run)
        self.model_import_worker.progress.connect(
            lambda current, total, name: self.update_task_progress(
                current,
                total,
                f"Importando modelo: {name}",
            )
        )
        self.model_import_worker.finished.connect(self.finish_model_import)
        self.model_import_worker.finished.connect(self.model_import_thread.quit)
        self.model_import_worker.finished.connect(self.model_import_worker.deleteLater)
        self.model_import_thread.finished.connect(self.model_import_thread.deleteLater)
        self.model_import_thread.start()

    def finish_model_import(self, copied, skipped, last_model_name, errors):
        if last_model_name:
            self.config["active_model"] = last_model_name
            self.config = with_derived_paths(self.config)
            save_config(self.config)

        self.append_log(
            f"Copiados: {copied}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        QApplication.restoreOverrideCursor()
        self.finish_task_progress("Importacao de modelo finalizada.", success=not errors)
        self.model_import_thread = None
        self.model_import_worker = None
        self.refresh_project()
        self.refresh_prediction()

        if errors:
            self.append_log("Erros:\n" + "\n".join(errors) + "\n")
            QMessageBox.warning(
                self,
                "Importar modelo",
                "Alguns modelos nao puderam ser importados:\n\n" + "\n".join(errors[:8]),
            )

    def open_prediction_image_import_dialog(self):
        options = self.prediction_image_import_options()
        if not options:
            return

        if options["mode"] == "files":
            self.import_prediction_image_files(options)
        else:
            self.import_prediction_image_folder(options)

    def prediction_image_import_options(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Importar imagens")
        dialog.setModal(True)
        dialog.setMinimumWidth(360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(14)

        mode_group = QButtonGroup(dialog)
        files_radio = QRadioButton("Imagens selecionadas")
        folder_radio = QRadioButton("Pasta")
        files_radio.setObjectName("choice")
        folder_radio.setObjectName("choice")
        mode_group.addButton(files_radio)
        mode_group.addButton(folder_radio)
        files_radio.setChecked(True)

        content_box = QFrame()
        content_box.setObjectName("dialogSection")
        content_layout = QVBoxLayout(content_box)
        content_layout.setContentsMargins(12, 10, 12, 12)
        content_layout.setSpacing(10)

        origin_choices = QHBoxLayout()
        origin_choices.setSpacing(18)
        origin_choices.addWidget(files_radio)
        origin_choices.addWidget(folder_radio)
        origin_choices.addStretch()
        content_layout.addLayout(origin_choices)

        recursive_check = QCheckBox("Incluir subpastas")
        recursive_check.setChecked(bool(self.config.get("import_results_recursive", True)))

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(10)

        grayscale_check = QCheckBox("Converter para cinza")
        grayscale_check.setChecked(bool(self.config.get("import_results_grayscale", False)))
        skip_keyword = QLineEdit(str(self.config.get("import_results_skip_keyword", "")))
        skip_keyword.setPlaceholderText("mask, overlay, temp")

        form.addRow("Ignorar contendo", skip_keyword)
        form.addRow("", grayscale_check)
        content_layout.addWidget(recursive_check)
        content_layout.addLayout(form)
        layout.addWidget(content_box)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        def update_folder_options():
            folder_mode = folder_radio.isChecked()
            recursive_check.setEnabled(folder_mode)
            skip_keyword.setEnabled(folder_mode)
            files_radio.setProperty("selected", files_radio.isChecked())
            folder_radio.setProperty("selected", folder_radio.isChecked())
            files_radio.style().unpolish(files_radio)
            files_radio.style().polish(files_radio)
            folder_radio.style().unpolish(folder_radio)
            folder_radio.style().polish(folder_radio)

        files_radio.toggled.connect(update_folder_options)
        folder_radio.toggled.connect(update_folder_options)
        update_folder_options()

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        return {
            "mode": "folder" if folder_radio.isChecked() else "files",
            "recursive": recursive_check.isChecked(),
            "keyword": skip_keyword.text().strip().lower(),
            "convert_to_grayscale": grayscale_check.isChecked(),
        }

    def import_prediction_image_files(self, options=None):
        options = options or self.default_prediction_import_options(mode="files")
        files, _filter = QFileDialog.getOpenFileNames(
            self,
            "Escolher imagens para resultados",
            str(PROJECT_DIR),
            "Imagens (*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.webp *.gif);;Todos os arquivos (*.*)",
        )
        if not files:
            return
        self.import_prediction_images_from_paths(
            [Path(file_name) for file_name in files],
            "Arquivos selecionados",
            keyword=options["keyword"],
            convert_to_grayscale=options["convert_to_grayscale"],
            recursive=options["recursive"],
        )

    def import_prediction_image_folder(self, options=None):
        options = options or self.default_prediction_import_options(mode="folder")
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        image_paths = collect_image_paths_from_folder(
            source_dir,
            options["keyword"],
            recursive=options["recursive"],
        )
        self.import_prediction_images_from_paths(
            image_paths,
            str(source_dir),
            source_root=source_dir,
            keyword=options["keyword"],
            convert_to_grayscale=options["convert_to_grayscale"],
            recursive=options["recursive"],
        )

    def default_prediction_import_options(self, mode="files"):
        return {
            "mode": mode,
            "recursive": bool(self.config.get("import_results_recursive", True)),
            "keyword": str(self.config.get("import_results_skip_keyword", "")).strip().lower(),
            "convert_to_grayscale": bool(self.config.get("import_results_grayscale", False)),
        }

    def prediction_import_skip_keyword(self):
        if not hasattr(self, "result_import_skip_keyword"):
            return ""
        return self.result_import_skip_keyword.text().strip().lower()

    def prediction_import_grayscale_enabled(self):
        return bool(
            hasattr(self, "result_import_grayscale")
            and self.result_import_grayscale.isChecked()
        )

    def import_prediction_images_from_paths(
        self,
        paths,
        source_label,
        source_root=None,
        keyword="",
        convert_to_grayscale=None,
        recursive=True,
    ):
        target_dir = dataset_images_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)
        keyword = str(keyword or "").strip().lower()
        if convert_to_grayscale is None:
            convert_to_grayscale = self.prediction_import_grayscale_enabled()
        source_root = Path(source_root) if source_root else None

        copied = 0
        converted = 0
        errors = []
        image_candidates, skipped = collect_prediction_image_candidates(paths, keyword)

        total = len(image_candidates)
        self.start_task_progress("Importar imagens", total, "Importando imagens para resultados...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            used_destinations = set()
            for index, src in enumerate(sorted(image_candidates, key=lambda path: str(path).lower()), start=1):
                self.update_task_progress(index - 1, total, f"Importando {src.name}")
                output_stem = prediction_import_output_stem(src, source_root)
                dst = available_import_destination(target_dir, output_stem, used_destinations)
                used_destinations.add(dst.name.lower())

                try:
                    action = import_prediction_image(src, dst, convert_to_grayscale)
                    update_plan_entry_group(self.config, dst.stem, "test", include=True, status="Sem mascara")
                    if action == "copied":
                        copied += 1
                    else:
                        converted += 1
                except Exception as exc:
                    skipped += 1
                    errors.append(f"{src}: {exc}")
                QApplication.processEvents()
        finally:
            QApplication.restoreOverrideCursor()

        self.config = with_derived_paths(self.config)
        self.config["import_results_recursive"] = bool(recursive)
        self.config["import_results_skip_keyword"] = keyword
        self.config["import_results_grayscale"] = convert_to_grayscale
        save_config(self.config)

        self.append_log(
            f"\n>>> Importar imagens para resultados\n"
            f"Origem: {source_label}\n"
            f"Destino: {target_dir}\n"
            f"Encontradas: {len(paths)}\n"
            f"Copiados: {copied}\n"
            f"Convertidos para TIFF: {converted}\n"
            f"Cinza: {'sim' if convert_to_grayscale else 'nao'}\n"
            f"Recursiva: {'sim' if recursive else 'nao'}\n"
            f"Filtro: {keyword or '-'}\n"
            f"Pulados/ignorados: {skipped}\n"
        )
        self.finish_task_progress("Importacao de imagens finalizada.", success=not errors)
        if errors:
            self.show_error(
                "Erro ao importar imagens",
                f"{len(errors)} imagem(ns) nao puderam ser importadas.",
                "\n".join(errors),
            )
        self.clear_result_indexes()
        self.refresh_analysis_images()
