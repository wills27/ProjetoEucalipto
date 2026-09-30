import shutil

from PyQt6.QtWidgets import QInputDialog, QMessageBox

from services.config import save_config, with_derived_paths
from services.image_set_service import (
    get_source_project,
    is_test_image_set,
    write_image_set_metadata,
)
from services.paths import (
    DEFAULT_IMAGE_SET,
    PENDING_IMAGE_SET,
    active_image_set_dir,
    active_image_set_name,
    clear_pending_import_dir,
    clear_pending_outputs,
    delete_image_set as delete_image_set_folder,
    ensure_image_set_structure,
    is_pending_image_set,
    list_image_sets,
    move_image_set_outputs,
    pending_import_dir,
)
from services.prediction_import import available_import_destination


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
        elif active == PENDING_IMAGE_SET:
            self.image_set_combo.setCurrentIndex(-1)
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
        if name == PENDING_IMAGE_SET:
            # Desativado por enquanto a pedido do usuario.
            self.image_set_badge.hide()
            return
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
        had_pending = is_pending_image_set(self.config)
        self.reset_project_dependent_state()
        self.config["active_image_set"] = name
        self.config = with_derived_paths(self.config)
        moved = self.move_pending_images_into_active_set() if had_pending else 0
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()

        if moved:
            QMessageBox.information(
                self,
                "Selecionar conjunto de imagens",
                f"{moved} imagem(ns) ja importada(s) foram movidas para o conjunto '{name}'.",
            )

    def discard_pending_image_set_if_active(self):
        """Descarta a importacao pendente (imagens temporarias e quaisquer
        predicoes/overlays ja gerados para elas) quando o app sai do modo
        'sem conjunto ainda' por um caminho que nao seja nomea-lo (trocar de
        projeto, deletar o projeto, trocar a pasta de projetos etc.). Sem
        isso, a pasta temporaria e as saidas geradas ficam orfas no disco."""
        if not is_pending_image_set(self.config):
            return False
        clear_pending_import_dir(self.config)
        clear_pending_outputs(self.config)
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(
                "Importacao pendente (ainda sem conjunto) foi descartada.", 5000
            )
        return True

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

        had_pending = is_pending_image_set(self.config)
        ensure_image_set_structure(self.config, name)
        write_image_set_metadata(self.config, name, {"type": "normal"})
        self.reset_project_dependent_state()
        self.config["active_image_set"] = name
        self.config = with_derived_paths(self.config)
        moved = self.move_pending_images_into_active_set() if had_pending else 0
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()

        if moved:
            QMessageBox.information(
                self,
                "Novo conjunto de imagens",
                f"{moved} imagem(ns) ja importada(s) foram movidas para o conjunto '{name}'.",
            )
            return

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
        """Usa o dialogo de importacao unificado (mesmo fluxo da pagina de resultados)."""
        self.open_prediction_image_import_dialog()

    def move_pending_images_into_active_set(self):
        """Mao dupla da importacao 'sem conjunto': move (sem duplicar) as imagens
        que ficaram na pasta temporaria para o conjunto recem-criado/selecionado."""
        pending_dir = pending_import_dir(self.config)
        if not pending_dir.exists():
            return 0
        target_dir = active_image_set_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)
        moved = 0
        used_destinations = set()
        for src in sorted(pending_dir.iterdir()):
            if not src.is_file():
                continue
            dst = available_import_destination(target_dir, src.stem, used_destinations)
            used_destinations.add(dst.name.lower())
            shutil.move(str(src), str(dst))
            moved += 1
        clear_pending_import_dir(self.config)
        move_image_set_outputs(self.config, PENDING_IMAGE_SET, active_image_set_name(self.config))
        return moved

    def delete_active_image_set(self):
        name = active_image_set_name(self.config)
        if name == PENDING_IMAGE_SET:
            QMessageBox.information(
                self,
                "Remover conjunto de imagens",
                "Ainda nao ha um conjunto criado; as imagens importadas sao temporarias.",
            )
            return
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
