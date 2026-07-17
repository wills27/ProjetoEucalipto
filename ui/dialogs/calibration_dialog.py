from pathlib import Path

from PIL import ImageDraw
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QApplication,
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
from ui.widgets import AnnotationPreviewLabel, displayed_pixmap_geometry, qimage_from_pil


class CalibrationDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.image = None
        self.image_path = None
        self.points = []
        self.drag_start = None
        self.active_point_index = None
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
            self.start_drag,
            self.drag_move,
            self.finish_drag,
            cancel_callback=self.cancel_drag,
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
        form.addWidget(QLabel("Px/unidade"), 3, 0)
        form.addWidget(self.unit_per_pixel, 3, 1)
        controls_layout.addLayout(form)
        self.pixel_distance.textChanged.connect(self.update_unit_per_pixel)
        self.real_distance.textChanged.connect(self.update_unit_per_pixel)

        hint = QLabel(
            "Clique e arraste na imagem para medir (Shift trava na horizontal/vertical) "
            "ou informe os valores manualmente."
        )
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

    def start_drag(self, source_label, x, y):
        if self.image is None:
            QMessageBox.information(self, "Calibracao", "Abra uma imagem para marcar os pontos.")
            return
        if len(self.points) == 2:
            hit_index = self.hit_test_point(source_label, x, y)
            if hit_index is not None:
                self.active_point_index = hit_index
                self.drag_start = None
                return
        point = self.widget_to_image_xy(source_label, x, y, clamp=True)
        if point is None:
            return
        self.active_point_index = None
        self.drag_start = point
        self.points = [point]
        self.update_preview()

    def drag_move(self, source_label, x, y):
        point = self.widget_to_image_xy(source_label, x, y, clamp=True)
        if point is None:
            return
        if self.active_point_index is not None:
            anchor = self.points[1 - self.active_point_index]
            point = self.apply_shift_lock(anchor, point)
            points = list(self.points)
            points[self.active_point_index] = point
            self.set_current_line(points[0], points[1])
            return
        if self.drag_start is None:
            return
        point = self.apply_shift_lock(self.drag_start, point)
        self.set_current_line(self.drag_start, point)

    def finish_drag(self, source_label, x, y):
        if self.active_point_index is not None:
            point = self.widget_to_image_xy(source_label, x, y, clamp=True)
            if point is not None:
                anchor = self.points[1 - self.active_point_index]
                point = self.apply_shift_lock(anchor, point)
                points = list(self.points)
                points[self.active_point_index] = point
                self.set_current_line(points[0], points[1])
            self.active_point_index = None
            return
        if self.drag_start is None:
            return
        point = self.widget_to_image_xy(source_label, x, y, clamp=True)
        if point is None:
            point = self.points[-1] if len(self.points) == 2 else self.drag_start
        point = self.apply_shift_lock(self.drag_start, point)
        self.set_current_line(self.drag_start, point)
        self.drag_start = None

    def cancel_drag(self):
        self.drag_start = None
        self.active_point_index = None
        self.clear_points()

    def hit_test_point(self, source_label, x, y, tolerance=10):
        if self.image is None or len(self.points) != 2:
            return None
        image_width, image_height = self.image.size
        scale, offset_x, offset_y = displayed_pixmap_geometry(source_label, image_width, image_height)
        for index, point in enumerate(self.points):
            widget_x = point[0] * scale + offset_x
            widget_y = point[1] * scale + offset_y
            if (widget_x - x) ** 2 + (widget_y - y) ** 2 <= tolerance ** 2:
                return index
        return None

    def set_current_line(self, start, end):
        self.points = [start, end]
        distance = self.distance_between_points(start, end)
        self.pixel_distance.setText(f"{distance:.3f}")
        self.update_preview()

    def apply_shift_lock(self, start, current):
        if not QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            return current
        delta_x = current[0] - start[0]
        delta_y = current[1] - start[1]
        if abs(delta_x) >= abs(delta_y):
            return (current[0], start[1])
        return (start[0], current[1])

    def widget_to_image_xy(self, source_label, x, y, clamp=False):
        if self.image is None:
            return None
        image_width, image_height = self.image.size
        scale, offset_x, offset_y = displayed_pixmap_geometry(source_label, image_width, image_height)
        if not scale:
            return None
        image_x = (x - offset_x) / scale
        image_y = (y - offset_y) / scale
        if clamp:
            image_x = min(max(image_x, 0), image_width - 1)
            image_y = min(max(image_y, 0), image_height - 1)
        elif image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
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
            x, y = round(point[0]), round(point[1])
            draw.rectangle((x, y, x, y), fill=(255, 214, 74), outline=(0, 46, 40))
        if len(self.points) == 2:
            draw.line(self.points, fill=(255, 214, 74), width=3)
        self.set_preview_image(image)

    def clear_points(self):
        self.points = []
        self.drag_start = None
        self.active_point_index = None
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

    def calculate_pixels_per_unit_value(self):
        pixels = self.parse_float_field(self.pixel_distance)
        real = self.parse_float_field(self.real_distance)
        if pixels <= 0 or real <= 0:
            return 0.0
        return pixels / real

    def update_unit_per_pixel(self):
        try:
            pixels_per_unit = self.calculate_pixels_per_unit_value()
        except ValueError:
            self.unit_per_pixel.clear()
            return
        self.unit_per_pixel.setText(f"{pixels_per_unit:.8g}" if pixels_per_unit > 0 else "")

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
        self.zoom = max(0.2, min(30.0, self.zoom * factor))
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
