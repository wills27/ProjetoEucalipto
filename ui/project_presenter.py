from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFileDialog, QInputDialog

from services.config import load_config, save_config, with_derived_paths
from services.model_service import first_model_name
from services.paths import (
    active_project_dir,
    ensure_project_structure,
    list_projects,
    projects_dir,
)
from ui.dialogs.calibration_dialog import CalibrationDialog


class ProjectPresenterMixin:
    def calibration(self):
        calibration = self.config.get("calibration", {})
        unit = calibration.get("unit", "um")
        try:
            unit_per_pixel = float(calibration.get("unit_per_pixel", 0.0) or 0.0)
        except (TypeError, ValueError):
            unit_per_pixel = 0.0
        return unit, unit_per_pixel

    def calibration_text(self):
        unit, unit_per_pixel = self.calibration()
        if unit_per_pixel <= 0:
            return "Calibracao: nao definida"
        return f"Calibracao: {unit_per_pixel:.6g} {unit}/px"

    def refresh_calibration_labels(self):
        text = self.calibration_text()
        for attr in ["dataset_calibration_label", "results_calibration_label"]:
            if hasattr(self, attr):
                getattr(self, attr).setText(text)

    def open_calibration_dialog(self):
        dialog = CalibrationDialog(self)
        dialog.exec()

    def select_project(self, project_name):
        if not project_name or project_name == self.config.get("active_project"):
            return
        self.reset_project_dependent_state()
        self.config["active_project"] = project_name
        self.config["active_model"] = first_model_name(self.config)
        self.config = with_derived_paths(self.config)
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()

    def create_project(self):
        name, ok = QInputDialog.getText(self, "Criar projeto", "Nome do projeto:")
        if not ok:
            return
        name = name.strip().replace(" ", "_")
        if not name:
            return
        self.reset_project_dependent_state()
        self.config["active_project"] = name
        self.config["active_model"] = ""
        ensure_project_structure(active_project_dir(self.config))
        self.config = with_derived_paths(self.config)
        save_config(self.config)
        self.refresh_all()

    def reset_project_dependent_state(self):
        self.pending_annotation_image_name = None
        self.pending_annotation_image_path = None
        self.clear_analysis_caches()
        if hasattr(self, "annotation_page"):
            self.annotation_page.current_image_entry = None
            self.annotation_page.base_image = None
            self.annotation_page.mask = None
            self.annotation_page.mask_history = []
            self.annotation_page.reset_transient_drawing()
        if hasattr(self, "dataset_preview_label"):
            self.dataset_preview_label.setText("Selecione uma imagem.")
            self.dataset_preview_label.setPixmap(QPixmap())
        if hasattr(self, "dataset_preview_info"):
            self.dataset_preview_info.setText("Imagem e mascara aparecem aqui. Duplo clique para editar a mascara.")
        if hasattr(self, "preview_label"):
            self.preview_label.setText("Selecione uma imagem.")
            self.preview_label.setPixmap(QPixmap())
        if hasattr(self, "result_images_table"):
            self.result_images_table.clearContents()
            self.result_images_table.setRowCount(0)
        if hasattr(self, "result_progress_bar"):
            self.result_progress_bar.setRange(0, 100)
            self.result_progress_bar.setValue(0)
            self.result_progress_bar.setFormat("%p%")
        if hasattr(self, "result_progress_label"):
            self.result_progress_label.setText("Aguardando processo.")
        if hasattr(self, "analysis_metric_labels"):
            for value in self.analysis_metric_labels.values():
                value.setText("-")
        if hasattr(self, "cell_counts_table"):
            self.cell_counts_table.clear()
            self.cell_counts_table.setRowCount(0)
            self.cell_counts_table.setColumnCount(0)
        if hasattr(self, "cell_measurements_table"):
            self.cell_measurements_table.clear()
            self.cell_measurements_table.setRowCount(0)
            self.cell_measurements_table.setColumnCount(0)
        if hasattr(self, "measurements_status_label"):
            self.measurements_status_label.setText("Gere os CSVs de medidas para visualizar os dados aqui.")

    def choose_projects_folder(self):
        current_dir = projects_dir(self.config)
        current_dir.mkdir(parents=True, exist_ok=True)
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta de projetos", str(current_dir))
        if not folder:
            return

        self.reset_project_dependent_state()
        self.config["projects_dir"] = folder
        available_projects = list_projects(self.config)
        if available_projects:
            self.config["active_project"] = available_projects[0]
            self.config["active_model"] = first_model_name(self.config)
        else:
            self.config["active_project"] = "eucalipto"
            self.config["active_model"] = ""
            ensure_project_structure(active_project_dir(self.config))
        self.config = with_derived_paths(self.config)
        save_config(self.config)
        self.refresh_all()

    def refresh_all(self):
        self.config = load_config()
        ensure_project_structure(active_project_dir(self.config))
        self.refresh_project_selector()
        self.refresh_project()
        self.refresh_dataset_import()
        self.refresh_project_models_table()
        self.refresh_prediction()
        self.refresh_analysis_images()
        self.refresh_analysis_metrics()
        self.refresh_measurement_tables()
        self.refresh_calibration_labels()

    def refresh_startup_shell(self):
        self.config = load_config()
        ensure_project_structure(active_project_dir(self.config))
        self.refresh_project_selector()
        self.refresh_project()
        self.refresh_prediction()
        self.refresh_calibration_labels()
        if hasattr(self, "dataset_validation_summary"):
            self.dataset_validation_summary.setText("Carregando dataset...")
        if hasattr(self, "results_list_status"):
            self.results_list_status.setText("Carregando resultados...")
        self.statusBar().showMessage("Abrindo projeto...")

    def begin_deferred_startup_refresh(self):
        self.deferred_startup_steps = [
            ("Dataset", self.refresh_dataset_import),
            ("Resultados", self.refresh_analysis_images),
            ("Metricas", self.refresh_analysis_metrics),
            ("Tabelas", self.refresh_measurement_tables),
        ]
        self.deferred_startup_total = len(self.deferred_startup_steps)
        self.start_task_progress("Carregando projeto", total=self.deferred_startup_total, detail="Carregando projeto...")
        QTimer.singleShot(50, self.run_next_deferred_startup_step)

    def run_next_deferred_startup_step(self):
        if not self.deferred_startup_steps:
            self.finish_task_progress("Projeto carregado.", success=True)
            return
        done = self.deferred_startup_total - len(self.deferred_startup_steps)
        label, callback = self.deferred_startup_steps.pop(0)
        self.update_task_progress(done, self.deferred_startup_total, f"Carregando: {label}")
        callback()
        self.update_task_progress(done + 1, self.deferred_startup_total, f"Carregado: {label}")
        QTimer.singleShot(50, self.run_next_deferred_startup_step)

    def refresh_project_selector(self):
        if not hasattr(self, "project_combo"):
            return
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = list_projects(self.config)
        self.project_combo.addItems(projects)
        index = self.project_combo.findText(self.config["active_project"])
        if index >= 0:
            self.project_combo.setCurrentIndex(index)
        self.project_combo.blockSignals(False)

    def refresh_project(self):
        self.refresh_project_models_table()
        self.refresh_home_model_selector()

    def refresh_annotation_images(self):
        if hasattr(self, "annotation_page"):
            self.annotation_page.refresh_images()

    def current_annotation_image_path(self):
        return self.annotation_page.current_image_path()

    def set_annotation_view_mode(self, mode):
        self.annotation_page.set_view_mode(mode)
