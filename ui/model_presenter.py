import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QHeaderView, QMessageBox, QTableWidgetItem

from services.config import save_config, with_derived_paths
from services.metrics import format_size
from services.model_service import (
    delete_model,
    delete_shared_model,
    first_model_name,
    list_available_model_names,
    list_model_names,
    list_model_paths,
    promote_model_to_shared,
)
from services.paths import (
    active_image_set_dir,
    active_image_set_name,
    active_model_path,
    metrics_csv_path,
    project_models_dir,
    relative_to_project,
    shared_models_dir,
)


class ModelPresenterMixin:
    def ensure_active_model(self):
        if self.config.get("active_model") and active_model_path(self.config).exists():
            return True
        QMessageBox.information(
            self,
            "Modelo nao selecionado",
            "Este projeto ainda nao tem um modelo ativo. Treine um modelo ou selecione um modelo existente antes de continuar.",
        )
        return False

    def refresh_project_models_table(self):
        if not hasattr(self, "project_models_table"):
            return

        models = list_model_paths(self.config)
        shared_dir = shared_models_dir(self.config)
        active_name = self.config.get("active_model") or ""

        self.project_models_table.setRowCount(len(models))
        active_row = None
        for row, model_path in enumerate(models):
            is_active = model_path.name == active_name
            in_shared = (shared_dir / model_path.name).exists()
            values = [
                model_path.name,
                format_size(model_path.stat().st_size),
                time.strftime("%d/%m/%Y", time.localtime(model_path.stat().st_mtime)),
                "✓" if metrics_csv_path(self.config, model_path.name).exists() else "–",
                "✓" if in_shared else "–",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if is_active:
                    item.setBackground(QColor("#dff0d8"))
                if col in (3, 4):
                    item.setTextAlignment(0x84)  # AlignCenter
                self.project_models_table.setItem(row, col, item)
            if is_active:
                active_row = row
            self.project_models_table.setRowHeight(row, 36)

        if active_row is not None:
            self.project_models_table.selectRow(active_row)
        else:
            self.project_models_table.clearSelection()

    def refresh_prediction(self):
        self.config = with_derived_paths(self.config)
        self.predict_model_label.setText(self.config["active_model"] or "Nenhum modelo selecionado")
        self.pred_input.setText(relative_to_project(active_image_set_dir(self.config), self.config))
        self.pred_output.setText(self.config["predictions_dir"])
        self.pred_padding.setText(str(self.config["padding_pixels"]))
        self.pred_diameter.setText(str(self.config["diameter"]))
        if hasattr(self, "dataset_prediction_diameter"):
            self.dataset_prediction_diameter.setText(str(self.config["diameter"]))
        if hasattr(self, "dataset_prediction_padding"):
            self.dataset_prediction_padding.setText(str(self.config["padding_pixels"]))
        if hasattr(self, "dataset_prediction_cellprob"):
            self.dataset_prediction_cellprob.setText(str(self.config["cellprob_threshold"]))
        if hasattr(self, "dataset_prediction_flow"):
            self.dataset_prediction_flow.setText(str(self.config["flow_threshold"]))
        self.pred_cellprob.setText(str(self.config["cellprob_threshold"]))
        self.pred_flow.setText(str(self.config["flow_threshold"]))
        if not self.config.get("active_model") and hasattr(self, "train_model_name"):
            self.train_model_name.setText(f"cpsam_{self.config['active_project']}_v1")
        self.refresh_prediction_model_selector()
        if hasattr(self, "annotation_page"):
            self.annotation_page.sync_from_config(self.config)

    def refresh_prediction_model_selector(self):
        self.refresh_home_model_selector()

    def refresh_home_model_selector(self):
        if not hasattr(self, "home_model_combo"):
            return

        image_set = active_image_set_name(self.config)
        models = list_available_model_names(self.config, image_set)
        self.home_model_combo.blockSignals(True)
        self.home_model_combo.clear()
        self.home_model_combo.addItem("Selecione um modelo", "")
        for model_name in models:
            self.home_model_combo.addItem(model_name, model_name)

        active_model = self.config.get("active_model") or ""
        index = self.home_model_combo.findData(active_model)
        if index < 0 and active_model:
            # Modelo salvo no config nao existe mais — limpa
            self.config["active_model"] = ""
            save_config(self.config)
            index = 0
        self.home_model_combo.setCurrentIndex(index if index >= 0 else 0)
        self.home_model_combo.blockSignals(False)

    def on_home_model_changed(self, _index=None):
        if not hasattr(self, "home_model_combo"):
            return
        model_name = self.home_model_combo.currentData() or ""
        if not model_name or model_name == self.config.get("active_model"):
            return
        self.set_active_model(model_name)

    def set_active_model(self, model_name):
        if not model_name or model_name == self.config.get("active_model"):
            return
        previous_model = self.config.get("active_model") or ""
        self.config["active_model"] = model_name
        self.config = with_derived_paths(self.config)
        self.clear_analysis_caches()
        save_config(self.config)
        if hasattr(self, "preview_label"):
            self.preview_label.setText("Selecione uma imagem.")
            self.preview_label.setPixmap(QPixmap())
        self.append_log(
            f"\n>>> Modelo ativo alterado\n"
            f"Anterior: {previous_model or '-'}\n"
            f"Atual: {model_name}\n"
        )
        self.refresh_all()

    def remove_active_model(self):
        model_name = self.home_model_combo.currentData() if hasattr(self, "home_model_combo") else None
        model_name = model_name or self.config.get("active_model")
        if not model_name:
            QMessageBox.information(self, "Remover modelo", "Selecione um modelo para remover.")
            return

        reply = QMessageBox.question(
            self,
            "Remover modelo",
            (
                f"Apagar definitivamente o modelo '{model_name}' do disco?\n\n"
                "Predicoes, overlays e metricas associadas a este modelo tambem serao removidas. "
                "Nao pode ser desfeito."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            if (shared_models_dir(self.config) / model_name).exists():
                delete_shared_model(self.config, model_name)
            else:
                delete_model(self.config, model_name)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Remover modelo", f"Nao foi possivel remover o modelo:\n{error}")
            return

        if self.config.get("active_model") == model_name:
            image_set = active_image_set_name(self.config)
            self.config["active_model"] = first_model_name(self.config, image_set)
            self.config = with_derived_paths(self.config)
        save_config(self.config)
        self.refresh_all()
        QMessageBox.information(self, "Remover modelo", f"Modelo '{model_name}' removido.")

    def select_project_model(self):
        if not hasattr(self, "project_models_table"):
            return
        row = self.project_models_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Modelo", "Selecione um modelo na tabela.")
            return
        self.set_active_model(self.project_models_table.item(row, 0).text())

    def promote_active_model(self):
        model_name = self.config.get("active_model")
        if not model_name:
            QMessageBox.information(self, "Promover modelo", "Nenhum modelo ativo para promover.")
            return
        if (shared_models_dir(self.config) / model_name).exists():
            QMessageBox.information(self, "Promover modelo", f"Modelo '{model_name}' ja esta nos modelos compartilhados.")
            return
        if not (project_models_dir(self.config) / model_name).exists():
            QMessageBox.information(self, "Promover modelo", f"Modelo '{model_name}' nao encontrado no projeto.")
            return
        try:
            promote_model_to_shared(self.config, model_name)
        except (ValueError, OSError) as error:
            QMessageBox.warning(self, "Promover modelo", f"Nao foi possivel promover o modelo:\n{error}")
            return
        self.append_log(f"\n>>> Modelo promovido para compartilhados\nModelo: {model_name}\n")
        self.refresh_home_model_selector()
        QMessageBox.information(self, "Promover modelo", f"Modelo '{model_name}' copiado para modelos compartilhados.")
