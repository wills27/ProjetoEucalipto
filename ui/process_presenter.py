import sys

from PyQt6.QtWidgets import QMessageBox

from services.config import load_config
from services.paths import PROJECT_DIR
from services.process_output import process_error_summary
from ui.dialogs.error_dialog import ErrorDialog


class ProcessPresenterMixin:
    def run_script(self, title, args):
        if self.process_runner.is_running():
            self.show_process_in_progress()
            return False

        self.current_process_title = title
        self.current_process_error = ""
        self.current_process_model = self.config.get("active_model") or ""
        if title == "Gerar resultados":
            self.runtime_overlay_ready_stems.clear()
            self.runtime_metrics_ready_stems.clear()
        if title == "Treinar modelo":
            self.start_training_progress()
        if title in self.result_process_titles:
            self.start_result_progress(title)
        if title in {"Exportar dataset", "Compactar mascaras"}:
            self.start_task_progress(title, detail=f"{title}...")
        self.append_log(f"\n>>> {title}\n")
        self.append_log(" ".join([sys.executable, "-u", *args]) + "\n")

        self.process_runner.start(args, PROJECT_DIR)
        if title not in {"Criar mascara", "Exportar dataset", "Compactar mascaras"} and title not in self.result_process_titles:
            self.refresh_all()
        return True

    def process_output_received(self, text):
        self.append_log(text)
        self.capture_process_error(text)
        self.update_training_last_message(text)
        self.update_result_progress(text)
        self.update_task_progress_from_output(text)
        self.update_result_status_from_output(text)

    def process_finished(self, exit_code):
        self.append_log(f">>> Finalizado com codigo {exit_code}\n")
        finished_title = self.current_process_title
        if self.current_process_title in self.result_process_titles:
            self.clear_analysis_caches()
            self.finish_result_progress(exit_code)
        if self.current_process_title == "Treinar modelo":
            self.finish_training_progress(exit_code)
        if self.current_process_title == "Exportar dataset":
            self.finish_task_progress(
                "Dataset exportado." if exit_code == 0 else "Erro ao exportar dataset.",
                success=exit_code == 0,
            )
        if self.current_process_title == "Compactar mascaras":
            self.finish_task_progress(
                "Mascaras compactadas." if exit_code == 0 else "Erro ao compactar mascaras.",
                success=exit_code == 0,
            )
            if exit_code == 0:
                self.clear_analysis_caches()
                self.refresh_dataset_import()
        if self.current_process_title == "Criar mascara" and exit_code == 0:
            self.set_annotation_view_mode("overlay")
            if hasattr(self, "annotation_page") and self.pending_annotation_image_name:
                self.annotation_page.reload_current_image()
                self.annotation_page.set_status(f"Mascara atualizada: {self.pending_annotation_image_name}")
        if finished_title == "Criar mascara":
            if exit_code != 0:
                self.set_annotation_busy(False, "Falha ao gerar mascara automatica.")
            else:
                self.set_annotation_busy(False)
        continue_after_failed_evaluation = (
            exit_code != 0
            and self.current_process_title == "Avaliar modelo"
            and self.auto_measure_after_evaluation
        )
        if exit_code != 0:
            self.show_process_error(exit_code)
        self.current_process_title = ""
        self.current_process_model = ""
        self.config = load_config()
        self.runtime_overlay_ready_stems.clear()
        self.runtime_metrics_ready_stems.clear()
        if not self.pending_actions:
            self.pending_result_stems = None
        self.refresh_all()
        if finished_title == "Criar mascara":
            self.pending_annotation_image_path = None
            self.pending_annotation_image_name = None
        if continue_after_failed_evaluation:
            self.auto_measure_after_evaluation = False
            if self.pending_actions and self.pending_actions[0] == self.run_cell_measurements:
                next_action = self.pending_actions.pop(0)
                next_action()
            return
        if self.pending_actions:
            next_action = self.pending_actions.pop(0)
            next_action()

    def process_error_occurred(self, error_message, failed_to_start):
        self.current_process_error = error_message
        self.append_log(f">>> Erro no processo: {error_message}\n")
        if not failed_to_start:
            return
        if self.current_process_title == "Criar mascara":
            self.set_annotation_busy(False, "Falha ao iniciar geracao de mascara.")
            self.pending_annotation_image_path = None
            self.pending_annotation_image_name = None
        if self.current_process_title in self.result_process_titles:
            self.clear_analysis_caches()
            self.finish_result_progress(1)
        if self.current_process_title == "Treinar modelo":
            self.finish_training_progress(1)
        if self.current_process_title == "Exportar dataset":
            self.finish_task_progress("Erro ao exportar dataset.", success=False)
        if self.current_process_title == "Compactar mascaras":
            self.finish_task_progress("Erro ao compactar mascaras.", success=False)
        self.pending_actions.clear()
        self.runtime_overlay_ready_stems.clear()
        self.runtime_metrics_ready_stems.clear()
        self.pending_result_stems = None
        title = self.current_process_title or "Processo"
        self.current_process_title = ""
        self.current_process_model = ""
        self.config = load_config()
        self.refresh_all()
        self.show_error("Erro no processo", f"{title} nao conseguiu iniciar.", error_message)

    def show_process_in_progress(self):
        title = self.current_process_title or "processo atual"
        QMessageBox.information(self, "Processo em andamento", f"Aguarde {title} terminar.")

    def append_log(self, text):
        self.log_text.moveCursor(self.log_text.textCursor().MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(self.log_text.textCursor().MoveOperation.End)

    def capture_process_error(self, text):
        summary = process_error_summary(text)
        if summary:
            self.current_process_error = summary

    def show_process_error(self, exit_code):
        message = self.current_process_error or "O processo terminou com erro, mas nao retornou detalhes."
        if self.current_process_title == "Treinar modelo":
            self.training_status_label.setText("Treino finalizado com erro.")
            self.training_last_message_label.setText(f"Erro: {message.splitlines()[-1]}")
        self.show_error(
            "Erro no processo",
            f"{self.current_process_title or 'Processo'} terminou com codigo {exit_code}.",
            message,
        )

    def show_error(self, title, message, details=""):
        dialog = ErrorDialog(self, title, message, details)
        dialog.exec()
