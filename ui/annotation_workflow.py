from PyQt6.QtWidgets import QMessageBox

from services.config import save_config
from services.paths import SCRIPTS_DIR, active_model_path


class AnnotationWorkflowMixin:
    def run_annotation_mask_prediction(self):
        if self.process_runner.is_running():
            self.show_process_in_progress()
            return
        image_path = self.current_annotation_image_path()
        if image_path is None:
            QMessageBox.information(self, "Anotar", "Selecione uma imagem para gerar ou refazer a mascara.")
            return
        if not self.ensure_active_model():
            return
        self.save_annotation_prediction_config()
        params = self.annotation_page.model_parameters()
        current_entry = self.annotation_page.current_entry()
        output_path = (
            current_entry.seg_path
            if current_entry is not None
            else image_path.with_name(f"{image_path.stem}_seg.npy")
        )
        args = [
            str(SCRIPTS_DIR / "create_mask_with_model.py"),
            "--model",
            str(active_model_path(self.config)),
            "--image",
            str(image_path),
            "--output",
            str(output_path),
            "--padding",
            str(params["padding"]),
            "--diameter",
            params["diameter"],
            "--cellprob-threshold",
            params["cellprob_threshold"],
            "--flow-threshold",
            params["flow_threshold"],
        ]
        self.pending_annotation_image_name = image_path.name
        self.pending_annotation_image_path = image_path
        self.set_annotation_busy(True, f"Gerando mascara para {image_path.name}...")
        if not self.run_script("Criar mascara", args):
            self.set_annotation_busy(False)
        else:
            self.set_annotation_busy(True, f"Gerando mascara para {image_path.name}...")

    def save_annotation_prediction_config(self):
        if hasattr(self, "dataset_prediction_diameter"):
            self.annotation_page.diameter.setText(self.dataset_prediction_diameter.text().strip())
        self.annotation_page.save_model_parameters_to_config(self.config, self.parse_float)
        save_config(self.config)

    def set_annotation_busy(self, busy, message=None):
        if hasattr(self, "annotation_page"):
            self.annotation_page.set_busy(busy, message)
        for attr in ["dataset_predict_mask_button", "dataset_edit_mask_button"]:
            if hasattr(self, attr):
                getattr(self, attr).setEnabled(not busy)
        if hasattr(self, "dataset_mask_progress"):
            self.dataset_mask_progress.setVisible(busy)
        if hasattr(self, "dataset_preview_label"):
            self.dataset_preview_label.setEnabled(not busy)
        if hasattr(self, "dataset_preview_info"):
            if busy and message:
                self.dataset_preview_info.setText(message)
            elif not busy:
                self.dataset_preview_info.setText(
                    "Imagens sem mascara entram como teste para Resultados. Duplo clique para editar/criar mascara."
                )
