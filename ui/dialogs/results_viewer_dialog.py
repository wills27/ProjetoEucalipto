import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QScrollArea,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from skimage.measure import regionprops
from skimage.segmentation import find_boundaries

from services.metrics import read_metrics
from services.paths import cell_counts_csv_path, cell_measurements_csv_path, metrics_csv_path, predictions_dir
from ui.widgets import AnnotationPreviewLabel, displayed_pixmap_geometry, qimage_from_pil


class ResultsViewerDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.current_stem = None
        self.current_mask = None
        self.current_base_overlay = None
        self.current_preview_image = None
        self.current_preview_pixmap = None
        self.selected_label = None
        self.label_to_cell_id = {}
        self.region_values_by_label = {}
        self.measurements_by_image = {}
        self.zoom = 1.0
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
        self.calibration_label = QLabel(self.calibration_status_text())
        self.calibration_label.setObjectName("hint")
        visual_layout.addWidget(self.calibration_label)
        self.result_preview = AnnotationPreviewLabel(
            self.show_cell_values_at,
            None,
            None,
            wheel_callback=self.zoom_preview,
            draw_button=Qt.MouseButton.LeftButton,
            pan_button=Qt.MouseButton.RightButton,
        )
        self.result_preview.setObjectName("preview")
        self.result_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_preview.setMinimumSize(360, 260)
        self.result_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_scroll_area = QScrollArea()
        self.preview_scroll_area.setWidgetResizable(True)
        self.preview_scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll_area.setWidget(self.result_preview)
        self.result_preview.pan_scroll_area = self.preview_scroll_area
        self.cell_values_table = QTableWidget(0, 2)
        self.cell_values_table.setHorizontalHeaderLabels(["Campo", "Valor"])
        self.cell_values_table.verticalHeader().setVisible(False)
        self.cell_values_table.horizontalHeader().setFixedHeight(28)
        self.cell_values_table.verticalHeader().setDefaultSectionSize(22)
        self.cell_values_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        visual_layout.addWidget(self.preview_scroll_area, 1)
        visual_layout.addWidget(self.cell_values_table, 0)
        self.update_cell_values_table_height()
        self.tabs.addTab(visual_tab, "Visualizacao")

        self.counts_table = self.create_result_table()
        self.measurements_table = self.create_result_table()
        self.metrics_table = self.create_result_table()
        self.tabs.addTab(self.counts_table, "Contagens")
        self.tabs.addTab(self.measurements_table, "Medidas")
        self.tabs.addTab(self.metrics_table, "Metricas")

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
        self.calibration_label.setText(self.calibration_status_text())
        selected = self.image_list.currentItem().text() if self.image_list.currentItem() else None
        self.image_list.clear()
        for stem in self.window.result_image_entries():
            self.image_list.addItem(stem)

        self.load_measurement_index()
        self.window.populate_csv_table(
            self.counts_table,
            self.window.load_semicolon_csv(cell_counts_csv_path(self.window.config)),
        )
        self.window.populate_csv_table(
            self.measurements_table,
            self.window.load_semicolon_csv(cell_measurements_csv_path(self.window.config)),
        )
        self.populate_metrics_table()

        if selected:
            items = self.image_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            if items:
                self.image_list.setCurrentItem(items[0])
                return
        if self.image_list.count() > 0:
            self.image_list.setCurrentRow(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_cell_values_table_height()
        self.set_preview_pixmap()

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
        self.current_base_overlay = None
        self.current_preview_image = None
        self.current_preview_pixmap = None
        self.selected_label = None
        self.label_to_cell_id = {}
        self.region_values_by_label = {}
        self.zoom = 1.0
        image = self.load_result_overlay(image_stem)
        if image is None:
            self.result_preview.setText("Imagem ou predicao nao encontrada.")
            self.result_preview.setPixmap(QPixmap())
            self.clear_cell_values()
            return
        self.set_preview_image(image)
        self.clear_cell_values()

    def load_result_overlay(self, image_stem):
        image_path = self.window.result_image_path(image_stem)
        pred_path = predictions_dir(self.window.config) / f"{image_stem}_pred_masks.tif"
        if image_path is None or not image_path.exists() or not pred_path.exists():
            return None
        base_image = self.window.load_image_as_rgb(image_path)
        mask = self.window.load_mask_array(pred_path)
        if mask is None:
            return None
        self.current_mask = mask
        self.index_mask_regions(mask)
        self.current_base_overlay = self.window.render_colored_id_overlay(
            base_image,
            mask,
            label_texts=self.label_to_cell_id,
        )
        return self.current_base_overlay

    def index_mask_regions(self, mask):
        self.label_to_cell_id = {}
        self.region_values_by_label = {}
        unit, unit_per_pixel = self.window.calibration()
        has_calibration = unit_per_pixel > 0
        for index, region in enumerate(regionprops(mask), start=1):
            label_value = int(region.label)
            self.label_to_cell_id[label_value] = index
            perimeter = getattr(region, "perimeter", None)
            area = float(region.area)
            perimeter_value = float(perimeter) if perimeter is not None else 0.0
            self.region_values_by_label[label_value] = {
                "filename": self.current_stem or "",
                "cell_id": str(index),
                "area_px": f"{area:.3f}",
                "perimeter_px": f"{perimeter_value:.3f}" if perimeter is not None else "",
                "centroid_x": f"{float(region.centroid[1]):.3f}",
                "centroid_y": f"{float(region.centroid[0]):.3f}",
                "area_calibrada": f"{area * (unit_per_pixel ** 2):.3f}" if has_calibration else "",
                "perimeter_calibrado": f"{perimeter_value * unit_per_pixel:.3f}" if has_calibration and perimeter is not None else "",
                "unidade": unit if has_calibration else "",
            }

    def render_selected_overlay(self, label_value=None):
        if self.current_base_overlay is None:
            return None
        if not label_value or self.current_mask is None:
            return self.current_base_overlay
        image = self.current_base_overlay.convert("RGB")
        selected_pixels = self.current_mask == int(label_value)
        if not selected_pixels.any():
            return image
        base = np.asarray(image).copy()
        color = np.array((255, 214, 74), dtype=np.float32)
        pixels = base[selected_pixels].astype(np.float32)
        base[selected_pixels] = np.clip((pixels * 0.28) + (color * 0.72), 0, 255).astype(np.uint8)
        boundary = find_boundaries(selected_pixels, mode="outer")
        base[boundary] = np.array((255, 255, 255), dtype=np.uint8)
        inner_boundary = find_boundaries(selected_pixels, mode="inner")
        base[inner_boundary] = np.array((255, 230, 90), dtype=np.uint8)
        return Image.fromarray(base)

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
            image = self.render_selected_overlay()
            if image is not None:
                self.set_preview_image(image)
            self.clear_cell_values()
            return
        self.selected_label = label_value
        image = self.render_selected_overlay(label_value)
        if image is not None:
            self.set_preview_image(image)
        cell_id = self.label_to_cell_id.get(label_value)
        image_values = self.measurements_by_image.get(self.current_stem, {})
        values = image_values.get(str(cell_id)) or image_values.get(str(label_value))
        if not values:
            values = self.region_values_by_label.get(label_value) or {"cell_id": str(cell_id or label_value)}
        values = self.display_cell_values(values)
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
        self.update_cell_values_table_height()

    def calibration_status_text(self):
        unit, unit_per_pixel = self.window.calibration()
        if unit_per_pixel <= 0:
            return "Calibracao: nao definida"
        return f"Calibracao: {unit_per_pixel:.6g} {unit}/px | Unidade: {unit}"

    def display_cell_values(self, values):
        unit, unit_per_pixel = self.window.calibration()
        has_calibration = unit_per_pixel > 0
        measurement_fields = [
            ("area_calibrada" if has_calibration else "area_px", "Area" if has_calibration else "Area px"),
            (
                "perimeter_calibrado" if has_calibration else "perimeter_px",
                "Perimeter" if has_calibration else "Perimeter px",
            ),
            (
                "diametro_elipse_menor_calibrado" if has_calibration else "diametro_elipse_menor_px",
                "Diametro" if has_calibration else "Diametro px",
            ),
        ]
        ordered_fields = [
            ("filename", "File name"),
            ("cell_id", "Cell ID"),
            *measurement_fields,
            ("centroid_x", "Centroid X"),
            ("centroid_y", "Centroid Y"),
        ]
        handled_keys = {key for key, _label in ordered_fields}
        hidden_keys = {
            "unidade",
            "mask_label",
            "fonte",
            "area_calibrada",
            "area_px",
            "perimeter_calibrado",
            "perimeter_px",
            "diametro_elipse_menor_calibrado",
            "diametro_elipse_menor_px",
        } - handled_keys
        display_values = {}
        for key, label in ordered_fields:
            value = values.get(key, "")
            if has_calibration and key.endswith("_calibrado") and value in (None, ""):
                continue
            display_values[label] = "" if value is None else str(value)

        for key, value in values.items():
            if key in handled_keys or key in hidden_keys:
                continue
            if value in (None, ""):
                continue
            display_values[key] = str(value)
        return display_values

    def widget_to_image_xy(self, source_label, x, y):
        if self.current_mask is None:
            return None
        image_height, image_width = self.current_mask.shape
        scale, offset_x, offset_y = displayed_pixmap_geometry(source_label, image_width, image_height)
        if scale is None or scale == 0:
            return None
        image_x = int((x - offset_x) / scale)
        image_y = int((y - offset_y) / scale)
        if image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
            return None
        return image_x, image_y

    def set_preview_image(self, image):
        qimage = qimage_from_pil(image)
        if qimage is None:
            return
        self.current_preview_image = image
        self.current_preview_pixmap = QPixmap.fromImage(qimage)
        self.set_preview_pixmap()

    def set_preview_pixmap(self):
        if self.current_preview_image is None or self.current_preview_pixmap is None:
            return
        width, height = self.current_preview_image.size
        viewport_size = self.preview_scroll_area.viewport().size()
        fit_scale = min(viewport_size.width() / width, viewport_size.height() / height)
        scale = max(0.05, fit_scale * self.zoom)
        target_width = max(1, int(width * scale))
        target_height = max(1, int(height * scale))
        pixmap = self.current_preview_pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.result_preview.setMinimumSize(pixmap.size())
        self.result_preview.resize(pixmap.size())
        self.result_preview._display_scale = pixmap.width() / width
        self.result_preview._display_offset_x = (self.result_preview.width() - pixmap.width()) / 2
        self.result_preview._display_offset_y = (self.result_preview.height() - pixmap.height()) / 2
        self.result_preview.setPixmap(pixmap)

    def zoom_preview(self, delta, source_label=None, x=None, y=None):
        factor = 1.15 if delta > 0 else 1 / 1.15
        self.zoom_by(factor, source_label, x, y)

    def zoom_by(self, factor, source_label=None, x=None, y=None):
        if self.current_preview_image is None:
            return
        point = None
        viewport_x = None
        viewport_y = None
        if source_label is not None and x is not None and y is not None:
            point = self.widget_to_image_xy(source_label, x, y)
            viewport_x = x - self.preview_scroll_area.horizontalScrollBar().value()
            viewport_y = y - self.preview_scroll_area.verticalScrollBar().value()
        self.zoom = max(0.2, min(8.0, self.zoom * factor))
        self.set_preview_pixmap()
        if point is not None and viewport_x is not None and viewport_y is not None:
            scale = getattr(self.result_preview, "_display_scale", 1.0)
            self.preview_scroll_area.horizontalScrollBar().setValue(int(point[0] * scale - viewport_x))
            self.preview_scroll_area.verticalScrollBar().setValue(int(point[1] * scale - viewport_y))

    def reset_zoom(self):
        self.zoom = 1.0
        self.set_preview_pixmap()

    def clear_cell_values(self):
        self.cell_values_table.setRowCount(0)
        self.update_cell_values_table_height()

    def update_cell_values_table_height(self):
        row_height = self.cell_values_table.verticalHeader().defaultSectionSize()
        header_height = self.cell_values_table.horizontalHeader().height()
        frame_height = self.cell_values_table.frameWidth() * 2
        margin = 18
        visible_rows = 9
        height = header_height + (visible_rows * row_height) + frame_height + margin
        self.cell_values_table.setMinimumHeight(height)
        self.cell_values_table.setMaximumHeight(height)

