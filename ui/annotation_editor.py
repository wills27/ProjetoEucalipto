from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
)

from ui.widgets import AnnotationPreviewLabel


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
        save_callback,
        clear_callback,
        undo_callback,
    ):
        super().__init__(parent)
        self.refresh_callback = None
        self.current_image = None
        self.zoom = 1.0

        self.setWindowTitle(f"Editar mascara - {image_name}")
        self.resize(1180, 820)
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
        self.preview_label.setMinimumSize(860, 720)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(False)
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
        original_button.clicked.connect(lambda: view_callback("original"))
        overlay_button.clicked.connect(lambda: view_callback("overlay"))
        view_row.addWidget(original_button)
        view_row.addWidget(overlay_button)
        tools_layout.addLayout(view_row)

        tool_grid = QGridLayout()
        contour_button = QPushButton("Contorno")
        brush_button = QPushButton("Pincel")
        eraser_button = QPushButton("Borracha")
        for button in [contour_button, brush_button, eraser_button]:
            button.setObjectName("mode")
        contour_button.clicked.connect(lambda: tool_callback("contour"))
        brush_button.clicked.connect(lambda: tool_callback("brush"))
        eraser_button.clicked.connect(lambda: tool_callback("eraser"))
        modal_brush_size = QSpinBox()
        modal_brush_size.setRange(1, 200)
        modal_brush_size.setValue(brush_size)
        modal_brush_size.valueChanged.connect(brush_size_callback)
        tool_grid.addWidget(contour_button, 0, 0)
        tool_grid.addWidget(brush_button, 0, 1)
        tool_grid.addWidget(eraser_button, 1, 0)
        tool_grid.addWidget(QLabel("Tamanho"), 2, 0)
        tool_grid.addWidget(modal_brush_size, 2, 1)
        tools_layout.addLayout(tool_grid)

        save_button = QPushButton("Salvar mascara")
        save_button.setObjectName("primary")
        save_button.clicked.connect(save_callback)
        clear_button = QPushButton("Limpar mascara")
        clear_button.clicked.connect(clear_callback)
        undo_button = QPushButton("Desfazer")
        undo_button.clicked.connect(undo_callback)
        close_button = QPushButton("Fechar")
        close_button.clicked.connect(self.accept)
        tools_layout.addWidget(save_button)
        tools_layout.addWidget(clear_button)
        tools_layout.addWidget(undo_button)
        tools_layout.addStretch()
        tools_layout.addWidget(close_button)
        layout.addWidget(tools_box, 0)

    def set_refresh_callback(self, callback):
        self.refresh_callback = callback

    def set_image(self, image):
        self.current_image = image.convert("RGB")
        self._set_preview_pixmap(self.current_image)

    def reset_zoom(self):
        self.zoom = 1.0

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
        if self.refresh_callback:
            self.refresh_callback()
        else:
            self._set_preview_pixmap(self.current_image)

        if point is not None and viewport_x is not None and viewport_y is not None:
            scale = getattr(self.preview_label, "_display_scale", 1.0)
            self.scroll_area.horizontalScrollBar().setValue(int(point[0] * scale - viewport_x))
            self.scroll_area.verticalScrollBar().setValue(int(point[1] * scale - viewport_y))

    def widget_to_image_xy(self, source_label, x, y):
        if self.current_image is None:
            return None
        image_width, image_height = self.current_image.size
        scale = getattr(source_label, "_display_scale", None)
        offset_x = getattr(source_label, "_display_offset_x", 0)
        offset_y = getattr(source_label, "_display_offset_y", 0)
        if scale is None:
            label_width = source_label.width()
            label_height = source_label.height()
            scale = min(label_width / image_width, label_height / image_height)
            display_width = image_width * scale
            display_height = image_height * scale
            offset_x = (label_width - display_width) / 2
            offset_y = (label_height - display_height) / 2
        image_x = int((x - offset_x) / scale)
        image_y = int((y - offset_y) / scale)
        if image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
            return None
        return image_x, image_y

    def _set_preview_pixmap(self, image):
        width, height = image.size
        qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
        source_pixmap = QPixmap.fromImage(qimage)
        viewport_size = self.scroll_area.viewport().size()
        fit_scale = min(viewport_size.width() / width, viewport_size.height() / height)
        scale = max(0.05, fit_scale * self.zoom)
        target_width = max(1, int(width * scale))
        target_height = max(1, int(height * scale))
        pixmap = source_pixmap.scaled(
            target_width,
            target_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setMinimumSize(pixmap.size())
        self.preview_label.resize(pixmap.size())
        self.preview_label._display_scale = pixmap.width() / width
        self.preview_label._display_offset_x = 0
        self.preview_label._display_offset_y = 0
        self.preview_label.setPixmap(pixmap)

    def _panel(self, title):
        box = QGroupBox(title)
        box.setObjectName("panel")
        return box
