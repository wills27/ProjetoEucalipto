from pathlib import Path
import os

from PyQt6.QtGui import QAction, QActionGroup, QKeySequence
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from services.config import save_config, with_derived_paths
from services.i18n import AVAILABLE_LANGUAGES, get_language, set_language, tr
from services.paths import DEFAULT_IMAGE_SET, PROJECT_DIR, is_pending_image_set
from ui.styles import APP_STYLE


class WindowChromeMixin:
    def build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        self.file_menu = menu_bar.addMenu(tr("menu.file"))
        self.action_exit = self.add_menu_action(self.file_menu, tr("menu.file.exit"), self.close, "Ctrl+Q")

        self.model_menu = menu_bar.addMenu(tr("menu.model"))
        self.action_import_model = self.add_menu_action(
            self.model_menu, tr("menu.model.import"), self.import_prediction_model
        )
        self.action_remove_model = self.add_menu_action(
            self.model_menu, tr("menu.model.remove"), self.remove_active_model
        )
        self.action_promote_model = self.add_menu_action(
            self.model_menu, tr("menu.model.promote"), self.promote_active_model
        )
        self.model_menu.addSeparator()
        self.action_train_model = self.add_menu_action(
            self.model_menu, tr("menu.model.train"), self.open_training_page
        )
        self.action_compact_masks = self.add_menu_action(
            self.model_menu, tr("menu.model.compact_masks"), self.run_mask_compaction
        )

        self.results_menu = menu_bar.addMenu(tr("menu.results"))
        self.action_generate_results = self.add_menu_action(
            self.results_menu, tr("menu.results.generate"), self.run_results, "Ctrl+R"
        )
        self.action_view_results = self.add_menu_action(
            self.results_menu, tr("menu.results.view"), self.open_results_viewer
        )

        self.help_menu = menu_bar.addMenu(tr("menu.help"))
        self.action_about = self.add_menu_action(self.help_menu, tr("menu.help.about"), self.show_about)

        self.language_menu = menu_bar.addMenu(tr("menu.language"))
        self.language_action_group = QActionGroup(self)
        self.language_action_group.setExclusive(True)
        self.language_actions = {}
        for code, label in AVAILABLE_LANGUAGES.items():
            action = QAction(label, self)
            action.setCheckable(True)
            action.setChecked(get_language() == code)
            action.triggered.connect(lambda checked=False, lang=code: self.change_language(lang))
            self.language_action_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[code] = action

    def change_language(self, language):
        if get_language() == language:
            return
        set_language(language)
        self.config["language"] = language
        save_config(self.config)
        self.retranslate_ui()

    def retranslate_ui(self):
        """Reaplica tr() nos widgets que ficam vivos a sessao inteira (menu,
        sidebar, painel de resultados) quando o idioma muda - dialogs
        recriados do zero a cada abertura (ex. CalibrationDialog) nao
        precisam disso."""
        self.retranslate_menu()
        if hasattr(self, "retranslate_sidebar"):
            self.retranslate_sidebar()
        if hasattr(self, "retranslate_results_page"):
            self.retranslate_results_page()

    def retranslate_menu(self):
        self.file_menu.setTitle(tr("menu.file"))
        self.action_exit.setText(tr("menu.file.exit"))
        self.model_menu.setTitle(tr("menu.model"))
        self.action_import_model.setText(tr("menu.model.import"))
        self.action_remove_model.setText(tr("menu.model.remove"))
        self.action_promote_model.setText(tr("menu.model.promote"))
        self.action_train_model.setText(tr("menu.model.train"))
        self.action_compact_masks.setText(tr("menu.model.compact_masks"))
        self.results_menu.setTitle(tr("menu.results"))
        self.action_generate_results.setText(tr("menu.results.generate"))
        self.action_view_results.setText(tr("menu.results.view"))
        self.help_menu.setTitle(tr("menu.help"))
        self.action_about.setText(tr("menu.help.about"))
        self.language_menu.setTitle(tr("menu.language"))

    def add_menu_action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def closeEvent(self, event):
        # Imagens importadas antes de existir um conjunto ficam numa pasta
        # temporaria (e quaisquer predicoes ja geradas para elas); ao fechar
        # o app normalmente, sao descartadas.
        if is_pending_image_set(self.config):
            self.discard_pending_image_set_if_active()
            self.config["active_image_set"] = DEFAULT_IMAGE_SET
            self.config = with_derived_paths(self.config)
            save_config(self.config)
        super().closeEvent(event)

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
            QMessageBox.information(self, tr("file_not_found.title"), str(file_path))
            return
        os.startfile(file_path)

    def show_about(self):
        QMessageBox.information(self, tr("about.title"), tr("about.text"))

    def apply_style(self):
        self.setStyleSheet(APP_STYLE)

