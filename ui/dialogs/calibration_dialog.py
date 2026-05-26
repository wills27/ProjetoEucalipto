from pathlib import Path

from PIL import ImageDraw
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from services.config import save_config
from services.paths import PROJECT_DIR, active_project_dir
from ui.widgets import AnnotationPreviewLabel


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
