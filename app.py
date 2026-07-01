import runpy
import sys
import traceback

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMainWindow

from controllers.process_runner import ScriptProcessRunner
from services.config import load_config
from ui.annotation_workflow import AnnotationWorkflowMixin
from ui.dataset_import_presenter import DatasetImportPresenterMixin
from ui.analysis_presenter import AnalysisPresenterMixin
from ui.dataset_preview_presenter import DatasetPreviewPresenterMixin
from ui.dataset_presenter import DatasetPresenterMixin
from ui.dialogs.error_dialog import ErrorDialog
from ui.model_presenter import ModelPresenterMixin
from ui.page_builders import UiBuilderMixin
from ui.prediction_import_presenter import PredictionImportPresenterMixin
from ui.process_presenter import ProcessPresenterMixin
from ui.project_presenter import ProjectPresenterMixin
from ui.progress_presenter import ProgressPresenterMixin
from ui.result_actions import ResultActionsMixin
from ui.results_page_builder import ResultsPageBuilderMixin
from ui.result_workflows import ResultWorkflowMixin
from ui.results_presenter import ResultsPresenterMixin
from ui.script_workflows import ScriptWorkflowMixin
from ui.training_page_builder import TrainingPageBuilderMixin
from ui.training_presenter import TrainingPresenterMixin
from ui.window_chrome import WindowChromeMixin


class CellposeWindow(
    AnalysisPresenterMixin,
    AnnotationWorkflowMixin,
    DatasetImportPresenterMixin,
    DatasetPreviewPresenterMixin,
    DatasetPresenterMixin,
    ResultActionsMixin,
    ResultsPageBuilderMixin,
    ResultWorkflowMixin,
    ResultsPresenterMixin,
    PredictionImportPresenterMixin,
    ModelPresenterMixin,
    ProcessPresenterMixin,
    ProjectPresenterMixin,
    ScriptWorkflowMixin,
    ProgressPresenterMixin,
    TrainingPageBuilderMixin,
    TrainingPresenterMixin,
    UiBuilderMixin,
    WindowChromeMixin,
    QMainWindow,
):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.process_runner = ScriptProcessRunner(self)
        self.process_runner.output_received.connect(self.process_output_received)
        self.process_runner.finished.connect(self.process_finished)
        self.process_runner.error_occurred.connect(self.process_error_occurred)
        self.pending_actions = []
        self.pending_annotation_image_name = None
        self.pending_annotation_image_path = None
        self.current_process_title = ""
        self.current_process_error = ""
        self.result_process_titles = {"Gerar resultados", "Avaliar modelo", "Gerar CSVs de medidas"}
        self.training_start_time = None
        self.current_view_mode = "overlay"
        self.nav_buttons = []
        self.metric_labels = {}
        self.analysis_metric_labels = {}
        self.analysis_cache = {}
        self.analysis_render_cache = {}
        self.analysis_pixmap_cache = {}
        self.viewer_render_cache = {}
        self.result_entries_cache = None
        self.result_status_index = {}
        self.result_status_index_model = None
        self.result_row_by_stem = {}
        self.runtime_overlay_ready_stems = set()
        self.runtime_metrics_ready_stems = set()
        self.pending_result_stems = None
        self.auto_measure_after_evaluation = False
        self.training_dialog = None
        self.model_import_thread = None
        self.model_import_worker = None
        self.dataset_scan_thread = None
        self.dataset_scan_worker = None
        self.bulk_updating_dataset_groups = False
        self.deferred_startup_steps = []
        self.deferred_startup_total = 0

        self.setWindowTitle("Cellpose - Vasos de Eucalipto")
        self.resize(1320, 820)
        self.setMinimumSize(900, 600)

        self.build_menu()
        self.build_ui()
        self.training_timer = QTimer(self)
        self.training_timer.timeout.connect(self.update_training_elapsed)
        self.refresh_startup_shell()
        QTimer.singleShot(0, self.begin_deferred_startup_refresh)

def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--run-script":
        script_path = sys.argv[2]
        sys.argv = [script_path, *sys.argv[3:]]
        runpy.run_path(script_path, run_name="__main__")
        return

    app = QApplication(sys.argv)
    window = None

    def handle_exception(exc_type, exc_value, exc_traceback):
        details = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        try:
            if window is not None:
                window.append_log(f"\n>>> Erro inesperado\n{details}\n")
                window.show_error("Erro inesperado", str(exc_value) or "Ocorreu um erro inesperado.", details)
            else:
                ErrorDialog(None, "Erro inesperado", str(exc_value) or "Ocorreu um erro inesperado.", details).exec()
        except Exception:
            sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception
    window = CellposeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()





