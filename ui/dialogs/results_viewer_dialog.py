from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from skimage.measure import regionprops

from services.metrics import read_metrics
from services.paths import cell_counts_csv_path, cell_measurements_csv_path, metrics_csv_path, predictions_dir
from ui.widgets import AnnotationPreviewLabel


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
        self.result_preview.setMinimumSize(360, 260)
        self.result_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
