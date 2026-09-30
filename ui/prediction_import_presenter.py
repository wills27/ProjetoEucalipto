from pathlib import Path

from PyQt6.QtCore import QThread, Qt
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMessageBox,
)

from services.config import save_config, with_derived_paths
from services.paths import (
    PENDING_IMAGE_SET,
    PROJECT_DIR,
    active_image_set_dir,
    is_default_image_set,
    project_models_dir,
    relative_to_project,
    shared_models_dir,
)
from services.prediction_import import (
    available_import_destination,
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
            str(shared_models_dir(self.config)),
            "Arquivos de modelo (*.*)",
        )
        if not files:
            return

        target_dir = shared_models_dir(self.config)
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
        files, _filter = QFileDialog.getOpenFileNames(
            self,
            "Escolher imagens",
            str(PROJECT_DIR),
            "Imagens (*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.webp *.gif);;Todos os arquivos (*.*)",
        )
        if not files:
            return
        self.import_prediction_images_from_paths(
            [Path(file_name) for file_name in files],
            "Arquivos selecionados",
        )

    def use_pending_image_set_if_none_active(self):
        """Sem um conjunto de imagens criado ainda, as importacoes vao para uma
        pasta temporaria (fora do projeto) ate a pessoa criar um conjunto para
        elas. Evita duplicar imagens na pasta padrao do dataset de treino."""
        if not is_default_image_set(self.config):
            return
        self.config["active_image_set"] = PENDING_IMAGE_SET
        self.config = with_derived_paths(self.config)
        save_config(self.config)
        self.refresh_image_set_selector()

    def import_prediction_images_from_paths(self, paths, source_label):
        self.use_pending_image_set_if_none_active()
        target_dir = active_image_set_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)
        convert_to_grayscale = True

        copied = 0
        converted = 0
        errors = []
        image_candidates, skipped = collect_prediction_image_candidates(paths)

        total = len(image_candidates)
        self.start_task_progress("Importar imagens", total, "Importando imagens para resultados...")
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            used_destinations = set()
            for index, src in enumerate(sorted(image_candidates, key=lambda path: str(path).lower()), start=1):
                self.update_task_progress(index - 1, total, f"Importando {src.name}")
                output_stem = prediction_import_output_stem(src)
                dst = available_import_destination(target_dir, output_stem, used_destinations)
                used_destinations.add(dst.name.lower())

                try:
                    action = import_prediction_image(src, dst, convert_to_grayscale)
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
        save_config(self.config)

        self.append_log(
            f"\n>>> Importar imagens para resultados\n"
            f"Origem: {source_label}\n"
            f"Destino: {target_dir}\n"
            f"Encontradas: {len(paths)}\n"
            f"Copiados: {copied}\n"
            f"Convertidos para TIFF: {converted}\n"
            f"Cinza: sim\n"
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
