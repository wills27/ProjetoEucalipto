from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QProgressBar,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QSizePolicy,
)

from ui.widgets import AnnotationPreviewLabel, displayed_pixmap_geometry


class AnnotationEditorDialog(QDialog):
    def __init__(
        self,
        parent,
        image_name,
        draw_callbacks,
        delete_object_callback,
        view_callback,
        tool_callback,
        brush_size,
        brush_size_callback,
        prediction_callback,
        save_callback,
        clear_callback,
        undo_callback,
    ):
        super().__init__(parent)
        self.refresh_callback = None
        self.current_image = None
        self.current_pixmap = None
        self.zoom = 1.0
        self.view_callback = view_callback
        self.view_mode = "overlay"
        self.is_busy = False
        self.busy_controls = []

        self.setWindowTitle(f"Editar mascara - {image_name}")
        self.resize(1320, 900)
        self.setModal(True)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        preview_box = self._panel("Mascara")
        preview_layout = QVBoxLayout(preview_box)
        self.preview_label = AnnotationPreviewLabel(
            draw_callbacks["start"],
            draw_callbacks["drag"],
            draw_callbacks["finish"],
            draw_callbacks["cancel"],
            wheel_callback=self.zoom_preview,
            ctrl_left_callback=delete_object_callback,
            draw_button=Qt.MouseButton.RightButton,
        )
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(480, 360)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll_area.setWidget(self.preview_label)
        self.preview_label.pan_button = Qt.MouseButton.LeftButton
        self.preview_label.pan_scroll_area = self.scroll_area
        preview_layout.addWidget(self.scroll_area, 1)
        layout.addWidget(preview_box, 1)

        tools_box = self._panel("Ferramentas")
        tools_layout = QVBoxLayout(tools_box)

        view_row = QHBoxLayout()
        original_button = QPushButton("Original")
        original_button.setObjectName("mode")
        overlay_button = QPushButton("Overlay")
        overlay_button.setObjectName("mode")
        self.view_buttons = {
            "original": original_button,
            "overlay": overlay_button,
        }
        original_button.clicked.connect(lambda: self.set_view_mode("original"))
        overlay_button.clicked.connect(lambda: self.set_view_mode("overlay"))
        self.update_view_buttons()
        self.busy_controls.extend([original_button, overlay_button])
        view_row.addWidget(original_button)
        view_row.addWidget(overlay_button)
        tools_layout.addLayout(view_row)

        contour_button = QPushButton("Contorno")
        eraser_button = QPushButton("Borracha")
        for button in [contour_button, eraser_button]:
            button.setObjectName("mode")
            button.setVisible(False)
        contour_button.clicked.connect(lambda: tool_callback("contour"))
        eraser_button.clicked.connect(lambda: tool_callback("eraser"))
        modal_brush_size = QSpinBox()
        modal_brush_size.setRange(1, 200)
        modal_brush_size.setValue(brush_size)
        modal_brush_size.setVisible(False)
        modal_brush_size.valueChanged.connect(brush_size_callback)
        tool_callback("contour")

        predict_button = QPushButton("Gerar mascara automatica")
        predict_button.clicked.connect(prediction_callback)
        save_button = QPushButton("Salvar mascara")
        save_button.setObjectName("primary")
        save_button.clicked.connect(save_callback)
        clear_button = QPushButton("Limpar mascara")
        clear_button.clicked.connect(clear_callback)
        undo_button = QPushButton("Desfazer")
        undo_button.clicked.connect(undo_callback)
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.accept)
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 0)
        self.busy_progress.setTextVisible(False)
        self.busy_progress.setVisible(False)
        self.busy_controls.extend([predict_button, save_button, clear_button, undo_button, close_button])
        tools_layout.addWidget(predict_button)
        tools_layout.addWidget(save_button)
        tools_layout.addWidget(clear_button)
        tools_layout.addWidget(undo_button)
        tools_layout.addWidget(self.busy_progress)
        tools_layout.addStretch()
        tools_layout.addWidget(close_button)
        layout.addWidget(tools_box, 0)

    def set_busy(self, busy):
        self.is_busy = busy
        self.preview_label.setEnabled(not busy)
        self.busy_progress.setVisible(busy)
        for widget in self.busy_controls:
            widget.setEnabled(not busy)

    def set_view_mode(self, mode):
        self.view_mode = "overlay" if mode == "overlay" else "original"
        self.view_callback(self.view_mode)
        self.update_view_buttons()

    def toggle_overlay(self):
        self.set_view_mode("original" if self.view_mode == "overlay" else "overlay")

    def update_view_buttons(self):
        for mode, button in self.view_buttons.items():
            button.setProperty("active", mode == self.view_mode)
            button.style().unpolish(button)
            button.style().polish(button)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_X and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            self.toggle_overlay()
            event.accept()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event):
        if self.is_busy:
            event.ignore()
            return
        super().closeEvent(event)

    def set_refresh_callback(self, callback):
        self.refresh_callback = callback

    def set_image(self, image):
        self.current_image = image.convert("RGB")
        width, height = self.current_image.size
        qimage = QImage(
            self.current_image.tobytes(),
            width,
            height,
            width * 3,
            QImage.Format.Format_RGB888,
        ).copy()
        self.current_pixmap = QPixmap.fromImage(qimage)
        self._set_preview_pixmap()

    def reset_zoom(self):
        self.zoom = 1.0

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self.refresh_fit_to_view)

    def refresh_fit_to_view(self):
        if self.current_image is None:
            return
        self.reset_zoom()
        if self.refresh_callback:
            self.refresh_callback()
        else:
            self._set_preview_pixmap()

    def zoom_preview(self, delta, source_label=None, x=None, y=None):
        if self.current_image is None:
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
        self._set_preview_pixmap()

        if point is not None and viewport_x is not None and viewport_y is not None:
            scale = getattr(self.preview_label, "_display_scale", 1.0)
            self.scroll_area.horizontalScrollBar().setValue(int(point[0] * scale - viewport_x))
            self.scroll_area.verticalScrollBar().setValue(int(point[1] * scale - viewport_y))

    def widget_to_image_xy(self, source_label, x, y):
        if self.current_image is None:
            return None
        image_width, image_height = self.current_image.size
        scale, offset_x, offset_y = displayed_pixmap_geometry(source_label, image_width, image_height)
        image_x = int((x - offset_x) / scale)
        image_y = int((y - offset_y) / scale)
        if image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
            return None
        return image_x, image_y

    def _set_preview_pixmap(self):
        if self.current_image is None or self.current_pixmap is None:
            return
        width, height = self.current_image.size
        viewport_size = self.scroll_area.viewport().size()
        fit_scale = min(viewport_size.width() / width, viewport_size.height() / height)
        scale = max(0.05, fit_scale * self.zoom)
        target_width = max(1, int(width * scale))
        target_height = max(1, int(height * scale))
        pixmap = self.current_pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
        self.preview_label.setMinimumSize(pixmap.size())
        self.preview_label.resize(pixmap.size())
        self.preview_label._display_scale = pixmap.width() / width
        self.preview_label._display_offset_x = (self.preview_label.width() - pixmap.width()) / 2
        self.preview_label._display_offset_y = (self.preview_label.height() - pixmap.height()) / 2
        self.preview_label.setPixmap(pixmap)

    def _panel(self, title):
        box = QGroupBox(title)
        box.setObjectName("panel")
        return box
