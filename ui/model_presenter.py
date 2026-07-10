import time

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QHeaderView, QMessageBox, QTableWidgetItem

from services.config import save_config, with_derived_paths
from services.metrics import format_size
from services.model_service import first_model_name, list_model_names, list_model_paths
from services.paths import (
    active_model_path,
    dataset_images_dir,
    metrics_csv_path,
    project_models_dir,
    relative_to_project,
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
        self.project_models_table.setRowCount(len(models))
        active_row = None
        for row, model_path in enumerate(models):
            values = [
                model_path.name,
                format_size(model_path.stat().st_size),
                time.strftime("%d/%m/%Y %H:%M", time.localtime(model_path.stat().st_mtime)),
                "sim" if metrics_csv_path(self.config, model_path.name).exists() else "nao",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if model_path.name == self.config["active_model"]:
                    item.setForeground(QColor("#1f2933"))
                self.project_models_table.setItem(row, col, item)
            if model_path.name == self.config["active_model"]:
                active_row = row
            self.project_models_table.setRowHeight(row, 30)

        self.project_models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.project_models_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        if active_row is not None:
            self.project_models_table.selectRow(active_row)
        else:
            self.project_models_table.clearSelection()

    def refresh_prediction(self):
        self.config = with_derived_paths(self.config)
        self.predict_model_label.setText(self.config["active_model"] or "Nenhum modelo selecionado")
        self.pred_input.setText(relative_to_project(dataset_images_dir(self.config), self.config))
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

        models = list_model_names(self.config)
        self.home_model_combo.blockSignals(True)
        self.home_model_combo.clear()
        self.home_model_combo.addItem("Selecione um modelo", "")
        for model_name in models:
            self.home_model_combo.addItem(model_name, model_name)

        active_model = self.config.get("active_model") or ""
        index = self.home_model_combo.findData(active_model)
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

    def select_project_model(self):
        if not hasattr(self, "project_models_table"):
            return
        row = self.project_models_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Modelo", "Selecione um modelo na tabela.")
            return
        self.set_active_model(self.project_models_table.item(row, 0).text())
