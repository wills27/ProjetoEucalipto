from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QMessageBox

from services.config import save_config, with_derived_paths
from services.dataset_import import (
    convert_dataset_images_to_tif as convert_folder_to_tif,
    import_dataset_folder_contents,
)
from services.image_set_service import (
    get_source_project,
    is_test_image_set,
    write_image_set_metadata,
)
from services.paths import (
    DEFAULT_IMAGE_SET,
    PROJECT_DIR,
    active_image_set_dir,
    active_image_set_name,
    delete_image_set as delete_image_set_folder,
    ensure_image_set_structure,
    list_image_sets,
)


class ImageSetPresenterMixin:
    def _custom_image_sets(self):
        """Lista conjuntos excluindo DEFAULT_IMAGE_SET."""
        return [n for n in list_image_sets(self.config) if n != DEFAULT_IMAGE_SET]

    def refresh_image_set_selector(self):
        if not hasattr(self, "image_set_combo"):
            return
        self.image_set_combo.blockSignals(True)
        self.image_set_combo.clear()
        for name in self._custom_image_sets():
            self.image_set_combo.addItem(name, name)
        active = active_image_set_name(self.config)
        index = self.image_set_combo.findData(active)
        if index >= 0:
            self.image_set_combo.setCurrentIndex(index)
        elif self.image_set_combo.count() > 0:
            self.image_set_combo.setCurrentIndex(0)
            # Migra config para o primeiro conjunto disponivel
            first = self.image_set_combo.currentData()
            if first and first != active:
                self.config["active_image_set"] = first
                self.config = with_derived_paths(self.config)
                save_config(self.config)
        self.image_set_combo.blockSignals(False)
        self.refresh_image_set_badge()

    def refresh_image_set_badge(self):
        if not hasattr(self, "image_set_badge"):
            return
        name = active_image_set_name(self.config)
        if name == DEFAULT_IMAGE_SET or not is_test_image_set(self.config, name):
            self.image_set_badge.hide()
            return
        source = get_source_project(self.config, name)
        text = f"Teste · {source}" if source else "Teste"
        self.image_set_badge.setText(text)
        self.image_set_badge.show()

    def on_image_set_selector_changed(self, _index=None):
        if not hasattr(self, "image_set_combo"):
            return
        name = self.image_set_combo.currentData()
        self.select_image_set(name)

    def select_image_set(self, name):
        if not name or name == DEFAULT_IMAGE_SET or name == active_image_set_name(self.config):
            return
        self.reset_project_dependent_state()
        self.config["active_image_set"] = name
        self.config = with_derived_paths(self.config)
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()

    def create_image_set(self):
        name, ok = QInputDialog.getText(self, "Novo conjunto de imagens", "Nome do conjunto:")
        if not ok:
            return
        name = name.strip().replace(" ", "_")
        if not name or name == DEFAULT_IMAGE_SET:
            QMessageBox.information(self, "Novo conjunto de imagens", "Nome invalido.")
            return
        if name in list_image_sets(self.config):
            QMessageBox.information(self, "Novo conjunto de imagens", "Ja existe um conjunto com esse nome.")
            return

        ensure_image_set_structure(self.config, name)
        write_image_set_metadata(self.config, name, {"type": "normal"})
        self.reset_project_dependent_state()
        self.config["active_image_set"] = name
        self.config = with_derived_paths(self.config)
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()

        reply = QMessageBox.question(
            self,
            "Novo conjunto de imagens",
            "Importar imagens de uma pasta para este conjunto agora?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.import_images_into_active_image_set()

    def import_images_into_active_image_set(self):
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = active_image_set_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        self.start_task_progress("Importar imagens", detail="Importando imagens...")
        result = import_dataset_folder_contents(
            source_dir,
            target_dir,
            progress_callback=self.update_task_progress,
        )
        self.start_task_progress("Converter imagens", detail="Convertendo imagens para TIFF...")
        convert_result = convert_folder_to_tif(target_dir, progress_callback=self.update_task_progress)

        name = active_image_set_name(self.config)
        self.append_log(
            f"\n>>> Importar imagens para conjunto '{name}'\n"
            f"Origem: {source_dir}\n"
            f"Destino: {target_dir}\n"
            f"Copiadas: {result['copied']}\n"
            f"Convertidas para TIFF: {result['converted']}\n"
            f"Puladas por ja existirem: {result['skipped']}\n"
        )
        all_errors = result["errors"] + convert_result["errors"]
        self.finish_task_progress("Importacao de imagens finalizada.", success=not all_errors)
        if all_errors:
            self.show_error(
                "Erro ao importar imagens",
                f"{len(all_errors)} arquivo(s) nao puderam ser processados.",
                "\n".join(all_errors),
            )
        self.clear_analysis_caches()
        self.refresh_analysis_images()

    def delete_active_image_set(self):
        name = active_image_set_name(self.config)
        if name == DEFAULT_IMAGE_SET:
            QMessageBox.information(
                self,
                "Remover conjunto de imagens",
                "O conjunto padrao nao pode ser removido.",
            )
            return

        reply = QMessageBox.question(
            self,
            "Remover conjunto de imagens",
            (
                f"Apagar definitivamente o conjunto '{name}' do disco?\n\n"
                "Imagens, predicoes, overlays e metricas deste conjunto serao removidas. "
                "Nao pode ser desfeito."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            delete_image_set_folder(self.config, name)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Remover conjunto de imagens", f"Nao foi possivel remover o conjunto:\n{error}")
            return

        self.reset_project_dependent_state()
        remaining = [n for n in self._custom_image_sets() if n != name]
        self.config["active_image_set"] = remaining[0] if remaining else DEFAULT_IMAGE_SET
        self.config = with_derived_paths(self.config)
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()
        QMessageBox.information(self, "Remover conjunto de imagens", f"Conjunto '{name}' removido.")
