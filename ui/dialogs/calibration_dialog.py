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
    QScrollArea,
    QVBoxLayout,
    QSizePolicy,
)

from services.config import save_config
from services.paths import PROJECT_DIR, active_project_dir
from ui.widgets import AnnotationPreviewLabel, qimage_from_pil


class CalibrationDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.image = None
        self.image_path = None
        self.points = []
        self.current_preview_image = None
        self.current_preview_pixmap = None
        self.zoom = 1.0
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
            wheel_callback=self.zoom_preview,
            draw_button=Qt.MouseButton.LeftButton,
        )
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(320, 240)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.preview_label)
        self.preview_label.pan_button = Qt.MouseButton.RightButton
        self.preview_label.pan_scroll_area = self.scroll_area
        preview_layout.addWidget(self.scroll_area, 1)
        preview_actions = QHBoxLayout()
        window.add_button(preview_actions, "Imagem do projeto", self.open_project_image)
        window.add_button(preview_actions, "Imagem externa", self.open_external_image)
        window.add_button(preview_actions, "Ajustar zoom", self.reset_zoom)
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
        self.unit_per_pixel.setReadOnly(True)
        form.addWidget(QLabel("Unidade"), 0, 0)
        form.addWidget(self.unit_combo, 0, 1)
        form.addWidget(QLabel("Distancia px"), 1, 0)
        form.addWidget(self.pixel_distance, 1, 1)
        form.addWidget(QLabel("Distancia real"), 2, 0)
        form.addWidget(self.real_distance, 2, 1)
        form.addWidget(QLabel("Unidade/px"), 3, 0)
        form.addWidget(self.unit_per_pixel, 3, 1)
        controls_layout.addLayout(form)
        self.pixel_distance.textChanged.connect(self.update_unit_per_pixel)
        self.real_distance.textChanged.connect(self.update_unit_per_pixel)

        hint = QLabel("Clique dois pontos na imagem ou informe os valores manualmente.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        controls_layout.addWidget(hint)

        controls_layout.addStretch()
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
        self.update_unit_per_pixel()

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
        self.reset_zoom()
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
            self.current_preview_image = None
            self.current_preview_pixmap = None
            return
        image = self.image.copy()
        draw = ImageDraw.Draw(image)
        for point in self.points:
            x, y = point
            draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=(255, 214, 74), outline=(0, 46, 40), width=2)
        if len(self.points) == 2:
            draw.line(self.points, fill=(255, 214, 74), width=3)
        self.set_preview_image(image)

    def clear_points(self):
        self.points = []
        self.pixel_distance.clear()
        self.update_preview()

    def parse_float_field(self, field):
        text = field.text().strip().replace(",", ".")
        return float(text) if text else 0.0

    def calculate_unit_per_pixel_value(self):
        pixels = self.parse_float_field(self.pixel_distance)
        real = self.parse_float_field(self.real_distance)
        if pixels <= 0 or real <= 0:
            return 0.0
        return real / pixels

    def update_unit_per_pixel(self):
        try:
            unit_per_pixel = self.calculate_unit_per_pixel_value()
        except ValueError:
            self.unit_per_pixel.clear()
            return
        self.unit_per_pixel.setText(f"{unit_per_pixel:.8g}" if unit_per_pixel > 0 else "")

    def save_calibration(self):
        try:
            unit_per_pixel = self.calculate_unit_per_pixel_value()
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

    def reset_zoom(self):
        self.zoom = 1.0
        self.set_preview_pixmap()

    def zoom_preview(self, delta, source_label=None, x=None, y=None):
        if self.current_preview_image is None:
            return
        point = None
        viewport_x = None
        viewport_y = None
        if source_label is not None and x is not None and y is not None:
            point = self.widget_to_image_xy(source_label, x, y)
            viewport_x = x - self.scroll_area.horizontalScrollBar().value()
            viewport_y = y - self.scroll_area.verticalScrollBar().value()

        factor = 1.15 if delta > 0 else 1 / 1.15
        self.zoom = max(0.2, min(8.0, self.zoom * factor))
        self.set_preview_pixmap()

        if point is not None and viewport_x is not None and viewport_y is not None:
            scale = getattr(self.preview_label, "_display_scale", 1.0)
            self.scroll_area.horizontalScrollBar().setValue(int(point[0] * scale - viewport_x))
            self.scroll_area.verticalScrollBar().setValue(int(point[1] * scale - viewport_y))

    def set_preview_image(self, image):
        self.current_preview_image = image
        qimage = qimage_from_pil(image)
        if qimage is None:
            return
        self.current_preview_pixmap = QPixmap.fromImage(qimage)
        self.set_preview_pixmap()

    def set_preview_pixmap(self):
        if self.current_preview_image is None or self.current_preview_pixmap is None:
            return
        width, height = self.current_preview_image.size
        viewport_size = self.scroll_area.viewport().size()
        fit_scale = min(viewport_size.width() / width, viewport_size.height() / height)
        scale = max(0.05, fit_scale * self.zoom)
        target_width = max(1, int(width * scale))
        target_height = max(1, int(height * scale))
        pixmap = self.current_preview_pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.preview_label.setMinimumSize(pixmap.size())
        self.preview_label.resize(pixmap.size())
        self.preview_label._display_scale = pixmap.width() / width
        self.preview_label._display_offset_x = 0
        self.preview_label._display_offset_y = 0
        self.preview_label.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.zoom == 1.0:
            self.set_preview_pixmap()
