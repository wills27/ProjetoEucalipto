from pathlib import Path
import csv
import os
import re
import runpy
import shutil
import sys
import time
import traceback

import numpy as np
import tifffile as tiff
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QImage, QKeySequence, QPixmap
from services.config import load_config, save_config
from services.cell_measurements import (
    build_mask_inteiros,
    compute_ellipse_minor_axis_by_label,
    filtrar_celulas_borda_proporcional,
)
from services.image_arrays import normalize_array
from services.paths import (
    PROJECT_DIR,
    SCRIPTS_DIR,
    active_model_path,
    active_project_dir,
    cell_counts_csv_path,
    cell_measurements_csv_path,
    conversion_input_dir,
    dataset_plan_path,
    ensure_project_structure,
    list_projects,
    metrics_csv_path,
    model_outputs_dir,
    overlays_dir,
    predictions_dir,
    projects_dir,
    project_models_dir,
    project_path,
    relative_to_project,
)
from services.dataset_plan import auto_split_indices, load_plan, save_plan, summarize_table_entries
from services.metrics import count_files, format_size, read_metrics, summarize_metrics
from services.training_log_parser import parse_training_log_line
from services.annotation import validate_mask_file
from ui.annotation_page import AnnotationPage
from ui.loss_plot import LossPlotWidget
from ui.mask_edit_target import DatasetMaskTarget, ResultMaskTarget
from ui.styles import APP_STYLE
from ui.widgets import AnnotationPreviewLabel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from skimage.measure import regionprops
from skimage.segmentation import find_boundaries


IMAGE_EXTENSIONS = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]


class ErrorDialog(QDialog):
    def __init__(self, parent, title, message, details=""):
        super().__init__(parent)
        self.setWindowTitle(title or "Erro")
        self.resize(680, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel(title or "Erro")
        header.setObjectName("errorTitle")
        header.setWordWrap(True)
        layout.addWidget(header)

        body = QLabel(message or "Ocorreu um erro inesperado.")
        body.setObjectName("errorMessage")
        body.setWordWrap(True)
        layout.addWidget(body)

        self.details_text = QTextEdit()
        self.details_text.setObjectName("errorDetails")
        self.details_text.setReadOnly(True)
        self.details_text.setPlainText(details or message or "")
        layout.addWidget(self.details_text, 1)

        actions = QHBoxLayout()
        copy_button = QPushButton("Copiar detalhes")
        copy_button.clicked.connect(self.copy_details)
        close_button = QPushButton("Fechar")
        close_button.setObjectName("primary")
        close_button.clicked.connect(self.accept)
        actions.addWidget(copy_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def copy_details(self):
        QApplication.clipboard().setText(self.details_text.toPlainText())


class CalibrationDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.image = None
        self.image_path = None
        self.points = []
        self.setWindowTitle("Calibracao")
        self.resize(980, 720)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        preview_box = window.panel("Imagem de referencia")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_label = AnnotationPreviewLabel(
            self.add_point,
            None,
            None,
            draw_button=Qt.MouseButton.LeftButton,
        )
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(620, 520)
        preview_layout.addWidget(self.preview_label, 1)
        preview_actions = QHBoxLayout()
        window.add_button(preview_actions, "Imagem do projeto", self.open_project_image)
        window.add_button(preview_actions, "Imagem externa", self.open_external_image)
        window.add_button(preview_actions, "Limpar pontos", self.clear_points)
        preview_actions.addStretch()
        preview_layout.addLayout(preview_actions)
        layout.addWidget(preview_box, 1)

        controls_box = window.panel("Escala")
        controls_layout = QVBoxLayout(controls_box)
        self.current_label = QLabel(window.calibration_text())
        self.current_label.setObjectName("hint")
        self.current_label.setWordWrap(True)
        controls_layout.addWidget(self.current_label)

        form = QGridLayout()
        self.unit_combo = QComboBox()
        self.unit_combo.setEditable(True)
        for unit in ["um", "mm", "nm"]:
            self.unit_combo.addItem(unit)
        self.pixel_distance = QLineEdit()
        self.real_distance = QLineEdit()
        self.unit_per_pixel = QLineEdit()
        form.addWidget(QLabel("Unidade"), 0, 0)
        form.addWidget(self.unit_combo, 0, 1)
        form.addWidget(QLabel("Distancia px"), 1, 0)
        form.addWidget(self.pixel_distance, 1, 1)
        form.addWidget(QLabel("Distancia real"), 2, 0)
        form.addWidget(self.real_distance, 2, 1)
        form.addWidget(QLabel("Unidade/px"), 3, 0)
        form.addWidget(self.unit_per_pixel, 3, 1)
        controls_layout.addLayout(form)

        hint = QLabel("Clique dois pontos na imagem ou informe os valores manualmente.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        controls_layout.addWidget(hint)

        controls_layout.addStretch()
        window.add_button(controls_layout, "Calcular unidade/px", self.calculate_unit_per_pixel)
        save_button = QPushButton("Salvar calibracao")
        save_button.setObjectName("primary")
        save_button.clicked.connect(self.save_calibration)
        controls_layout.addWidget(save_button)
        window.add_button(controls_layout, "Limpar calibracao", self.clear_calibration)
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.accept)
        controls_layout.addWidget(close_button)
        layout.addWidget(controls_box, 0)

        self.load_current_calibration()

    def load_current_calibration(self):
        calibration = self.window.config.get("calibration", {})
        unit = calibration.get("unit", "um")
        index = self.unit_combo.findText(unit)
        if index >= 0:
            self.unit_combo.setCurrentIndex(index)
        else:
            self.unit_combo.setEditText(unit)
        self.pixel_distance.setText(self.format_float(calibration.get("pixel_distance", 0.0)))
        self.real_distance.setText(self.format_float(calibration.get("real_distance", 0.0)))
        self.unit_per_pixel.setText(self.format_float(calibration.get("unit_per_pixel", 0.0)))

    def format_float(self, value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            value = 0.0
        return "" if value <= 0 else f"{value:.6g}"

    def open_project_image(self):
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Escolher imagem do projeto",
            str(active_project_dir(self.window.config)),
            "Imagens (*.tif *.tiff *.png *.jpg *.jpeg)",
        )
        if file_name:
            self.load_image(Path(file_name), "project_image")

    def open_external_image(self):
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Escolher imagem para calibracao",
            str(PROJECT_DIR),
            "Imagens (*.tif *.tiff *.png *.jpg *.jpeg)",
        )
        if file_name:
            self.load_image(Path(file_name), "external_image")

    def load_image(self, path, source):
        self.image_path = path
        self.image_source = source
        self.points = []
        self.image = self.window.load_image_as_rgb(path)
        self.update_preview()

    def add_point(self, source_label, x, y):
        if self.image is None:
            QMessageBox.information(self, "Calibracao", "Abra uma imagem para marcar os pontos.")
            return
        point = self.widget_to_image_xy(source_label, x, y)
        if point is None:
            return
        if len(self.points) >= 2:
            self.points = []
        self.points.append(point)
        if len(self.points) == 2:
            distance = self.distance_between_points(self.points[0], self.points[1])
            self.pixel_distance.setText(f"{distance:.3f}")
            self.calculate_unit_per_pixel(show_warning=False)
        self.update_preview()

    def widget_to_image_xy(self, source_label, x, y):
        if self.image is None:
            return None
        image_width, image_height = self.image.size
        scale = getattr(source_label, "_display_scale", None)
        offset_x = getattr(source_label, "_display_offset_x", 0)
        offset_y = getattr(source_label, "_display_offset_y", 0)
        if scale is None or scale == 0:
            return None
        image_x = int((x - offset_x) / scale)
        image_y = int((y - offset_y) / scale)
        if image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
            return None
        return image_x, image_y

    def distance_between_points(self, first, second):
        return ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5

    def update_preview(self):
        if self.image is None:
            self.preview_label.setText("Abra uma imagem ou informe a escala manualmente.")
            self.preview_label.setPixmap(QPixmap())
            return
        image = self.image.copy()
        draw = ImageDraw.Draw(image)
        for point in self.points:
            x, y = point
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 214, 74), outline=(0, 46, 40), width=2)
        if len(self.points) == 2:
            draw.line(self.points, fill=(255, 214, 74), width=3)
        self.window.set_label_pixmap(self.preview_label, image)

    def clear_points(self):
        self.points = []
        self.pixel_distance.clear()
        self.update_preview()

    def parse_float_field(self, field):
        text = field.text().strip().replace(",", ".")
        return float(text) if text else 0.0

    def calculate_unit_per_pixel(self, show_warning=True):
        try:
            pixels = self.parse_float_field(self.pixel_distance)
            real = self.parse_float_field(self.real_distance)
        except ValueError:
            if show_warning:
                QMessageBox.warning(self, "Calibracao", "Informe valores numericos validos.")
            return
        if pixels <= 0 or real <= 0:
            if show_warning:
                QMessageBox.warning(self, "Calibracao", "Informe distancia em pixels e distancia real maiores que zero.")
            return
        self.unit_per_pixel.setText(f"{real / pixels:.8g}")

    def save_calibration(self):
        try:
            unit_per_pixel = self.parse_float_field(self.unit_per_pixel)
            pixel_distance = self.parse_float_field(self.pixel_distance)
            real_distance = self.parse_float_field(self.real_distance)
        except ValueError:
            QMessageBox.warning(self, "Calibracao", "Informe valores numericos validos.")
            return
        unit = self.unit_combo.currentText().strip() or "um"
        if unit_per_pixel <= 0:
            QMessageBox.warning(self, "Calibracao", "Informe uma escala unidade/px maior que zero.")
            return
        self.window.config["calibration"] = {
            "unit": unit,
            "unit_per_pixel": unit_per_pixel,
            "pixel_distance": pixel_distance,
            "real_distance": real_distance,
            "source": getattr(self, "image_source", "manual") if self.image_path else "manual",
            "source_image": str(self.image_path) if self.image_path else "",
        }
        save_config(self.window.config)
        self.window.refresh_all()
        self.current_label.setText(self.window.calibration_text())
        QMessageBox.information(self, "Calibracao", "Calibracao salva.")

    def clear_calibration(self):
        self.window.config["calibration"] = {
            "unit": "um",
            "unit_per_pixel": 0.0,
            "pixel_distance": 0.0,
            "real_distance": 0.0,
            "source": "",
            "source_image": "",
        }
        save_config(self.window.config)
        self.window.refresh_all()
        self.load_current_calibration()
        self.current_label.setText(self.window.calibration_text())


class ResultsViewerDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.current_stem = None
        self.current_mask = None
        self.selected_label = None
        self.label_to_cell_id = {}
        self.measurements_by_image = {}
        self.setWindowTitle("Visualizar resultados")
        self.resize(1240, 820)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        left = window.panel("Imagens")
        left_layout = QVBoxLayout(left)
        self.image_list = QListWidget()
        self.image_list.currentTextChanged.connect(self.show_image)
        left_layout.addWidget(self.image_list, 1)
        window.add_button(left_layout, "Atualizar", self.refresh_all)
        layout.addWidget(left, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        visual_tab = QWidget()
        visual_layout = QVBoxLayout(visual_tab)
        self.calibration_label = QLabel(window.calibration_text())
        self.calibration_label.setObjectName("hint")
        visual_layout.addWidget(self.calibration_label)
        self.result_preview = AnnotationPreviewLabel(
            self.show_cell_values_at,
            None,
            None,
            draw_button=Qt.MouseButton.LeftButton,
        )
        self.result_preview.setObjectName("preview")
        self.result_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_preview.setMinimumSize(760, 520)
        self.cell_status_label = QLabel("Clique em uma celula para ver os valores.")
        self.cell_status_label.setObjectName("hint")
        self.cell_values_table = QTableWidget(0, 2)
        self.cell_values_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.cell_values_table.verticalHeader().setVisible(False)
        self.cell_values_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        visual_layout.addWidget(self.result_preview, 1)
        visual_layout.addWidget(self.cell_status_label)
        visual_layout.addWidget(self.cell_values_table, 0)
        self.tabs.addTab(visual_tab, "Visualizacao")

        self.counts_table = self.create_result_table()
        self.measurements_table = self.create_result_table()
        self.metrics_table = self.create_result_table()
        self.tabs.addTab(self.counts_table, "Contagens")
        self.tabs.addTab(self.measurements_table, "Medidas")
        self.tabs.addTab(self.metrics_table, "Metricas")

        actions = QHBoxLayout()
        window.add_button(actions, "Rodar avaliacao", self.run_evaluation)
        window.add_button(actions, "Gerar CSVs", self.run_measurements)
        actions.addStretch()
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.accept)
        actions.addWidget(close_button)
        visual_layout.addLayout(actions)

        self.refresh_all()

    def create_result_table(self):
        table = QTableWidget(0, 0)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        return table

    def refresh_all(self):
        self.calibration_label.setText(self.window.calibration_text())
        selected = self.image_list.currentItem().text() if self.image_list.currentItem() else None
        self.image_list.clear()
        for stem in self.window.result_image_entries():
            self.image_list.addItem(stem)

        self.load_measurement_index()
        self.window.populate_csv_table(self.counts_table, self.window.load_semicolon_csv(cell_counts_csv_path(self.window.config)))
        self.window.populate_csv_table(self.measurements_table, self.window.load_semicolon_csv(cell_measurements_csv_path(self.window.config)))
        self.populate_metrics_table()

        if selected:
            items = self.image_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            if items:
                self.image_list.setCurrentItem(items[0])
                return
        if self.image_list.count() > 0:
            self.image_list.setCurrentRow(0)

    def populate_metrics_table(self):
        rows = read_metrics(metrics_csv_path(self.window.config))
        if not rows:
            self.window.populate_csv_table(self.metrics_table, [])
            return
        headers = list(rows[0].keys())
        table_rows = [headers] + [[row.get(header, "") for header in headers] for row in rows]
        self.window.populate_csv_table(self.metrics_table, table_rows)

    def load_measurement_index(self):
        rows = self.window.load_semicolon_csv(cell_measurements_csv_path(self.window.config))
        self.measurements_by_image = {}
        if not rows:
            return
        headers = rows[0]
        for row in rows[1:]:
            values = {header: row[index] if index < len(row) else "" for index, header in enumerate(headers)}
            filename = values.get("filename", "")
            cell_id = values.get("cell_id", "")
            if filename and cell_id:
                self.measurements_by_image.setdefault(filename, {})[cell_id] = values

    def show_image(self, image_stem):
        if not image_stem:
            return
        self.current_stem = image_stem
        self.current_mask = None
        self.selected_label = None
        self.label_to_cell_id = {}
        image = self.render_id_overlay(image_stem)
        if image is None:
            self.result_preview.setText("Imagem ou predicao nao encontrada.")
            self.result_preview.setPixmap(QPixmap())
            self.clear_cell_values("Nenhuma celula selecionada.")
            return
        self.window.set_label_pixmap(self.result_preview, image)
        self.clear_cell_values("Clique em uma celula para ver os valores.")

    def render_id_overlay(self, image_stem):
        image_path = self.window.result_image_path(image_stem)
        pred_path = predictions_dir(self.window.config) / f"{image_stem}_pred_masks.tif"
        if image_path is None or not image_path.exists() or not pred_path.exists():
            return None
        base_image = self.window.load_image_as_rgb(image_path)
        mask = self.window.load_mask_array(pred_path)
        if mask is None:
            return None
        self.current_mask = mask
        self.label_to_cell_id = {
            int(region.label): index
            for index, region in enumerate(regionprops(mask), start=1)
        }
        return self.window.render_colored_id_overlay(
            base_image,
            mask,
            selected_label=self.selected_label,
            label_texts=self.label_to_cell_id,
        )

    def show_cell_values_at(self, source_label, x, y):
        if self.current_mask is None or self.current_stem is None:
            return
        point = self.widget_to_image_xy(source_label, x, y)
        if point is None:
            return
        image_x, image_y = point
        label_value = int(self.current_mask[image_y, image_x])
        if label_value == 0:
            self.selected_label = None
            if self.current_stem:
                image = self.render_id_overlay(self.current_stem)
                if image is not None:
                    self.window.set_label_pixmap(self.result_preview, image)
            self.clear_cell_values("Nenhuma celula nesse ponto.")
            return
        self.selected_label = label_value
        image = self.render_id_overlay(self.current_stem)
        if image is not None:
            self.window.set_label_pixmap(self.result_preview, image)
        cell_id = self.label_to_cell_id.get(label_value)
        image_values = self.measurements_by_image.get(self.current_stem, {})
        values = image_values.get(str(cell_id)) or image_values.get(str(label_value))
        if not values:
            values = self.measure_values_from_current_mask(label_value, cell_id)
        self.cell_status_label.setText(f"{self.current_stem} - celula {cell_id}")
        self.cell_values_table.setSortingEnabled(False)
        self.cell_values_table.setRowCount(len(values))
        self.cell_values_table.setColumnCount(2)
        self.cell_values_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        for row_index, (field, value) in enumerate(values.items()):
            self.cell_values_table.setItem(row_index, 0, QTableWidgetItem(field))
            self.cell_values_table.setItem(row_index, 1, QTableWidgetItem(value))
        self.cell_values_table.resizeColumnsToContents()
        self.cell_values_table.horizontalHeader().setStretchLastSection(True)
        self.cell_values_table.setSortingEnabled(True)

    def measure_values_from_current_mask(self, label_value, cell_id):
        if self.current_mask is None:
            return {"cell_id": str(cell_id or label_value)}
        for region in regionprops(self.current_mask):
            if int(region.label) != int(label_value):
                continue
            perimeter = getattr(region, "perimeter", None)
            unit, unit_per_pixel = self.window.calibration()
            has_calibration = unit_per_pixel > 0
            area = float(region.area)
            perimeter_value = float(perimeter) if perimeter is not None else 0.0
            return {
                "filename": self.current_stem or "",
                "cell_id": str(cell_id or label_value),
                "mask_label": str(label_value),
                "area_px": f"{area:.3f}",
                "perimeter_px": f"{perimeter_value:.3f}" if perimeter is not None else "",
                "centroid_x": f"{float(region.centroid[1]):.3f}",
                "centroid_y": f"{float(region.centroid[0]):.3f}",
                "area_calibrada": f"{area * (unit_per_pixel ** 2):.3f}" if has_calibration else "",
                "perimeter_calibrado": f"{perimeter_value * unit_per_pixel:.3f}" if has_calibration and perimeter is not None else "",
                "unidade": unit if has_calibration else "",
                "fonte": "calculado da mascara completa",
            }
        return {"cell_id": str(cell_id or label_value), "mask_label": str(label_value)}

    def widget_to_image_xy(self, source_label, x, y):
        if self.current_mask is None:
            return None
        image_height, image_width = self.current_mask.shape
        scale = getattr(source_label, "_display_scale", None)
        offset_x = getattr(source_label, "_display_offset_x", 0)
        offset_y = getattr(source_label, "_display_offset_y", 0)
        if scale is None or scale == 0:
            return None
        image_x = int((x - offset_x) / scale)
        image_y = int((y - offset_y) / scale)
        if image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
            return None
        return image_x, image_y

    def clear_cell_values(self, text):
        self.cell_status_label.setText(text)
        self.cell_values_table.setRowCount(0)

    def run_evaluation(self):
        self.window.run_evaluation()

    def run_measurements(self):
        self.window.run_cell_measurements()


class CellposeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.process = None
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
        self.result_entries_cache = None
        self.result_status_index = {}
        self.result_row_by_stem = {}
        self.runtime_overlay_ready_stems = set()
        self.runtime_metrics_ready_stems = set()
        self.pending_result_stems = None
        self.auto_measure_after_evaluation = False
        self.training_dialog = None

        self.setWindowTitle("Cellpose - Vasos de Eucalipto")
        self.resize(1320, 820)
        self.setMinimumSize(1100, 700)

        self.build_menu()
        self.build_ui()
        self.training_timer = QTimer(self)
        self.training_timer.timeout.connect(self.update_training_elapsed)
        self.refresh_all()

    def build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        file_menu = menu_bar.addMenu("Arquivo")
        self.add_menu_action(file_menu, "Importar imagens e mascaras", self.import_dataset_folder)
        file_menu.addSeparator()
        self.add_menu_action(file_menu, "Sair", self.close, "Ctrl+Q")

        project_menu = menu_bar.addMenu("Projeto")
        self.add_menu_action(project_menu, "Criar projeto", self.create_project, "Ctrl+N")
        self.add_menu_action(project_menu, "Pasta de projetos", self.choose_projects_folder)
        self.add_menu_action(project_menu, "Calibracao", self.open_calibration_dialog)

        model_menu = menu_bar.addMenu("Modelo")
        self.add_menu_action(model_menu, "Importar modelo", self.import_prediction_model)
        self.add_menu_action(model_menu, "Treinar modelo", self.open_training_dialog)

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

    def build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(12)
        root_layout.addLayout(body, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)
        body.addWidget(sidebar, 0)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        for label, builder in [
            ("Inicio", self.build_project_page),
            ("Resultados", self.build_results_page),
        ]:
            button = QPushButton(label)
            button.setObjectName("nav")
            button.clicked.connect(lambda checked=False, index=len(self.nav_buttons): self.set_page(index))
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
            page = QWidget()
            builder(page)
            self.stack.addWidget(page)

        sidebar_layout.addStretch()
        self.add_button(sidebar_layout, "Atualizar", self.refresh_all)

        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.hide()

        self.set_page(0)
        self.apply_style()

    def build_project_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        project_box = self.panel("Projeto atual")
        project_layout = QGridLayout(project_box)
        project_layout.setContentsMargins(10, 8, 10, 10)
        project_layout.setHorizontalSpacing(10)
        project_layout.setVerticalSpacing(6)
        self.project_combo = QComboBox()
        self.project_combo.currentTextChanged.connect(self.select_project)
        self.home_model_combo = QComboBox()
        self.home_model_combo.currentIndexChanged.connect(self.on_home_model_changed)
        project_layout.addWidget(QLabel("Projeto"), 0, 0)
        project_layout.addWidget(self.project_combo, 0, 1)
        project_layout.addWidget(QLabel("Modelo"), 0, 2)
        project_layout.addWidget(self.home_model_combo, 0, 3)
        project_actions = QHBoxLayout()
        self.add_button(project_actions, "Criar projeto", self.create_project)
        self.add_button(project_actions, "Pasta de projetos", self.choose_projects_folder)
        self.add_button(project_actions, "Treinar modelo", self.open_training_dialog)
        project_actions.addStretch()
        project_layout.addLayout(project_actions, 0, 4)
        project_layout.setColumnStretch(1, 1)
        project_layout.setColumnStretch(3, 1)
        layout.addWidget(project_box)

        self.build_dataset_section(layout, show_import_actions=False)

    def build_dataset_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        self.build_dataset_section(layout)

    def build_dataset_section(self, layout, show_import_actions=True):
        validation_box = self.panel("Selecao e divisao do dataset")
        validation_layout = QHBoxLayout(validation_box)
        table_layout = QVBoxLayout()
        self.dataset_validation_summary = QLabel()
        self.dataset_validation_summary.setObjectName("mono")
        table_layout.addWidget(self.dataset_validation_summary)
        self.dataset_calibration_label = QLabel("Calibracao: nao definida")
        self.dataset_calibration_label.setObjectName("hint")
        table_layout.addWidget(self.dataset_calibration_label)
        self.dataset_pairs_table = QTableWidget(0, 5)
        self.dataset_pairs_table.setHorizontalHeaderLabels(["Usar", "Grupo", "Imagem", "Segmentacao", "Status"])
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.verticalHeader().setVisible(False)
        self.dataset_pairs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dataset_pairs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.dataset_pairs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dataset_pairs_table.itemChanged.connect(self.save_dataset_plan_from_table)
        self.dataset_pairs_table.currentCellChanged.connect(self.on_dataset_pair_current_cell_changed)
        table_layout.addWidget(self.dataset_pairs_table, 1)
        validation_actions = QHBoxLayout()
        if show_import_actions:
            self.add_button(validation_actions, "Importar imagens", self.import_dataset_folder)
        self.add_button(validation_actions, "Padronizar TIFF", self.convert_dataset_images_to_tif)
        self.add_button(validation_actions, "Recarregar tabela", self.refresh_dataset_import)
        self.add_button(validation_actions, "Separar treino/teste", self.auto_split_dataset_table)
        validation_actions.addStretch()
        table_layout.addLayout(validation_actions)
        validation_layout.addLayout(table_layout, 1)

        preview_layout = QVBoxLayout()
        self.dataset_preview_label = AnnotationPreviewLabel(
            lambda *_args: None,
            lambda *_args: None,
            lambda *_args: None,
            double_click_callback=self.open_selected_dataset_editor,
            draw_button=None,
        )
        self.dataset_preview_label.setObjectName("preview")
        self.dataset_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dataset_preview_label.setMinimumSize(560, 520)
        self.dataset_preview_label.setWordWrap(True)
        self.dataset_preview_info = QLabel(
            "Imagens sem mascara entram como teste para Resultados. Duplo clique para editar/criar mascara."
        )
        self.dataset_preview_info.setObjectName("hint")
        self.dataset_preview_info.setWordWrap(True)
        preview_actions = QHBoxLayout()
        self.dataset_predict_mask_button = self.add_button(
            preview_actions,
            "Criar mascara com modelo",
            self.run_annotation_mask_prediction,
        )
        self.dataset_edit_mask_button = self.add_button(
            preview_actions,
            "Editar/desenhar mascara",
            self.open_selected_dataset_editor,
            primary=True,
        )
        preview_actions.addStretch()
        self.dataset_mask_progress = QProgressBar()
        self.dataset_mask_progress.setRange(0, 0)
        self.dataset_mask_progress.setTextVisible(False)
        self.dataset_mask_progress.setVisible(False)
        preview_layout.addWidget(self.dataset_preview_label, 1)
        preview_layout.addLayout(preview_actions)
        preview_layout.addWidget(self.dataset_mask_progress)
        preview_layout.addWidget(self.dataset_preview_info)
        validation_layout.addLayout(preview_layout, 2)
        layout.addWidget(validation_box, 1)

        self.annotation_page = AnnotationPage(self, build_ui=False)

    def build_train_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        form_box = self.panel("Novo modelo")
        form_layout = QGridLayout(form_box)
        form_layout.setContentsMargins(10, 8, 10, 10)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(6)
        self.train_model_name = QLineEdit("cpsam_vasos_eucalipto_v2")
        self.train_base_model = QLineEdit("cpsam")
        self.train_epochs = QSpinBox()
        self.train_epochs.setRange(1, 10000)
        self.train_epochs.setValue(100)
        self.train_learning_rate = QLineEdit("1e-5")
        self.train_weight_decay = QLineEdit("0.1")
        self.train_batch_size = QSpinBox()
        self.train_batch_size.setRange(1, 512)
        self.train_batch_size.setValue(1)
        self.train_epochs.setFixedWidth(104)
        self.train_batch_size.setFixedWidth(92)
        for field in [self.train_learning_rate, self.train_weight_decay]:
            field.setFixedWidth(104)

        training_params = QWidget()
        training_params_layout = QGridLayout(training_params)
        training_params_layout.setContentsMargins(0, 0, 0, 0)
        training_params_layout.setHorizontalSpacing(8)
        training_params_layout.setVerticalSpacing(6)
        for index, (label, field) in enumerate([
            ("Epocas", self.train_epochs),
            ("Learning rate", self.train_learning_rate),
            ("Weight decay", self.train_weight_decay),
            ("Batch", self.train_batch_size),
        ]):
            row = index // 2
            column = (index % 2) * 2
            training_params_layout.addWidget(QLabel(label), row, column)
            training_params_layout.addWidget(field, row, column + 1)
        training_params_layout.setColumnStretch(4, 1)

        form_layout.addWidget(QLabel("Nome do modelo"), 0, 0)
        form_layout.addWidget(self.train_model_name, 0, 1)
        form_layout.addWidget(QLabel("Modelo base"), 1, 0)
        form_layout.addWidget(self.train_base_model, 1, 1)
        form_layout.addWidget(QLabel("Parametros"), 2, 0)
        form_layout.addWidget(training_params, 2, 1)
        train_button = QPushButton("Iniciar treinamento")
        train_button.setObjectName("primary")
        train_button.clicked.connect(self.run_training)
        form_layout.addWidget(train_button, 3, 1)
        top_layout.addWidget(form_box, 1)

        progress_box = self.panel("Status do treino")
        progress_layout = QVBoxLayout(progress_box)
        self.training_status_label = QLabel("Aguardando treino.")
        self.training_status_label.setObjectName("largeText")
        self.training_model_label = QLabel("Modelo: -")
        self.training_elapsed_label = QLabel("Tempo decorrido: 00:00:00")
        self.training_epoch_label = QLabel("Epocas: 0/0")
        self.training_epoch_label.setObjectName("largeText")
        self.training_epoch_progress = QProgressBar()
        self.training_epoch_progress.setRange(0, 100)
        self.training_epoch_progress.setValue(0)
        self.training_epoch_progress.setFormat("%p%")
        self.training_epoch_progress.setTextVisible(True)
        self.training_detail_label = QLabel("Detalhes: aguardando inicio")
        self.training_detail_label.setWordWrap(True)
        self.training_detail_label.setObjectName("hint")
        training_metrics = QFrame()
        training_metrics.setObjectName("trainingMetrics")
        training_metrics_layout = QGridLayout(training_metrics)
        training_metrics_layout.setContentsMargins(10, 8, 10, 8)
        training_metrics_layout.setSpacing(8)
        self.training_train_loss_label = QLabel("-")
        self.training_val_loss_label = QLabel("-")
        self.training_lr_label = QLabel("-")
        self.training_internal_time_label = QLabel("-")
        for column, (label, value) in enumerate(
            [
                ("Loss treino", self.training_train_loss_label),
                ("Loss validacao", self.training_val_loss_label),
                ("Learning rate", self.training_lr_label),
                ("Tempo Cellpose", self.training_internal_time_label),
            ]
        ):
            title = QLabel(label)
            title.setObjectName("metricTitle")
            value.setObjectName("metricValue")
            training_metrics_layout.addWidget(title, 0, column)
            training_metrics_layout.addWidget(value, 1, column)
        self.training_end_hint_label = QLabel("Fim real: quando a etapa 'Modelo salvo' for marcada e o processo encerrar.")
        self.training_end_hint_label.setObjectName("hint")
        self.training_saved_model_label = QLabel("Modelo salvo em: -")
        self.training_saved_model_label.setObjectName("hint")
        self.training_last_message_label = QLabel("Atualizacao: -")
        self.training_last_message_label.setWordWrap(True)
        self.training_steps_table = QTableWidget(0, 2)
        self.training_steps_table.setHorizontalHeaderLabels(["Etapa", "Status"])
        self.training_steps_table.verticalHeader().setVisible(False)
        self.training_steps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.training_steps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.training_steps_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.training_steps_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.training_steps = [
            ("dados_treino", "Carregar dados de treino"),
            ("dados_validacao", "Carregar dados de validacao"),
            ("inicializar_modelo", "Inicializar modelo"),
            ("treinar", "Treinar modelo"),
            ("modelo_salvo", "Modelo salvo"),
            ("concluido", "Concluido"),
        ]
        self.reset_training_steps()
        progress_layout.addWidget(self.training_status_label)
        progress_layout.addWidget(self.training_model_label)
        progress_layout.addWidget(self.training_elapsed_label)
        progress_layout.addWidget(self.training_epoch_label)
        progress_layout.addWidget(self.training_epoch_progress)
        progress_layout.addWidget(self.training_detail_label)
        progress_layout.addWidget(training_metrics)
        progress_layout.addWidget(self.training_end_hint_label)
        progress_layout.addWidget(self.training_steps_table)
        progress_layout.addWidget(self.training_saved_model_label)
        progress_layout.addWidget(self.training_last_message_label)
        progress_layout.addStretch()
        top_layout.addWidget(progress_box, 1)

        layout.addLayout(top_layout)

        loss_box = self.panel("Grafico de perda")
        loss_layout = QVBoxLayout(loss_box)
        self.loss_plot = LossPlotWidget(self.train_epochs.value())
        self.train_epochs.valueChanged.connect(lambda value: self.loss_plot.reset(value))
        loss_layout.addWidget(self.loss_plot, 1)
        layout.addWidget(loss_box, 1)

    def open_training_dialog(self):
        if self.training_dialog is None:
            self.training_dialog = QDialog(self)
            self.training_dialog.setWindowTitle("Treinar modelo")
            self.training_dialog.resize(1100, 760)
            self.build_train_page(self.training_dialog)
            if not self.config.get("active_model"):
                self.train_model_name.setText(f"cpsam_{self.config['active_project']}_v1")
        self.training_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.training_dialog.show()
        self.training_dialog.raise_()
        self.training_dialog.activateWindow()

    def build_results_page(self, page):
        layout = QHBoxLayout(page)
        layout.setSpacing(12)

        left_column = QVBoxLayout()
        left_column.setSpacing(12)

        model_box = self.panel("Predicao")
        model_layout = QGridLayout(model_box)
        model_layout.setContentsMargins(10, 8, 10, 10)
        model_layout.setHorizontalSpacing(10)
        model_layout.setVerticalSpacing(6)
        self.predict_model_label = QLabel()
        self.predict_model_label.setObjectName("largeText")
        self.pred_input = QLineEdit(self.config["test_images_dir"])
        self.pred_output = QLineEdit(self.config["predictions_dir"])
        self.pred_output.setReadOnly(True)
        self.pred_padding = QSpinBox()
        self.pred_padding.setRange(0, 2048)
        self.pred_padding.setValue(int(self.config["padding_pixels"]))
        self.pred_diameter = QLineEdit(str(self.config["diameter"]))
        self.pred_cellprob = QLineEdit(str(self.config["cellprob_threshold"]))
        self.pred_flow = QLineEdit(str(self.config["flow_threshold"]))
        self.pred_padding.setFixedWidth(82)
        for field in [self.pred_diameter, self.pred_cellprob, self.pred_flow]:
            field.setFixedWidth(86)
        self.results_calibration_label = QLabel("Calibracao: nao definida")
        self.results_calibration_label.setObjectName("hint")

        params_row = QWidget()
        params_layout = QHBoxLayout(params_row)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(8)
        for label, field in [
            ("Padding", self.pred_padding),
            ("Diametro", self.pred_diameter),
            ("Cell prob", self.pred_cellprob),
            ("Flow", self.pred_flow),
        ]:
            params_layout.addWidget(QLabel(label))
            params_layout.addWidget(field)
        params_layout.addStretch()

        self.prediction_model_combo = QComboBox()
        self.prediction_model_combo.currentIndexChanged.connect(self.on_prediction_model_changed)

        model_header = QWidget()
        model_header_layout = QHBoxLayout(model_header)
        model_header_layout.setContentsMargins(0, 0, 0, 0)
        model_header_layout.setSpacing(8)
        model_header_layout.addWidget(self.prediction_model_combo, 1)
        self.add_button(model_header_layout, "Importar modelo", self.import_prediction_model)

        model_layout.addWidget(QLabel("Modelo usado"), 0, 0)
        model_layout.addWidget(model_header, 0, 1)
        model_layout.addWidget(QLabel("Parametros"), 1, 0)
        model_layout.addWidget(params_row, 1, 1)
        model_layout.addWidget(self.results_calibration_label, 2, 1)
        predict_actions = QHBoxLayout()
        self.generate_results_button = self.add_button(predict_actions, "Gerar resultados", self.run_results, primary=True)
        results_menu = QMenu(self.generate_results_button)
        all_images_action = results_menu.addAction("Todas as imagens")
        current_image_action = results_menu.addAction("Imagem atual")
        selected_images_action = results_menu.addAction("Imagens selecionadas")
        missing_outputs_action = results_menu.addAction("Imagens sem resultado")
        all_images_action.triggered.connect(lambda _checked=False: self.run_results())
        current_image_action.triggered.connect(lambda _checked=False: self.run_results_for_current_image())
        selected_images_action.triggered.connect(lambda _checked=False: self.run_results_for_selected_images())
        missing_outputs_action.triggered.connect(lambda _checked=False: self.run_missing_result_outputs())
        self.generate_results_button.setMenu(results_menu)
        view_results_button = self.add_button(predict_actions, "Visualizar resultados", self.open_results_viewer)
        view_results_button.setObjectName("accent")
        predict_actions.addStretch()
        model_layout.addLayout(predict_actions, 3, 1)
        self.result_progress_label = QLabel("Aguardando processo.")
        self.result_progress_label.setObjectName("hint")
        self.result_progress_label.setWordWrap(True)
        self.result_progress_bar = QProgressBar()
        self.result_progress_bar.setRange(0, 100)
        self.result_progress_bar.setValue(0)
        self.result_progress_bar.setFormat("%p%")
        self.result_progress_bar.setTextVisible(True)
        model_layout.addWidget(self.result_progress_label, 4, 1)
        model_layout.addWidget(self.result_progress_bar, 5, 1)
        left_column.addWidget(model_box)

        left = self.panel("Imagens")
        left_layout = QVBoxLayout(left)
        self.result_images_table = QTableWidget(0, 4)
        self.result_images_table.setHorizontalHeaderLabels(["Usar", "Imagem", "Overlay", "Metricas"])
        self.result_images_table.verticalHeader().setVisible(False)
        self.result_images_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_images_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_images_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_images_table.currentCellChanged.connect(
            lambda row, _col, _previous_row, _previous_col: self.show_result_table_row(row)
        )
        self.result_images_table.itemChanged.connect(self.on_result_image_check_changed)
        self.result_images_table.itemSelectionChanged.connect(self.sync_result_checkboxes_from_selection)
        self.result_images_table.horizontalHeader().sectionClicked.connect(self.on_result_images_header_clicked)
        self.last_result_check_row = None
        self.result_images_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.result_images_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_images_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.result_images_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        left_layout.addWidget(self.result_images_table, 1)
        self.results_list_status = QLabel()
        self.results_list_status.setObjectName("hint")
        self.results_list_status.setWordWrap(True)
        left_layout.addWidget(self.results_list_status)
        self.add_button(left_layout, "Recarregar imagens", self.refresh_analysis_images)
        self.add_button(left_layout, "Remover imagem", self.remove_selected_result_image)
        left_column.addWidget(left, 1)
        layout.addLayout(left_column, 0)

        center = self.panel("Visualizador")
        center_layout = QVBoxLayout(center)
        mode_layout = QHBoxLayout()
        self.view_buttons = {}
        for label, mode in [
            ("Original", "original"),
            ("Overlay", "overlay"),
            ("50%+", "overlay_50pct"),
            ("Inteiros", "overlay_inteiros"),
            ("Diametro", "overlay_diametro"),
        ]:
            button = QPushButton(label)
            button.setObjectName("mode")
            button.clicked.connect(lambda checked=False, selected=mode: self.set_view_mode(selected))
            self.view_buttons[mode] = button
            mode_layout.addWidget(button)
        mode_layout.addStretch()
        self.add_button(mode_layout, "Editar mascara", self.open_selected_result_mask_editor)
        self.add_button(mode_layout, "Recalcular metrica", self.run_metrics_for_current_result_image, primary=True)
        center_layout.addLayout(mode_layout)
        self.preview_label = QLabel("Selecione uma imagem.")
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 520)
        center_layout.addWidget(self.preview_label, 1)
        layout.addWidget(center, 1)

    def panel(self, title):
        box = QGroupBox(title)
        box.setObjectName("panel")
        return box

    def metric_card(self, label):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setMinimumHeight(118)
        frame.setMaximumHeight(118)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel(label)
        title.setObjectName("cardTitle")
        divider = QFrame()
        divider.setObjectName("subtleDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        value = QLabel("-")
        value.setObjectName("cardValue")
        value.setWordWrap(True)
        value.setMinimumHeight(64)
        value.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)
        layout.addWidget(divider)
        layout.addWidget(value, 1)
        return frame, value

    def path_field(self, line_edit):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit, 1)
        button = QPushButton("Escolher")
        button.clicked.connect(lambda: self.choose_folder(line_edit))
        layout.addWidget(button)
        return widget

    def add_button(self, layout, text, callback, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

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

    def select_project(self, project_name):
        if not project_name or project_name == self.config.get("active_project"):
            return
        self.reset_project_dependent_state()
        self.config["active_project"] = project_name
        models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
        if models:
            self.config["active_model"] = models[0]
        else:
            self.config["active_model"] = ""
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
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
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
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
            models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
            self.config["active_model"] = models[0] if models else ""
        else:
            self.config["active_project"] = "eucalipto"
            self.config["active_model"] = ""
            ensure_project_structure(active_project_dir(self.config))
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)
        self.refresh_all()

    def run_prepare_dataset(self):
        self.save_dataset_plan_from_table()
        self.run_script(
            "Preparar dataset",
            [
                str(SCRIPTS_DIR / "prepare_dataset.py"),
                "--project-dir",
                str(active_project_dir(self.config)),
                "--plan",
                str(dataset_plan_path(self.config)),
            ],
        )

    def run_training(self):
        model_name = self.train_model_name.text().strip()
        if not model_name:
            QMessageBox.information(self, "Modelo", "Informe um nome para o modelo.")
            return

        self.config["active_model"] = model_name
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)
        args = [
            str(SCRIPTS_DIR / "train_cellpose.py"),
            "--project-dir",
            str(active_project_dir(self.config)),
            "--model-name",
            model_name,
            "--base-model",
            self.train_base_model.text().strip(),
            "--epochs",
            str(self.train_epochs.value()),
            "--learning-rate",
            self.train_learning_rate.text().strip(),
            "--weight-decay",
            self.train_weight_decay.text().strip(),
            "--batch-size",
            str(self.train_batch_size.value()),
            "--require-gpu",
        ]
        self.run_script("Treinar modelo", args)

    def run_results(self, image_stems=None):
        if isinstance(image_stems, bool):
            image_stems = None
        if self.process is not None:
            self.show_process_in_progress()
            return
        if not self.ensure_active_model():
            return
        self.clear_analysis_caches()
        self.save_prediction_config()
        input_dir = project_path(self.config["test_images_dir"], self.config)
        result_entries = self.result_image_entries()
        selected_stems = list(image_stems) if image_stems else None
        args = [
            str(SCRIPTS_DIR / "generate_results.py"),
            "--model",
            str(active_model_path(self.config)),
            "--input",
            str(input_dir),
            "--predictions-output",
            str(predictions_dir(self.config)),
            "--overlays-output",
            str(overlays_dir(self.config)),
            "--padding",
            str(self.config["padding_pixels"]),
            "--diameter",
            str(self.config["diameter"]),
            "--cellprob-threshold",
            str(self.config["cellprob_threshold"]),
            "--flow-threshold",
            str(self.config["flow_threshold"]),
        ]
        if selected_stems:
            image_paths = [result_entries.get(stem, input_dir / f"{stem}.tif") for stem in selected_stems]
            missing = [path.name for path in image_paths if not path.exists()]
            if missing:
                QMessageBox.warning(
                    self,
                    "Gerar resultados",
                    "Algumas imagens selecionadas nao foram encontradas:\n" + "\n".join(missing),
                )
                return
            args.extend(["--images", *[str(path) for path in image_paths]])
        elif result_entries:
            args.extend(["--images", *[str(path) for path in result_entries.values()]])
        self.append_log(
            "\n>>> Imagens enviadas para resultados\n"
            + (
                "\n".join(selected_stems)
                if selected_stems
                else f"Todas as imagens listadas ({len(result_entries)})"
            )
            + "\n"
        )
        self.pending_result_stems = selected_stems
        if list(project_path(self.config["test_masks_dir"], self.config).glob("*_masks.tif")):
            self.pending_actions.extend([self.run_evaluation_then_measurements, self.run_cell_measurements])
        else:
            self.pending_actions.append(self.run_cell_measurements)
        self.run_script("Gerar resultados", args)

    def run_results_for_current_image(self):
        stem = self.current_result_image_stem()
        if not stem:
            QMessageBox.information(self, "Gerar resultados", "Selecione uma imagem na lista.")
            return
        self.run_results_for_stem(stem)

    def run_results_for_stem(self, stem):
        if not stem:
            QMessageBox.information(self, "Gerar resultados", "Selecione uma imagem na lista.")
            return
        self.run_results([stem])

    def run_results_for_selected_images(self):
        stems = self.selected_result_image_stems()
        if not stems:
            QMessageBox.information(self, "Gerar resultados", "Marque uma ou mais imagens na tabela.")
            return
        self.run_results(stems)

    def run_missing_result_outputs(self):
        if self.process is not None:
            self.show_process_in_progress()
            return
        if not self.ensure_active_model():
            return
        self.clear_analysis_caches()
        self.save_prediction_config()
        entries = self.result_image_entries()
        if not entries:
            QMessageBox.information(self, "Gerar resultados", "Nenhuma imagem encontrada para gerar resultados.")
            return

        missing_predictions = [stem for stem in entries if not self.result_prediction_exists(stem)]
        if missing_predictions:
            self.append_log(
                f"\n>>> Gerar resultados faltantes\n"
                f"Imagens sem predicao: {len(missing_predictions)}\n"
            )
            self.run_results(missing_predictions)
            return

        missing_overlay = [stem for stem in entries if not self.result_overlay_exists(stem)]
        missing_metrics = [stem for stem in entries if not self.result_metrics_exists(stem)]

        created_overlays, skipped_overlays = self.create_missing_result_overlays(missing_overlay)
        if missing_metrics:
            self.append_log(
                f"\n>>> Gerar resultados faltantes\n"
                f"Overlays criados: {created_overlays}\n"
                f"Overlays pulados sem predicao: {skipped_overlays}\n"
                f"Imagens sem metricas/medidas: {len(missing_metrics)}\n"
            )
            if list(project_path(self.config["test_masks_dir"], self.config).glob("*_masks.tif")):
                self.pending_result_stems = missing_metrics
                self.pending_actions.extend([self.run_evaluation_then_measurements, self.run_cell_measurements])
            else:
                self.pending_result_stems = missing_metrics
                self.pending_actions.append(self.run_cell_measurements)
            next_action = self.pending_actions.pop(0)
            next_action()
            return

        self.append_log(
            f"\n>>> Gerar resultados faltantes\n"
            f"Overlays criados: {created_overlays}\n"
            f"Overlays pulados sem predicao: {skipped_overlays}\n"
            f"Nenhuma metrica/medida faltante.\n"
        )
        if hasattr(self, "result_progress_label"):
            self.result_progress_label.setText("Resultados faltantes: nada pendente.")
        if hasattr(self, "result_progress_bar"):
            self.result_progress_bar.setRange(0, 100)
            self.result_progress_bar.setValue(100)
            self.result_progress_bar.setFormat("100%")
        self.refresh_all()

    def create_missing_result_overlays(self, image_stems):
        overlays_dir(self.config).mkdir(parents=True, exist_ok=True)
        created = 0
        skipped = 0
        for stem in image_stems:
            image_path = self.result_image_path(stem)
            pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
            if image_path is None or not image_path.exists() or not pred_path.exists():
                skipped += 1
                continue
            base_image = self.load_image_as_rgb(image_path)
            mask = self.load_mask_array(pred_path)
            if mask is None:
                skipped += 1
                continue
            overlay = self.overlay_colored_mask_on_image(base_image, mask)
            overlay_path = overlays_dir(self.config) / f"{stem}_overlay_pred.tif"
            tiff.imwrite(overlay_path, np.asarray(overlay), photometric="rgb")
            created += 1
        return created, skipped

    def open_results_viewer(self):
        dialog = ResultsViewerDialog(self)
        dialog.exec()

    def import_prediction_model(self):
        files, _filter = QFileDialog.getOpenFileNames(
            self,
            "Escolher modelos para importar",
            str(project_models_dir(self.config)),
            "Arquivos de modelo (*.*)",
        )
        if not files:
            return

        target_dir = project_models_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        last_model_name = None
        for file_name in files:
            source_path = Path(file_name)
            if not source_path.is_file():
                continue
            destination_path = target_dir / source_path.name
            if destination_path.exists():
                skipped += 1
                continue
            shutil.copy2(source_path, destination_path)
            copied += 1
            last_model_name = destination_path.name

        if last_model_name:
            self.config["active_model"] = last_model_name
            self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
            self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
            save_config(self.config)

        self.append_log(
            f"\n>>> Importar modelos\n"
            f"Destino: {target_dir}\n"
            f"Copiados: {copied}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        self.refresh_all()

    def import_prediction_images(self):
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = project_path(self.pred_input.text().strip() or self.config["test_images_dir"], self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        converted = 0
        skipped = 0
        errors = []

        image_candidates = {}

        for src in sorted(source_dir.iterdir()):
            if not src.is_file():
                continue
            if src.stem.endswith("_masks") or src.stem.endswith("_pred_mask") or src.name.endswith("_seg.npy"):
                continue

            suffix = src.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}:
                continue

            current = image_candidates.get(src.stem)
            if current is None:
                image_candidates[src.stem] = src
                continue

            current_is_tif = current.suffix.lower() in {".tif", ".tiff"}
            src_is_tif = suffix in {".tif", ".tiff"}
            if src_is_tif and not current_is_tif:
                image_candidates[src.stem] = src

        for src in sorted(image_candidates.values()):
            suffix = src.suffix.lower()
            dst = target_dir / f"{src.stem}.tif"
            if dst.exists():
                skipped += 1
                continue

            if suffix == ".tif":
                shutil.copy2(src, dst)
                copied += 1
                continue

            try:
                if suffix == ".tiff":
                    tiff.imwrite(dst, tiff.imread(src))
                else:
                    with Image.open(src) as image:
                        if image.mode == "P":
                            image = image.convert("RGB")
                        tiff.imwrite(dst, np.asarray(image))
                converted += 1
            except Exception as exc:
                skipped += 1
                errors.append(f"{src}: {exc}")

        self.config["test_images_dir"] = relative_to_project(target_dir, self.config)
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)

        self.append_log(
            f"\n>>> Importar imagens para predicao\n"
            f"Origem: {source_dir}\n"
            f"Destino: {target_dir}\n"
            f"Copiados: {copied}\n"
            f"Convertidos para TIFF: {converted}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        if errors:
            self.show_error(
                "Erro ao importar imagens",
                f"{len(errors)} imagem(ns) nao puderam ser importadas.",
                "\n".join(errors),
            )
        self.refresh_all()

    def run_annotation_mask_prediction(self):
        if self.process is not None:
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
        output_path = image_path.with_name(f"{image_path.stem}_seg.npy")
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

    def run_evaluation(self, image_stems=None):
        if not self.ensure_active_model():
            return
        selected_stems = image_stems if image_stems is not None else self.pending_result_stems
        args = [
            str(SCRIPTS_DIR / "evaluate_cellpose.py"),
            "--masks",
            str(project_path(self.config["test_masks_dir"], self.config)),
            "--predictions",
            str(predictions_dir(self.config)),
            "--output-csv",
            str(metrics_csv_path(self.config)),
        ]
        if selected_stems:
            args.extend(["--images", *selected_stems])
        self.run_script("Avaliar modelo", args)

    def run_evaluation_then_measurements(self):
        self.auto_measure_after_evaluation = True
        self.run_evaluation(self.pending_result_stems)

    def run_cell_measurements(self, image_stems=None):
        self.auto_measure_after_evaluation = False
        if not self.ensure_active_model():
            return
        selected_stems = image_stems if image_stems is not None else self.pending_result_stems
        args = [
            str(SCRIPTS_DIR / "measure_cells.py"),
            "--masks-dir",
            str(predictions_dir(self.config)),
            "--output-dir",
            str(model_outputs_dir(self.config)),
            "--pattern",
            "*_pred_masks.tif",
        ]
        if selected_stems:
            args.extend(["--images", *selected_stems])
        unit, unit_per_pixel = self.calibration()
        if unit_per_pixel > 0:
            args.extend(["--unit", unit, "--unit-per-pixel", str(unit_per_pixel)])
        self.run_script("Gerar CSVs de medidas", args)

    def run_metrics_for_current_result_image(self):
        stem = self.current_result_image_stem()
        if not stem:
            QMessageBox.information(self, "Recalcular metrica", "Selecione uma imagem na lista.")
            return
        self.run_metrics_for_result_image(stem, interactive=True)

    def run_metrics_for_result_image(self, stem, interactive=False):
        if self.process is not None:
            if interactive:
                self.show_process_in_progress()
            elif hasattr(self, "result_progress_label"):
                self.result_progress_label.setText(
                    f"Mascara salva para {stem}, mas ha um processo em andamento. Recalcule depois."
                )
            return False
        if not self.result_prediction_exists(stem):
            if interactive:
                QMessageBox.information(
                    self,
                    "Recalcular metrica",
                    "Esta imagem ainda nao tem mascara de predicao para recalcular.",
                )
            return False

        self.pending_actions.clear()
        self.pending_result_stems = [stem]
        if (project_path(self.config["test_masks_dir"], self.config) / f"{stem}_masks.tif").exists():
            self.pending_actions.extend([self.run_evaluation_then_measurements, self.run_cell_measurements])
        else:
            self.pending_actions.append(self.run_cell_measurements)
        next_action = self.pending_actions.pop(0)
        next_action()
        return True

    def save_prediction_config(self):
        self.config["test_images_dir"] = self.pred_input.text().strip()
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.config["padding_pixels"] = self.pred_padding.value()
        self.config["diameter"] = self.parse_float(self.pred_diameter.text(), 0.0)
        self.config["cellprob_threshold"] = self.parse_float(self.pred_cellprob.text(), 0.0)
        self.config["flow_threshold"] = self.parse_float(self.pred_flow.text(), 0.4)
        save_config(self.config)

    def save_annotation_prediction_config(self):
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

    def ensure_active_model(self):
        if self.config.get("active_model") and active_model_path(self.config).exists():
            return True
        QMessageBox.information(
            self,
            "Modelo nao selecionado",
            "Este projeto ainda nao tem um modelo ativo. Treine um modelo ou selecione um modelo existente antes de continuar.",
        )
        return False

    def run_script(self, title, args):
        if self.process is not None:
            self.show_process_in_progress()
            return False

        self.current_process_title = title
        self.current_process_error = ""
        if title == "Gerar resultados":
            self.runtime_overlay_ready_stems.clear()
            self.runtime_metrics_ready_stems.clear()
        if title == "Treinar modelo":
            self.start_training_progress()
        if title in self.result_process_titles:
            self.start_result_progress(title)
        self.append_log(f"\n>>> {title}\n")
        self.append_log(" ".join([sys.executable, "-u", *args]) + "\n")

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_DIR))
        self.process.setProgram(sys.executable)
        if getattr(sys, "frozen", False):
            self.process.setArguments(["--run-script", *args])
        else:
            self.process.setArguments(["-u", *args])
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.readyReadStandardError.connect(self.read_process_output)
        self.process.errorOccurred.connect(self.process_error_occurred)
        self.process.finished.connect(self.process_finished)
        self.process.start()
        if title != "Criar mascara" and title not in self.result_process_titles:
            self.refresh_all()
        return True

    def read_process_output(self):
        if self.process is None:
            return
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if output:
            self.append_log(output)
            self.capture_process_error(output)
            self.update_training_last_message(output)
            self.update_result_progress(output)
            self.update_result_status_from_output(output)
        if error:
            self.append_log(error)
            self.capture_process_error(error)
            self.update_training_last_message(error)
            self.update_result_progress(error)
            self.update_result_status_from_output(error)

    def process_finished(self, exit_code):
        self.append_log(f">>> Finalizado com codigo {exit_code}\n")
        finished_title = self.current_process_title
        if self.current_process_title in self.result_process_titles:
            self.clear_analysis_caches()
            self.finish_result_progress(exit_code)
        if self.current_process_title == "Treinar modelo":
            self.finish_training_progress(exit_code)
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
        self.process = None
        self.current_process_title = ""
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

    def process_error_occurred(self, error):
        if self.process is None:
            return
        error_message = self.process.errorString()
        self.current_process_error = error_message
        self.append_log(f">>> Erro no processo: {error_message}\n")
        if error != QProcess.ProcessError.FailedToStart:
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
        self.pending_actions.clear()
        self.runtime_overlay_ready_stems.clear()
        self.runtime_metrics_ready_stems.clear()
        self.pending_result_stems = None
        title = self.current_process_title or "Processo"
        self.process = None
        self.current_process_title = ""
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
        error_markers = ["Traceback", "Error:", "Exception", "RuntimeError", "FileNotFoundError", "CUDA out of memory"]
        if any(marker in text for marker in error_markers):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                self.current_process_error = "\n".join(lines[-8:])

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

    def start_result_progress(self, title):
        if not hasattr(self, "result_progress_bar"):
            return
        self.result_progress_bar.setRange(0, 100)
        self.result_progress_bar.setValue(0)
        self.result_progress_label.setText(f"{title}: iniciando.")

    def update_result_progress(self, text):
        if self.current_process_title not in self.result_process_titles:
            return
        if not hasattr(self, "result_progress_bar"):
            return
        for line in text.splitlines():
            match = re.match(r"^PROGRESS\s+(\d+)\s+(\d+)\s*(.*)$", line.strip())
            if not match:
                continue
            current = int(match.group(1))
            total = max(1, int(match.group(2)))
            detail = match.group(3).strip()
            self.result_progress_bar.setRange(0, total)
            self.result_progress_bar.setValue(min(current, total))
            self.result_progress_bar.setFormat(f"{current}/{total}")
            if detail:
                self.result_progress_label.setText(detail)

    def update_result_status_from_output(self, text):
        if self.current_process_title not in self.result_process_titles:
            return
        if not hasattr(self, "result_images_table"):
            return
        for line in text.splitlines():
            stem = self.result_status_stem_from_line(line)
            if not stem:
                continue
            if "Overlay salvo:" in line or "Resultados:" in line:
                self.runtime_overlay_ready_stems.add(stem)
            if self.current_process_title in {"Avaliar modelo", "Gerar CSVs de medidas"}:
                self.runtime_metrics_ready_stems.add(stem)
            self.update_result_status_row(stem)

    def result_status_stem_from_line(self, line):
        line = line.strip()
        if not line:
            return None
        if "Overlay salvo:" in line:
            return self.stem_from_result_path(line.split("Overlay salvo:", 1)[1].strip(), "_overlay_pred")
        if "Predicao salva:" in line:
            return self.stem_from_result_path(line.split("Predicao salva:", 1)[1].strip(), "_pred_masks")

        progress_match = re.match(r"^PROGRESS\s+\d+\s+\d+\s+Resultados:\s+(.+)$", line)
        if progress_match:
            return Path(progress_match.group(1).strip()).stem

        metrics_match = re.match(r"^METRICS\s+(.+)$", line)
        if metrics_match:
            return metrics_match.group(1).strip()

        measurements_match = re.match(r"^MEASUREMENTS\s+(.+)$", line)
        if measurements_match:
            return measurements_match.group(1).strip()
        return None

    def stem_from_result_path(self, text, suffix):
        stem = Path(text).stem
        return stem[: -len(suffix)] if stem.endswith(suffix) else stem

    def update_result_status_row(self, stem):
        row = self.result_table_row_for_stem(stem)
        if row < 0:
            return
        self.result_images_table.blockSignals(True)
        overlay_item = self.result_status_item(self.result_overlay_exists(stem))
        overlay_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_images_table.setItem(row, 2, overlay_item)
        metrics_item = self.result_status_item(self.result_metrics_exists(stem))
        metrics_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_images_table.setItem(row, 3, metrics_item)
        self.result_images_table.blockSignals(False)

    def finish_result_progress(self, exit_code):
        if not hasattr(self, "result_progress_bar"):
            return
        if exit_code == 0:
            maximum = self.result_progress_bar.maximum()
            self.result_progress_bar.setValue(maximum)
            self.result_progress_bar.setFormat("100%")
            self.result_progress_label.setText(f"{self.current_process_title}: concluido.")
        else:
            self.result_progress_label.setText(f"{self.current_process_title}: erro.")

    def reset_training_steps(self):
        self.training_step_states = {key: "Pendente" for key, _label in self.training_steps}
        self.training_steps_table.setRowCount(len(self.training_steps))
        for row, (key, label) in enumerate(self.training_steps):
            self.training_steps_table.setItem(row, 0, QTableWidgetItem(label))
            self.training_steps_table.setItem(row, 1, QTableWidgetItem(self.training_step_states[key]))
        self.training_steps_table.resizeColumnsToContents()

    def set_training_step(self, key, state):
        if key not in getattr(self, "training_step_states", {}):
            return
        self.training_step_states[key] = state
        for row, (step_key, _label) in enumerate(self.training_steps):
            if step_key == key:
                self.training_steps_table.setItem(row, 1, QTableWidgetItem(state))
                break

    def complete_previous_training_steps(self, current_key):
        order = [key for key, _label in self.training_steps]
        if current_key not in order:
            return
        for key in order[: order.index(current_key)]:
            if self.training_step_states.get(key) in ["Pendente", "Em andamento"]:
                self.set_training_step(key, "Concluido")

    def start_training_progress(self):
        self.training_start_time = time.time()
        self.reset_training_steps()
        self.loss_plot.reset(self.train_epochs.value())
        self.training_status_label.setText("Treinando...")
        self.training_model_label.setText(f"Modelo: {self.train_model_name.text().strip()}")
        self.training_epoch_progress.setRange(0, self.train_epochs.value())
        self.training_epoch_progress.setValue(0)
        self.training_epoch_label.setText(f"Epocas: 0/{self.train_epochs.value()}")
        self.training_detail_label.setText("Detalhes: preparando dados e inicializando o treino")
        self.training_train_loss_label.setText("-")
        self.training_val_loss_label.setText("-")
        self.training_lr_label.setText("-")
        self.training_internal_time_label.setText("-")
        self.training_saved_model_label.setText("Modelo salvo em: -")
        self.training_last_message_label.setText("Atualizacao: iniciando treino")
        self.training_timer.start(1000)
        self.update_training_elapsed()

    def finish_training_progress(self, exit_code):
        self.training_timer.stop()
        if exit_code == 0:
            self.training_epoch_progress.setValue(self.train_epochs.value())
            self.training_epoch_label.setText(f"Epocas: {self.train_epochs.value()}/{self.train_epochs.value()}")
            self.training_detail_label.setText("Detalhes: treino concluido e modelo salvo")
            self.training_last_message_label.setText("Atualizacao: treinamento concluido com sucesso")
            self.complete_previous_training_steps("concluido")
            self.set_training_step("concluido", "Concluido")
            self.training_status_label.setText("Treino concluido.")
        else:
            for key, state in self.training_step_states.items():
                if state == "Em andamento":
                    self.set_training_step(key, "Erro")
                    break
            self.training_detail_label.setText(self.friendly_error_message())
            self.training_last_message_label.setText("Atualizacao: consulte o log para os detalhes tecnicos")
            self.training_status_label.setText("Treino finalizado com erro.")
        self.update_training_elapsed()

    def update_training_elapsed(self):
        if self.training_start_time is None:
            return
        elapsed = int(time.time() - self.training_start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        self.training_elapsed_label.setText(f"Tempo decorrido: {hours:02d}:{minutes:02d}:{seconds:02d}")

    def update_training_last_message(self, text):
        if self.current_process_title != "Treinar modelo":
            return
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return
        for line in lines:
            event = parse_training_log_line(line, self.friendly_error_message)
            if event:
                self.apply_training_event(event)

    def apply_training_event(self, event):
        event_type = event["type"]
        if event_type == "epoch":
            self.update_training_epoch(event)
        elif event_type == "stage":
            self.update_training_stage(event)
        elif event_type == "model_saved":
            self.complete_previous_training_steps("modelo_salvo")
            self.set_training_step("treinar", "Concluido")
            self.set_training_step("modelo_salvo", "Concluido")
            self.training_saved_model_label.setText(f"Modelo salvo em: {event['path']}")
            self.training_status_label.setText("Modelo salvo")
            self.training_detail_label.setText("Detalhes: modelo salvo; aguardando encerramento do processo")
            self.training_last_message_label.setText("Atualizacao: modelo salvo com sucesso")
        elif event_type == "detail":
            self.training_detail_label.setText(f"Detalhes: {event['text']}")
            self.training_last_message_label.setText("Atualizacao: informacao do treino recebida")
        elif event_type == "internal_progress":
            self.training_detail_label.setText("Detalhes: etapa interna do Cellpose concluida")
            self.training_last_message_label.setText("Atualizacao: Cellpose concluiu uma subetapa interna")
        elif event_type == "error":
            self.training_detail_label.setText(event["text"])
            self.training_last_message_label.setText("Atualizacao: erro detectado durante o treino")

    def update_training_epoch(self, event):
        epoch = event["epoch"]
        total_epochs = self.train_epochs.value()
        visible_epoch = min(epoch, total_epochs)
        train_loss = self.parse_optional_float(event["train_loss"])
        val_loss = self.parse_optional_float(event["val_loss"])
        self.training_epoch_progress.setValue(visible_epoch)
        self.training_epoch_label.setText(f"Epocas: {visible_epoch}/{total_epochs}")
        self.training_train_loss_label.setText(event["train_loss"])
        self.training_val_loss_label.setText(event["val_loss"])
        self.training_lr_label.setText(event["lr"])
        self.training_internal_time_label.setText(f"{event['cellpose_time']}s")
        self.complete_previous_training_steps("treinar")
        self.set_training_step("treinar", "Em andamento")
        self.training_status_label.setText(f"Treinando rede: epoca {visible_epoch}/{total_epochs}")
        self.training_detail_label.setText(
            f"Detalhes: epoca {visible_epoch} concluida; loss treino {event['train_loss']} e validacao {event['val_loss']}"
        )
        self.training_last_message_label.setText("Atualizacao: metricas da epoca atualizadas")
        self.loss_plot.add_point(event["plot_epoch"], train_loss, val_loss)

    def parse_optional_float(self, value):
        try:
            return float(value)
        except ValueError:
            return None

    def update_training_stage(self, event):
        key = event["key"]
        self.complete_previous_training_steps(key)
        if key == "concluido":
            self.set_training_step("modelo_salvo", "Concluido")
            self.set_training_step("concluido", "Concluido")
            self.training_status_label.setText("Treinamento finalizado")
            self.training_detail_label.setText("Detalhes: finalizando arquivos do treino")
        else:
            self.set_training_step(key, "Em andamento")
            self.training_status_label.setText(event["title"])
            self.training_detail_label.setText(f"Detalhes: {event['title'].lower()}")
        self.training_last_message_label.setText(f"Atualizacao: {event['title'].lower()}")

    def friendly_error_message(self, message=None):
        text = message or self.current_process_error
        lowered = text.lower()
        if "gpu obrigatoria" in lowered or "cuda" in lowered and "not detect" in lowered:
            return "Detalhes: GPU nao detectada ou indisponivel para o treino"
        if "nenhuma imagem de treino valida" in lowered:
            return "Detalhes: nenhuma imagem valida de treino foi encontrada"
        if "out of memory" in lowered:
            return "Detalhes: memoria da GPU insuficiente para este treino"
        return "Detalhes: falha durante o treinamento; veja o log bruto para detalhes"

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

    def refresh_dataset_import(self):
        if not hasattr(self, "dataset_pairs_table"):
            return

        input_dir = conversion_input_dir(self.config)
        input_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "conversion_input_label"):
            self.conversion_input_label.setText(str(input_dir))

        selected_image = self.pending_annotation_image_name
        if selected_image is None and self.dataset_pairs_table.currentRow() >= 0:
            current_item = self.dataset_pairs_table.item(self.dataset_pairs_table.currentRow(), 2)
            if current_item is not None:
                selected_image = current_item.text()

        plan = self.load_dataset_plan()
        all_rows = self.scan_conversion_input()
        rows = all_rows
        image_count = len(all_rows)
        valid_count = sum(1 for row in all_rows if row["status"] == "OK")
        missing_count = sum(1 for row in all_rows if row["status"] == "Sem mascara")
        invalid_count = image_count - valid_count - missing_count
        seg_count = len(list(input_dir.glob("*_seg.npy")))
        tif_mask_count = len(list(input_dir.glob("*_masks.tif"))) + len(list(input_dir.glob("*_masks.tiff")))
        selected_count = sum(
            1
            for row in rows
            if row["status"] in {"OK", "Sem mascara"} and plan.get(row["image"], {}).get("include", True)
        )

        self.dataset_validation_summary.setText(
            f"Imagens: {image_count}\n"
            f"Mascaras: {seg_count + tif_mask_count}\n"
            f"Pares validos: {valid_count}\n"
            f"Selecionadas: {selected_count}\n"
            f"Sem mascara: {missing_count}\n"
            f"Mascaras invalidas: {invalid_count}"
        )

        self.dataset_pairs_table.blockSignals(True)
        self.dataset_pairs_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            saved = plan.get(row["image"], {})
            can_include = row["status"] in {"OK", "Sem mascara"}
            include = can_include and (row["status"] == "Sem mascara" or saved.get("include", True))
            group = "test" if row["status"] == "Sem mascara" else saved.get("group", "auto")

            include_item = QTableWidgetItem()
            include_item.setFlags(include_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if not can_include:
                include_item.setFlags(include_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            include_item.setCheckState(Qt.CheckState.Checked if include else Qt.CheckState.Unchecked)
            include_item.setData(Qt.ItemDataRole.UserRole, row)
            self.dataset_pairs_table.setItem(row_index, 0, include_item)

            group_combo = QComboBox()
            group_options = [
                ("auto", "Auto"),
                ("train", "Treino"),
                ("val", "Validacao"),
                ("test", "Teste"),
            ]
            for key, label in group_options:
                group_combo.addItem(label, key)
            group_index = group_combo.findData(group)
            group_combo.setCurrentIndex(group_index if group_index >= 0 else 0)
            group_combo.setEnabled(row["status"] == "OK")
            group_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            group_combo.currentIndexChanged.connect(
                lambda _index, selected_row=row_index: self.on_dataset_group_changed(selected_row)
            )
            self.dataset_pairs_table.setCellWidget(row_index, 1, group_combo)

            values = [row["image"], row["segmentation"], row["status"]]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.dataset_pairs_table.setItem(row_index, col + 2, item)
            self.dataset_pairs_table.setRowHeight(row_index, 30)
        self.dataset_pairs_table.blockSignals(False)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        if rows:
            selected_row = 0
            if selected_image:
                for row_index, row in enumerate(rows):
                    if row["image"] == selected_image:
                        selected_row = row_index
                        break
            self.dataset_pairs_table.selectRow(selected_row)
            self.show_selected_dataset_pair()
        else:
            self.dataset_preview_label.setText("Nenhuma imagem encontrada.")
            self.dataset_preview_label.setPixmap(QPixmap())

    def scan_conversion_input(self):
        input_dir = conversion_input_dir(self.config)
        image_files = []
        for ext in IMAGE_EXTENSIONS:
            image_files.extend(input_dir.glob(f"*{ext}"))

        image_files = sorted(
            path
            for path in image_files
            if not path.stem.endswith("_masks") and not path.stem.endswith("_pred_mask")
        )

        rows = []
        for image_path in image_files:
            seg_path = image_path.with_name(f"{image_path.stem}_seg.npy")
            tif_mask_path = image_path.with_name(f"{image_path.stem}_masks.tif")
            tiff_mask_path = image_path.with_name(f"{image_path.stem}_masks.tiff")
            mask_path = tif_mask_path if tif_mask_path.exists() else tiff_mask_path
            validation = validate_mask_file(seg_path, mask_path)
            has_mask = validation["valid"]
            segmentation = (
                seg_path.name if seg_path.exists()
                else (mask_path.name if mask_path.exists() else "ausente")
            )
            status = validation["status"] if seg_path.exists() or mask_path.exists() else "Sem mascara"
            rows.append(
                {
                    "image": image_path.name,
                    "segmentation": segmentation,
                    "status": "OK" if has_mask else status,
                    "image_path": str(image_path),
                    "seg_path": str(seg_path),
                    "tif_mask_path": str(mask_path),
                    "mask_pixels": validation["pixel_count"],
                    "mask_objects": validation["object_count"],
                }
            )
        return rows

    def load_dataset_plan(self):
        return load_plan(dataset_plan_path(self.config))

    def save_dataset_plan_from_table(self):
        if not hasattr(self, "dataset_pairs_table") or self.dataset_pairs_table.signalsBlocked():
            return
        entries = self.dataset_plan_entries_from_table()
        save_plan(dataset_plan_path(self.config), entries)
        self.update_dataset_selection_summary()

    def on_dataset_group_changed(self, row):
        self.save_dataset_plan_from_table()
        group_combo = self.dataset_pairs_table.cellWidget(row, 1)
        if group_combo and group_combo.currentData() == "test":
            self.run_prepare_dataset()

    def update_dataset_selection_summary(self):
        if not hasattr(self, "dataset_validation_summary"):
            return
        summary = summarize_table_entries(self.dataset_plan_entries_from_table())
        groups = summary["groups"]
        self.dataset_validation_summary.setText(
            f"Imagens: {summary['total']}\n"
            f"Pares validos: {summary['valid']}\n"
            f"Selecionadas: {summary['selected']}\n"
            f"Treino/Val/Teste/Auto: {groups['train']}/{groups['val']}/{groups['test']}/{groups['auto']}\n"
            f"Sem mascara: {summary['problems']}"
        )

    def dataset_plan_entries_from_table(self):
        entries = []
        for row in range(self.dataset_pairs_table.rowCount()):
            include_item = self.dataset_pairs_table.item(row, 0)
            status_item = self.dataset_pairs_table.item(row, 4)
            group_combo = self.dataset_pairs_table.cellWidget(row, 1)
            image_item = self.dataset_pairs_table.item(row, 2)
            if include_item is None or status_item is None or image_item is None:
                continue
            entries.append(
                {
                    "image": image_item.text(),
                    "include": include_item.checkState() == Qt.CheckState.Checked,
                    "group": group_combo.currentData() if group_combo else "auto",
                    "status": status_item.text(),
                }
            )
        return entries

    def auto_split_dataset_table(self):
        assignments = auto_split_indices(self.dataset_plan_entries_from_table())

        self.dataset_pairs_table.blockSignals(True)
        for row, group in assignments.items():
            combo = self.dataset_pairs_table.cellWidget(row, 1)
            if combo:
                index = combo.findData(group)
                if index >= 0:
                    combo.setCurrentIndex(index)
        self.dataset_pairs_table.blockSignals(False)
        self.save_dataset_plan_from_table()
        self.run_prepare_dataset()

    def on_dataset_pair_current_cell_changed(self, current_row, current_column, _previous_row, _previous_column):
        if current_row < 0 or current_column == 1:
            return
        self.show_selected_dataset_pair()

    def show_selected_dataset_pair(self):
        row = self.dataset_pairs_table.currentRow()
        if row < 0:
            return
        item = self.dataset_pairs_table.item(row, 2)
        if item is None:
            return
        row_data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.show_dataset_preview(row_data)
        self.select_dataset_annotation_row(row_data)

    def show_dataset_preview(self, row_data):
        image_path = Path(row_data.get("image_path", ""))
        seg_path = Path(row_data.get("seg_path", ""))
        tif_mask_path = Path(row_data.get("tif_mask_path", ""))
        if not image_path.exists():
            self.dataset_preview_label.setText("Imagem nao encontrada.")
            self.dataset_preview_label.setPixmap(QPixmap())
            return
        try:
            image = Image.open(image_path).convert("RGB")
            mask = None
            if seg_path.exists():
                mask = np.load(seg_path, allow_pickle=True).item().get("masks")
            elif tif_mask_path.exists():
                mask = np.array(Image.open(tif_mask_path))
            if mask is not None and np.max(mask) > 0:
                mask = np.asarray(mask)
                mask_image = Image.fromarray((mask > 0).astype(np.uint8) * 120).resize(image.size)
                color = Image.new("RGBA", image.size, (22, 107, 92, 0))
                color.putalpha(mask_image)
                image = Image.alpha_composite(image.convert("RGBA"), color).convert("RGB")
            self.set_label_pixmap(self.dataset_preview_label, image)
            self.dataset_preview_info.setText(
                f"{image_path.name}\n{row_data.get('status', '')}\nDuplo clique para editar a mascara."
            )
        except Exception as exc:
            self.dataset_preview_label.setText(f"Nao foi possivel carregar preview:\n{exc}")
            self.dataset_preview_label.setPixmap(QPixmap())
            self.show_error(
                "Erro ao carregar preview",
                "Nao foi possivel carregar a imagem de preview.",
                traceback.format_exc(),
            )

    def select_dataset_annotation_row(self, row_data):
        if not hasattr(self, "annotation_page"):
            return
        image_path = Path(row_data.get("image_path", ""))
        if not image_path.exists():
            return
        seg_path = Path(row_data.get("seg_path", ""))
        tif_mask_path = Path(row_data.get("tif_mask_path", ""))
        validation = validate_mask_file(seg_path, tif_mask_path)
        has_mask = validation["valid"]
        target = DatasetMaskTarget(
            path=image_path,
            seg_path=seg_path,
            tif_mask_path=tif_mask_path,
            has_mask=has_mask,
            label="[Com mascara]" if has_mask else "[Sem mascara]",
            window=self,
        )
        self.annotation_page.show_image(target)

    def open_selected_dataset_editor(self):
        row = self.dataset_pairs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Editar mascara", "Selecione uma imagem na tabela.")
            return
        item = self.dataset_pairs_table.item(row, 2)
        if item is None:
            return
        row_data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.select_dataset_annotation_row(row_data)
        self.annotation_page.open_editor()

    def import_dataset_folder(self):
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens e _seg.npy", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = conversion_input_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        converted = 0
        skipped = 0
        errors = []
        image_candidates = {}

        for src in sorted(source_dir.iterdir()):
            if not src.is_file():
                continue

            if src.name.endswith("_seg.npy"):
                dst = target_dir / src.name
                if dst.exists():
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
                continue

            if src.stem.endswith("_masks") or src.stem.endswith("_pred_mask"):
                continue

            if src.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            current = image_candidates.get(src.stem)
            if current is None:
                image_candidates[src.stem] = src
                continue

            current_is_tif = current.suffix.lower() in {".tif", ".tiff"}
            src_is_tif = src.suffix.lower() in {".tif", ".tiff"}
            if src_is_tif and not current_is_tif:
                image_candidates[src.stem] = src

        for src in sorted(image_candidates.values()):
            if src.suffix.lower() in {".tif", ".tiff"}:
                dst = target_dir / src.name
                if dst.exists():
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
                continue

            dst = target_dir / f"{src.stem}.tif"
            if dst.exists():
                skipped += 1
                continue

            try:
                with Image.open(src) as image:
                    if image.mode == "P":
                        image = image.convert("RGB")
                    tiff.imwrite(dst, np.asarray(image))
                converted += 1
            except Exception as exc:
                skipped += 1
                errors.append(f"{src}: {exc}")

        self.append_log(
            f"\n>>> Importar imagens e _seg.npy\n"
            f"Origem: {source_dir}\n"
            f"Destino: {target_dir}\n"
            f"Copiados: {copied}\n"
            f"Convertidos para TIFF: {converted}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        if errors:
            self.show_error(
                "Erro ao importar dataset",
                f"{len(errors)} imagem(ns) nao puderam ser convertidas.",
                "\n".join(errors),
            )
        self.convert_dataset_images_to_tif(target_dir)
        self.refresh_dataset_import()
        self.refresh_project()

    def convert_dataset_images_to_tif(self, folder=None):
        input_dir = Path(folder) if folder else conversion_input_dir(self.config)
        input_dir.mkdir(parents=True, exist_ok=True)

        converted = 0
        skipped = 0
        failed = 0
        errors = []

        for image_path in sorted(input_dir.iterdir()):
            if not image_path.is_file():
                continue
            if image_path.name.endswith("_seg.npy") or image_path.stem.endswith("_masks") or image_path.stem.endswith("_pred_mask"):
                continue

            suffix = image_path.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}:
                continue

            if suffix in {".tif", ".tiff"}:
                skipped += 1
                continue

            tif_path = image_path.with_suffix(".tif")
            if tif_path.exists():
                if image_path.exists():
                    image_path.unlink()
                skipped += 1
                continue

            try:
                with Image.open(image_path) as image:
                    if image.mode == "P":
                        image = image.convert("RGB")
                    tiff.imwrite(tif_path, np.asarray(image))
                image_path.unlink()
                converted += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{image_path}: {exc}")

        self.append_log(
            f"\n>>> Converter para TIFF\n"
            f"Pasta: {input_dir}\n"
            f"Convertidos: {converted}\n"
            f"Ja eram TIFF: {skipped}\n"
            f"Falhas: {failed}\n"
        )
        if errors:
            self.show_error(
                "Erro ao converter para TIFF",
                f"{len(errors)} arquivo(s) nao puderam ser convertidos.",
                "\n".join(errors),
            )

    def refresh_annotation_images(self):
        if hasattr(self, "annotation_page"):
            self.annotation_page.refresh_images()

    def current_annotation_image_path(self):
        return self.annotation_page.current_image_path()

    def set_annotation_view_mode(self, mode):
        self.annotation_page.set_view_mode(mode)

    def refresh_project_models_table(self):
        if not hasattr(self, "project_models_table"):
            return

        models_dir = project_models_dir(self.config)
        models_dir.mkdir(parents=True, exist_ok=True)
        models = sorted(path for path in models_dir.iterdir() if path.is_file())
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
        self.predict_model_label.setText(self.config["active_model"] or "Nenhum modelo selecionado")
        self.pred_input.setText(self.config["test_images_dir"])
        self.pred_output.setText(self.config["predictions_dir"])
        self.pred_padding.setValue(int(self.config["padding_pixels"]))
        self.pred_diameter.setText(str(self.config["diameter"]))
        self.pred_cellprob.setText(str(self.config["cellprob_threshold"]))
        self.pred_flow.setText(str(self.config["flow_threshold"]))
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.pred_output.setText(self.config["predictions_dir"])
        if not self.config.get("active_model") and hasattr(self, "train_model_name"):
            self.train_model_name.setText(f"cpsam_{self.config['active_project']}_v1")
        self.refresh_prediction_model_selector()
        if hasattr(self, "annotation_page"):
            self.annotation_page.sync_from_config(self.config)

    def refresh_prediction_model_selector(self):
        if not hasattr(self, "prediction_model_combo"):
            return

        models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
        self.prediction_model_combo.blockSignals(True)
        self.prediction_model_combo.clear()
        for model_name in models:
            self.prediction_model_combo.addItem(model_name, model_name)

        active_model = self.config.get("active_model") or ""
        index = self.prediction_model_combo.findData(active_model)
        self.prediction_model_combo.setCurrentIndex(index if index >= 0 and models else -1)
        self.prediction_model_combo.blockSignals(False)

    def refresh_home_model_selector(self):
        if not hasattr(self, "home_model_combo"):
            return

        models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
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

    def on_prediction_model_changed(self, _index=None):
        if not hasattr(self, "prediction_model_combo"):
            return
        model_name = self.prediction_model_combo.currentData() or ""
        if not model_name or model_name == self.config.get("active_model"):
            return
        self.set_active_model(model_name)

    def set_active_model(self, model_name):
        if not model_name or model_name == self.config.get("active_model"):
            return
        self.config["active_model"] = model_name
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.clear_analysis_caches()
        save_config(self.config)
        self.refresh_all()

    def refresh_analysis_images(self):
        if not hasattr(self, "result_images_table"):
            return
        self.clear_result_indexes()
        selected = self.current_result_image_stem()
        checked_stems = set(self.checked_result_image_stems())
        entries = self.result_image_entries()
        self.build_result_status_index(entries)
        self.result_row_by_stem = {}
        self.result_images_table.blockSignals(True)
        self.result_images_table.setRowCount(len(entries))
        for row_index, stem in enumerate(entries):
            self.result_row_by_stem[stem] = row_index
            check_item = QTableWidgetItem()
            check_item.setFlags(
                check_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setFlags(check_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            check_item.setCheckState(
                Qt.CheckState.Checked if stem in checked_stems else Qt.CheckState.Unchecked
            )
            self.result_images_table.setItem(row_index, 0, check_item)

            image_item = QTableWidgetItem(stem)
            image_item.setData(Qt.ItemDataRole.UserRole, stem)
            self.result_images_table.setItem(row_index, 1, image_item)

            overlay_item = self.result_status_item(self.result_overlay_exists(stem))
            overlay_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_images_table.setItem(row_index, 2, overlay_item)

            metrics_item = self.result_status_item(self.result_metrics_exists(stem))
            metrics_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_images_table.setItem(row_index, 3, metrics_item)
        self.result_images_table.blockSignals(False)
        if hasattr(self, "results_list_status"):
            self.results_list_status.setText(
                f"{len(entries)} imagem(ns). Linha ativa = Imagem atual; clique em Usar para alternar todas."
            )
        if selected:
            row = self.result_table_row_for_stem(selected)
            if row >= 0:
                self.result_images_table.setCurrentCell(row, 1)
            elif self.result_images_table.rowCount() > 0:
                self.result_images_table.setCurrentCell(0, 1)
            else:
                self.preview_label.setText("Nenhuma imagem encontrada.")
                self.preview_label.setPixmap(QPixmap())
        elif self.result_images_table.rowCount() > 0:
            self.result_images_table.setCurrentCell(0, 1)
        else:
            self.preview_label.setText("Nenhuma imagem encontrada.")
            self.preview_label.setPixmap(QPixmap())

    def show_result_table_row(self, row):
        if row < 0:
            return
        stem = self.result_table_stem(row)
        if stem:
            self.show_analysis_image(stem)

    def on_result_image_check_changed(self, item):
        if item.column() != 0:
            return
        row = item.row()
        state = item.checkState()
        modifiers = QApplication.keyboardModifiers()
        rows = []

        if modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_result_check_row is not None:
            start = min(self.last_result_check_row, row)
            end = max(self.last_result_check_row, row)
            rows = list(range(start, end + 1))
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            rows = sorted({index.row() for index in self.result_images_table.selectedIndexes()})

        if rows:
            self.set_result_rows_checked(rows, state)

        self.last_result_check_row = row

    def set_result_rows_checked(self, rows, state):
        if not hasattr(self, "result_images_table"):
            return
        self.result_images_table.blockSignals(True)
        for row in rows:
            check_item = self.result_images_table.item(row, 0)
            if check_item:
                check_item.setCheckState(state)
        self.result_images_table.blockSignals(False)

    def on_result_images_header_clicked(self, section):
        if section != 0 or not hasattr(self, "result_images_table"):
            return
        total = self.result_images_table.rowCount()
        if total == 0:
            return
        checked = len(self.checked_result_image_stems())
        state = Qt.CheckState.Unchecked if checked > total / 2 else Qt.CheckState.Checked
        self.set_result_rows_checked(range(total), state)

    def sync_result_checkboxes_from_selection(self):
        if not hasattr(self, "result_images_table"):
            return
        selected_rows = sorted({index.row() for index in self.result_images_table.selectedIndexes()})
        if len(selected_rows) <= 1:
            return
        self.set_result_rows_checked(selected_rows, Qt.CheckState.Checked)

    def result_status_item(self, exists):
        item = QTableWidgetItem("✓" if exists else "✖")
        item.setForeground(QColor("#00b341" if exists else "#e00000"))
        item.setText("OK" if exists else "X")
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        return item

    def result_table_stem(self, row):
        if not hasattr(self, "result_images_table") or row < 0:
            return None
        item = self.result_images_table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def result_table_row_for_stem(self, stem):
        if not hasattr(self, "result_images_table"):
            return -1
        cached_row = getattr(self, "result_row_by_stem", {}).get(stem)
        if cached_row is not None:
            return cached_row
        for row in range(self.result_images_table.rowCount()):
            if self.result_table_stem(row) == stem:
                return row
        return -1

    def checked_result_image_stems(self):
        if not hasattr(self, "result_images_table"):
            return []
        stems = []
        for row in range(self.result_images_table.rowCount()):
            check_item = self.result_images_table.item(row, 0)
            stem = self.result_table_stem(row)
            if stem and check_item and check_item.checkState() == Qt.CheckState.Checked:
                stems.append(stem)
        return stems

    def open_selected_result_mask_editor(self):
        stem = self.current_result_image_stem()
        if not stem:
            QMessageBox.information(self, "Editar mascara", "Selecione uma imagem na lista de resultados.")
            return
        image_path = self.result_image_path(stem)
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if image_path is None or not image_path.exists():
            QMessageBox.information(self, "Editar mascara", "Imagem original nao encontrada.")
            return
        if not pred_path.exists():
            QMessageBox.information(
                self,
                "Editar mascara",
                "Mascara de predicao nao encontrada. Gere resultados para esta imagem antes de editar.",
            )
            return

        target = ResultMaskTarget(
            path=image_path,
            tif_mask_path=pred_path,
            stem=stem,
            window=self,
            prediction_callback=lambda image_stem=stem: self.run_results_for_stem(image_stem),
        )
        self.annotation_page.show_image(target)
        self.annotation_page.open_editor()

    def on_result_mask_saved(self, stem, mask, recalculate=False):
        self.clear_analysis_caches()
        self.create_result_overlay(stem, mask)
        removed_rows = self.invalidate_result_metrics(stem)
        self.runtime_metrics_ready_stems.discard(stem)
        self.update_result_status_row(stem)
        self.refresh_analysis_metrics()
        self.refresh_measurement_tables()
        self.show_analysis_image(stem)
        if hasattr(self, "result_progress_label"):
            self.result_progress_label.setText(
                f"Mascara editada para {stem}. Recalculando metricas..."
                if recalculate
                else f"Mascara editada para {stem}. Metrica invalidada; use Recalcular metrica."
            )
        self.append_log(
            f"\n>>> Mascara de resultado editada\n"
            f"Imagem: {stem}\n"
            f"Overlay atualizado: sim\n"
            f"CSVs invalidados: {removed_rows}\n"
        )
        if recalculate:
            QTimer.singleShot(0, lambda image_stem=stem: self.run_metrics_for_result_image(image_stem))

    def create_result_overlay(self, stem, mask=None):
        image_path = self.result_image_path(stem)
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if image_path is None or not image_path.exists():
            return False
        if mask is None:
            if not pred_path.exists():
                return False
            mask = self.load_mask_array(pred_path)
        if mask is None:
            return False
        overlays_dir(self.config).mkdir(parents=True, exist_ok=True)
        base_image = self.load_image_as_rgb(image_path)
        overlay = self.overlay_colored_mask_on_image(base_image, mask)
        overlay_path = overlays_dir(self.config) / f"{stem}_overlay_pred.tif"
        tiff.imwrite(overlay_path, np.asarray(overlay), photometric="rgb")
        self.runtime_overlay_ready_stems.add(stem)
        return True

    def invalidate_result_metrics(self, stem):
        removed = 0
        removed += self.remove_rows_from_csv(metrics_csv_path(self.config), "image", stem)
        removed += self.remove_rows_from_csv(cell_counts_csv_path(self.config), "filename", stem)
        removed += self.remove_rows_from_csv(cell_measurements_csv_path(self.config), "filename", stem)
        return removed

    def result_overlay_exists(self, stem):
        if stem in getattr(self, "runtime_overlay_ready_stems", set()):
            return True
        overlay_stems = getattr(self, "result_status_index", {}).get("overlays")
        if overlay_stems is not None:
            return stem in overlay_stems
        return any(
            (overlays_dir(self.config) / f"{stem}_overlay_pred{suffix}").exists()
            for suffix in [".tif", ".tiff"]
        )

    def result_prediction_exists(self, stem):
        prediction_stems = getattr(self, "result_status_index", {}).get("predictions")
        if prediction_stems is not None:
            return stem in prediction_stems
        return any(
            (predictions_dir(self.config) / f"{stem}_pred_masks{suffix}").exists()
            for suffix in [".tif", ".tiff"]
        )

    def result_metrics_exists(self, stem):
        if stem in getattr(self, "runtime_metrics_ready_stems", set()):
            return True
        metric_stems = getattr(self, "result_status_index", {}).get("metrics")
        if metric_stems is not None:
            return stem in metric_stems
        for row in read_metrics(metrics_csv_path(self.config)):
            if row.get("image") == stem:
                return True
        for row in self.load_semicolon_csv(cell_counts_csv_path(self.config))[1:]:
            if row and row[0] == stem:
                return True
        for row in self.load_semicolon_csv(cell_measurements_csv_path(self.config))[1:]:
            if row and row[0] == stem:
                return True
        return False

    def build_result_status_index(self, entries=None):
        overlay_stems = {
            self.stem_from_result_path(path.name, "_overlay_pred")
            for suffix in [".tif", ".tiff"]
            for path in overlays_dir(self.config).glob(f"*_overlay_pred{suffix}")
        }
        overlay_stems.update(getattr(self, "runtime_overlay_ready_stems", set()))

        prediction_stems = {
            self.stem_from_result_path(path.name, "_pred_masks")
            for suffix in [".tif", ".tiff"]
            for path in predictions_dir(self.config).glob(f"*_pred_masks{suffix}")
        }

        metric_stems = set(getattr(self, "runtime_metrics_ready_stems", set()))
        metric_stems.update(row.get("image", "") for row in read_metrics(metrics_csv_path(self.config)))
        metric_stems.update(row[0] for row in self.load_semicolon_csv(cell_counts_csv_path(self.config))[1:] if row)
        metric_stems.update(row[0] for row in self.load_semicolon_csv(cell_measurements_csv_path(self.config))[1:] if row)
        metric_stems.discard("")

        if entries is not None:
            entry_stems = set(entries)
            overlay_stems &= entry_stems
            prediction_stems &= entry_stems
            metric_stems &= entry_stems

        self.result_status_index = {
            "overlays": overlay_stems,
            "predictions": prediction_stems,
            "metrics": metric_stems,
        }

    def result_image_entries(self):
        if self.result_entries_cache is not None:
            return self.result_entries_cache
        entries = {}
        images_dir = project_path(self.config["test_images_dir"], self.config)
        if images_dir.exists():
            for ext in IMAGE_EXTENSIONS:
                for path in sorted(images_dir.glob(f"*{ext}")):
                    if path.stem.endswith("_masks") or path.stem.endswith("_pred_mask") or path.stem.endswith("_pred_masks"):
                        continue
                    entries.setdefault(path.stem, path)

        plan = self.load_dataset_plan()
        for image_path in self.result_conversion_input_images():
            saved = plan.get(image_path.name, {})
            is_prediction_only = not self.result_input_mask_exists(image_path)
            if not is_prediction_only and not saved.get("include", True):
                continue
            is_test_image = is_prediction_only or saved.get("group") == "test"
            if is_test_image:
                entries.setdefault(image_path.stem, image_path)

        self.result_entries_cache = dict(sorted(entries.items()))
        return self.result_entries_cache

    def result_conversion_input_images(self):
        input_dir = conversion_input_dir(self.config)
        image_files = []
        for ext in IMAGE_EXTENSIONS:
            image_files.extend(input_dir.glob(f"*{ext}"))
        return sorted(
            path
            for path in image_files
            if not path.stem.endswith("_masks")
            and not path.stem.endswith("_pred_mask")
            and not path.stem.endswith("_pred_masks")
        )

    def result_input_mask_exists(self, image_path):
        return any(
            image_path.with_name(f"{image_path.stem}{suffix}").exists()
            for suffix in ["_seg.npy", "_masks.tif", "_masks.tiff"]
        )

    def result_image_path(self, stem):
        if not stem:
            return None
        return self.result_image_entries().get(stem)

    def current_result_image_stem(self):
        if not hasattr(self, "result_images_table"):
            return None
        return self.result_table_stem(self.result_images_table.currentRow())

    def selected_result_image_stems(self):
        if not hasattr(self, "result_images_table"):
            return []
        return self.checked_result_image_stems()

    def remove_selected_result_image(self):
        if not hasattr(self, "result_images_table"):
            return

        image_stems = self.selected_result_image_stems()
        if not image_stems:
            QMessageBox.information(self, "Remover imagem", "Marque uma ou mais imagens na tabela de resultados.")
            return

        image_label = image_stems[0] if len(image_stems) == 1 else f"{len(image_stems)} imagens"
        reply = QMessageBox.question(
            self,
            "Remover imagem",
            (
                f"Remover {image_label} da aba de resultados e do conjunto test?\n\n"
                "As imagens de teste, mascaras de teste, predicoes, overlays e linhas dos CSVs "
                "serao movidos para pastas 'removed' quando existirem."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        moved_paths = []
        missing_paths = []
        csv_updates = 0
        for image_stem in image_stems:
            for source_path, removed_dir in self.result_image_removal_targets(image_stem):
                if not source_path.exists():
                    missing_paths.append(source_path)
                    continue
                moved_paths.append(self.move_to_removed_folder(source_path, removed_dir))

            csv_updates += self.remove_rows_from_csv(metrics_csv_path(self.config), "image", image_stem)
            csv_updates += self.remove_rows_from_csv(cell_counts_csv_path(self.config), "filename", image_stem)
            csv_updates += self.remove_rows_from_csv(cell_measurements_csv_path(self.config), "filename", image_stem)

        self.clear_analysis_caches()
        self.preview_label.setText("Selecione uma imagem.")
        self.preview_label.setPixmap(QPixmap())
        self.update_metric_panel(None)
        self.refresh_analysis_images()
        self.refresh_analysis_metrics()
        self.refresh_measurement_tables()
        self.refresh_project()

        self.append_log(
            f"\n>>> Remover imagem dos resultados\n"
            f"Imagens: {', '.join(image_stems)}\n"
            f"Arquivos movidos: {len(moved_paths)}\n"
            f"Arquivos nao encontrados: {len(missing_paths)}\n"
            f"CSVs atualizados: {csv_updates}\n"
        )

    def result_image_removal_targets(self, image_stem):
        project_dir = active_project_dir(self.config)
        test_images_dir = project_path(self.config["test_images_dir"], self.config)
        test_masks_dir = project_dir / "data" / "test" / "masks"
        test_removed_dir = project_dir / "data" / "test" / "removed"
        output_removed_dir = model_outputs_dir(self.config) / "removed"

        targets = []
        for suffix in [".tif", ".tiff", ".png", ".jpg", ".jpeg"]:
            targets.append((test_images_dir / f"{image_stem}{suffix}", test_removed_dir / "images"))
        for suffix in [".tif", ".tiff"]:
            targets.append((test_masks_dir / f"{image_stem}_masks{suffix}", test_removed_dir / "masks"))
            targets.append((predictions_dir(self.config) / f"{image_stem}_pred_masks{suffix}", output_removed_dir / "predictions"))
            targets.append((predictions_dir(self.config) / f"{image_stem}_pred_padded_masks{suffix}", output_removed_dir / "predictions"))
            targets.append((overlays_dir(self.config) / f"{image_stem}_overlay_pred{suffix}", output_removed_dir / "overlays"))
        return targets

    def move_to_removed_folder(self, source_path, removed_dir):
        removed_dir.mkdir(parents=True, exist_ok=True)
        destination = removed_dir / source_path.name
        if destination.exists():
            counter = 1
            while True:
                candidate = removed_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
                if not candidate.exists():
                    destination = candidate
                    break
                counter += 1
        shutil.move(str(source_path), str(destination))
        return destination

    def remove_rows_from_csv(self, path, column_name, image_stem):
        if not path.exists():
            return 0

        with path.open("r", encoding="utf-8-sig", newline="") as file:
            sample = file.read(2048)
            file.seek(0)
            first_line = sample.splitlines()[0] if sample.splitlines() else ""
            delimiter = ";" if ";" in first_line else ","
            rows = list(csv.reader(file, delimiter=delimiter))

        if not rows or column_name not in rows[0]:
            return 0

        column_index = rows[0].index(column_name)
        kept_rows = [rows[0]]
        removed = 0
        for row in rows[1:]:
            if len(row) > column_index and row[column_index] == image_stem:
                removed += 1
            else:
                kept_rows.append(row)

        if removed == 0:
            return 0

        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.writer(file, delimiter=delimiter)
            writer.writerows(kept_rows)
        return 1

    def refresh_analysis_metrics(self):
        self.metrics_by_image = {
            row["image"]: row for row in read_metrics(metrics_csv_path(self.config))
        }
        stem = self.current_result_image_stem() if hasattr(self, "result_images_table") else None
        self.update_metric_panel(stem)

    def refresh_measurement_tables(self):
        if not hasattr(self, "cell_counts_table"):
            return
        counts_path = cell_counts_csv_path(self.config)
        measurements_path = cell_measurements_csv_path(self.config)
        counts_rows = self.load_semicolon_csv(counts_path)
        measurement_rows = self.load_semicolon_csv(measurements_path)
        self.populate_csv_table(self.cell_counts_table, counts_rows)
        self.populate_csv_table(self.cell_measurements_table, measurement_rows)

        if counts_path.exists() and measurements_path.exists():
            self.measurements_status_label.setText(
                f"Contagens: {max(len(counts_rows) - 1, 0)} imagens | "
                f"Medidas: {max(len(measurement_rows) - 1, 0)} objetos"
            )
        else:
            missing = []
            if not counts_path.exists():
                missing.append("cell_counts.csv")
            if not measurements_path.exists():
                missing.append("cell_measurements.csv")
            self.measurements_status_label.setText(
                "Arquivos ainda nao encontrados: " + ", ".join(missing)
            )

    def load_semicolon_csv(self, path):
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.reader(file, delimiter=";"))

    def populate_csv_table(self, table, rows):
        table.setSortingEnabled(False)
        table.clear()
        if not rows:
            table.setRowCount(0)
            table.setColumnCount(0)
            table.setSortingEnabled(True)
            return
        headers = rows[0]
        body = rows[1:]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(body))
        for row_index, row in enumerate(body):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)

    def select_project_model(self):
        if not hasattr(self, "project_models_table"):
            return
        row = self.project_models_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Modelo", "Selecione um modelo na tabela.")
            return
        self.set_active_model(self.project_models_table.item(row, 0).text())

    def show_analysis_image(self, image_stem):
        if not image_stem:
            return
        self.update_metric_panel(image_stem)
        image = self.analysis_preview_image(image_stem, self.current_view_mode)
        if image is not None:
            self.set_analysis_preview_pixmap(image_stem, self.current_view_mode, image)
            QTimer.singleShot(0, lambda stem=image_stem: self.preload_fast_result_views(stem))
            return

        if self.current_view_mode in {"overlay", "overlay_50pct", "overlay_inteiros", "overlay_diametro"}:
            image_path = self.analysis_image_path(image_stem, "original")
            if image_path is not None and image_path.exists():
                self.show_image_file(image_path)
            else:
                self.preview_label.setText("Imagem ou predicao nao encontrada para este modo.")
                self.preview_label.setPixmap(QPixmap())
            return

        image_path = self.analysis_image_path(image_stem, self.current_view_mode)
        if image_path is None or not image_path.exists():
            self.preview_label.setText("Arquivo nao encontrado para este modo.")
            self.preview_label.setPixmap(QPixmap())
            return
        self.show_image_file(image_path)

    def analysis_preview_image(self, stem, mode):
        cache_key = self.analysis_render_cache_key(stem, mode)
        if cache_key is None:
            return None
        if cache_key not in self.analysis_render_cache:
            if mode == "original":
                image_path = self.analysis_image_path(stem, mode)
                if image_path is None or not image_path.exists():
                    return None
                image = self.load_image_as_rgb(image_path)
            else:
                image = self.render_measurement_overlay(stem, mode)
                if image is None:
                    return None
            self.analysis_render_cache[cache_key] = image.copy()
        return self.analysis_render_cache[cache_key].copy()

    def preload_fast_result_views(self, stem):
        if stem != self.current_result_image_stem():
            return
        for mode in ["original", "overlay"]:
            image = self.analysis_preview_image(stem, mode)
            if image is not None:
                self.analysis_pixmap_data(stem, mode, image)

    def analysis_render_cache_key(self, stem, mode):
        image_path = self.result_image_path(stem)
        if image_path is None or not image_path.exists():
            return None
        image_key = self.cache_key("image", image_path)
        if mode == "original":
            return "render", stem, mode, image_key
        if mode in {"overlay", "overlay_50pct", "overlay_inteiros", "overlay_diametro"}:
            pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
            if not pred_path.exists():
                return None
            return "render", stem, mode, image_key, self.cache_key("mask", pred_path)
        return None

    def set_analysis_preview_pixmap(self, stem, mode, image):
        pixmap, scale, offset_x, offset_y = self.analysis_pixmap_data(stem, mode, image)
        self.preview_label._display_scale = scale
        self.preview_label._display_offset_x = offset_x
        self.preview_label._display_offset_y = offset_y
        self.preview_label.setPixmap(pixmap)

    def analysis_pixmap_data(self, stem, mode, image):
        render_key = self.analysis_render_cache_key(stem, mode)
        pixmap_key = (
            render_key,
            self.preview_label.width(),
            self.preview_label.height(),
            image.size,
        )
        if pixmap_key not in self.analysis_pixmap_cache:
            image = image.convert("RGB")
            width, height = image.size
            qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
            source_pixmap = QPixmap.fromImage(qimage)
            pixmap = source_pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scale = pixmap.width() / width
            offset_x = (self.preview_label.width() - pixmap.width()) / 2
            offset_y = (self.preview_label.height() - pixmap.height()) / 2
            self.analysis_pixmap_cache[pixmap_key] = (pixmap, scale, offset_x, offset_y)
        return self.analysis_pixmap_cache[pixmap_key]

    def analysis_image_path(self, stem, mode):
        if mode == "original":
            return self.result_image_path(stem)
        return None

    def render_measurement_overlay(self, stem, mode):
        image_path = self.result_image_path(stem)
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if image_path is None or not image_path.exists() or not pred_path.exists():
            return None

        base_image = self.load_image_as_rgb(image_path)
        mask = self.load_mask_array(pred_path)
        if mask is None:
            return None

        if mode == "overlay":
            return self.overlay_colored_mask_on_image(base_image, mask)

        if mode == "overlay_50pct":
            filtered = filtrar_celulas_borda_proporcional(
                mask,
                area_minima=0,
                max_borda_diametro_ratio=1.5,
                borda_expandida=8,
            )
            return self.overlay_colored_mask_on_image(base_image, filtered)

        filtered = build_mask_inteiros(mask)
        image = self.overlay_colored_mask_on_image(base_image, filtered)

        if mode == "overlay_diametro":
            image = self.draw_minor_axes(image, filtered)

        return image

    def load_image_as_rgb(self, path):
        cache_key = self.cache_key("image", path)
        if cache_key not in self.analysis_cache:
            image = Image.open(path)
            array = np.array(image)
            if array.ndim == 2:
                array = normalize_array(array)
                image = Image.fromarray(array).convert("RGB")
            else:
                image = image.convert("RGB")
            self.analysis_cache[cache_key] = image
        return self.analysis_cache[cache_key].copy()

    def load_mask_array(self, path):
        cache_key = self.cache_key("mask", path)
        if cache_key not in self.analysis_cache:
            mask = np.asarray(tiff.imread(path)).astype(np.uint16)
            if mask.ndim > 2:
                mask = np.squeeze(mask)
            if mask.ndim != 2:
                return None
            self.analysis_cache[cache_key] = mask
        return self.analysis_cache[cache_key]

    def clear_analysis_caches(self):
        self.analysis_cache.clear()
        self.analysis_render_cache.clear()
        self.analysis_pixmap_cache.clear()
        self.clear_result_indexes()

    def clear_result_indexes(self):
        self.result_entries_cache = None
        self.result_status_index = {}
        self.result_row_by_stem = {}

    def cache_key(self, kind, path):
        path = Path(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0
        return kind, str(path), mtime

    def overlay_mask_on_image(self, image, mask, color, alpha):
        overlay_alpha = Image.fromarray((np.asarray(mask) > 0).astype(np.uint8) * alpha).resize(image.size)
        color_image = Image.new("RGBA", image.size, (*color, 0))
        color_image.putalpha(overlay_alpha)
        return Image.alpha_composite(image.convert("RGBA"), color_image).convert("RGB")

    def render_colored_id_overlay(self, image, mask, selected_label=None, label_texts=None):
        image = self.overlay_colored_mask_on_image(image, mask, selected_label=selected_label)
        self.draw_mask_ids(image, mask, selected_label=selected_label, label_texts=label_texts)
        return image

    def overlay_colored_mask_on_image(self, image, mask, selected_label=None, alpha=118):
        mask = np.asarray(mask)
        if mask.ndim != 2 or mask.max() == 0:
            return image.convert("RGB")

        if mask.shape[:2] != (image.height, image.width):
            mask_image = Image.fromarray(mask.astype(np.uint16)).resize(image.size, Image.Resampling.NEAREST)
            mask = np.asarray(mask_image)

        base = np.asarray(image.convert("RGB")).astype(np.float32)
        labels = [int(label) for label in np.unique(mask) if int(label) > 0]
        for label_value in labels:
            pixels = mask == label_value
            color = np.array(self.vessel_label_color(label_value), dtype=np.float32)
            blend = alpha / 255.0
            if selected_label and label_value == int(selected_label):
                color = np.array((255, 214, 74), dtype=np.float32)
                blend = 0.72
            base[pixels] = (base[pixels] * (1 - blend)) + (color * blend)

        if selected_label:
            selected_pixels = mask == int(selected_label)
            if selected_pixels.any():
                boundary = find_boundaries(selected_pixels, mode="outer")
                base[boundary] = np.array((255, 255, 255), dtype=np.float32)
                inner_boundary = find_boundaries(selected_pixels, mode="inner")
                base[inner_boundary] = np.array((255, 230, 90), dtype=np.float32)

        return Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))

    def vessel_label_color(self, label_value):
        palette = [
            (230, 92, 58),
            (22, 107, 92),
            (71, 125, 210),
            (174, 92, 179),
            (218, 154, 48),
            (64, 156, 178),
            (122, 144, 57),
            (202, 84, 123),
        ]
        return palette[(int(label_value) - 1) % len(palette)]

    def overlay_id_font(self, image):
        size = max(11, min(22, int(min(image.size) / 42)))
        for font_name in ["arialbd.ttf", "arial.ttf"]:
            try:
                return ImageFont.truetype(font_name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    def draw_mask_ids(self, image, mask, selected_label=None, label_texts=None):
        draw = ImageDraw.Draw(image)
        font = self.overlay_id_font(image)
        selected_label = int(selected_label) if selected_label else None
        for region in regionprops(mask):
            y, x = region.centroid
            label = str(label_texts.get(int(region.label), region.label)) if label_texts else str(region.label)
            fill = (0, 46, 40) if region.label != selected_label else (84, 49, 0)
            stroke = (255, 255, 255)
            draw.text(
                (x + 3, y + 3),
                label,
                fill=fill,
                font=font,
                stroke_width=3,
                stroke_fill=stroke,
            )

    def draw_minor_axes(self, image, mask):
        draw = ImageDraw.Draw(image)
        axes = compute_ellipse_minor_axis_by_label(mask)
        for ellipse in axes.values():
            y1, x1 = ellipse.axis_start_rc
            y2, x2 = ellipse.axis_end_rc
            cy, cx = ellipse.centroid_rc
            draw.line((x1, y1, x2, y2), fill=(255, 235, 59), width=3)
            draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(255, 235, 59))
        return image

    def show_image_file(self, path):
        image = self.load_image_as_rgb(path)
        self.set_label_pixmap(self.preview_label, image)

    def set_label_pixmap(self, label, image):
        image = image.convert("RGB")
        width, height = image.size
        qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
        source_pixmap = QPixmap.fromImage(qimage)
        pixmap = source_pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label._display_scale = pixmap.width() / width
        label._display_offset_x = (label.width() - pixmap.width()) / 2
        label._display_offset_y = (label.height() - pixmap.height()) / 2
        label.setPixmap(pixmap)

    def update_metric_panel(self, image_stem):
        if not getattr(self, "analysis_metric_labels", None):
            return
        row = getattr(self, "metrics_by_image", {}).get(image_stem) if image_stem else None
        values = {
            "Dice": "-",
            "IoU": "-",
            "Precision": "-",
            "Recall": "-",
            "GT objects": "-",
            "Pred objects": "-",
        }
        if row:
            values.update(
                {
                    "Dice": f"{float(row['dice']):.4f}",
                    "IoU": f"{float(row['iou']):.4f}",
                    "Precision": f"{float(row['precision']):.4f}",
                    "Recall": f"{float(row['recall']):.4f}",
                    "GT objects": row["gt_objects"],
                    "Pred objects": row["pred_objects"],
                }
            )
        for key, value in values.items():
            self.analysis_metric_labels[key].setText(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        stem = self.current_result_image_stem() if hasattr(self, "result_images_table") else None
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
