from pathlib import Path
import os

from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from services.paths import PROJECT_DIR
from ui.styles import APP_STYLE


class WindowChromeMixin:
    def build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        file_menu = menu_bar.addMenu("Arquivo")
        self.add_menu_action(file_menu, "Sair", self.close, "Ctrl+Q")

        model_menu = menu_bar.addMenu("Modelo")
        self.add_menu_action(model_menu, "Importar modelo", self.import_prediction_model)
        model_menu.addSeparator()
        self.add_menu_action(model_menu, "Treinar modelo", self.open_training_page)
        self.add_menu_action(model_menu, "Compactar mascaras", self.run_mask_compaction)

        results_menu = menu_bar.addMenu("Resultados")
        self.add_menu_action(results_menu, "Gerar resultados", self.run_results, "Ctrl+R")
        self.add_menu_action(results_menu, "Visualizar resultados", self.open_results_viewer)

        help_menu = menu_bar.addMenu("Ajuda")
        self.add_menu_action(help_menu, "Sobre", self.show_about)

    def add_menu_action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def set_page(self, index):
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def set_view_mode(self, mode):
        self.current_view_mode = mode
        for key, button in self.view_buttons.items():
            button.setProperty("active", key == mode)
            button.style().unpolish(button)
            button.style().polish(button)
        stem = self.current_result_image_stem()
        if stem:
            self.show_analysis_image(stem)

    def choose_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta", str(PROJECT_DIR))
        if folder:
            try:
                line_edit.setText(str(Path(folder).relative_to(PROJECT_DIR)))
            except ValueError:
                line_edit.setText(folder)

    def parse_float(self, value, default):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return default

    def open_folder(self, folder):
        Path(folder).mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def open_file(self, file_path):
        if not file_path.exists():
            QMessageBox.information(self, "Arquivo nao encontrado", str(file_path))
            return
        os.startfile(file_path)

    def show_about(self):
        QMessageBox.information(
            self,
            "Sobre",
            "Cellpose - Vasos de Eucalipto\n\n"
            "Interface local para preparar datasets, treinar modelos, gerar predicoes, "
            "criar overlays e avaliar metricas por projeto.",
        )

    def apply_style(self):
        self.setStyleSheet(APP_STYLE)

