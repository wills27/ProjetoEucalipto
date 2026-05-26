from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QImage
import io


def qimage_from_pil(image):
    """Convert a PIL Image to QImage robustly, with PNG fallback."""
    if image is None:
        return None
    try:
        img = image.convert("RGB")
        width, height = img.size
        data = img.tobytes()
        bytes_per_line = width * 3
        qimg = QImage(data, width, height, bytes_per_line, QImage.Format.Format_RGB888)
        return qimg.copy()
    except Exception:
        try:
            bio = io.BytesIO()
            image.save(bio, format="PNG")
            qimg = QImage.fromData(bio.getvalue())
            return qimg.copy()
        except Exception:
            return None


class AnnotationPreviewLabel(QLabel):
    def __init__(
        self,
        start_callback,
        drag_callback,
        finish_callback,
        cancel_callback=None,
        double_click_callback=None,
        wheel_callback=None,
        ctrl_left_callback=None,
        draw_button=Qt.MouseButton.LeftButton,
        pan_button=None,
        pan_scroll_area=None,
    ):
        super().__init__("Selecione uma imagem.")
        self.start_callback = start_callback
        self.drag_callback = drag_callback
        self.finish_callback = finish_callback
        self.cancel_callback = cancel_callback
        self.double_click_callback = double_click_callback
        self.wheel_callback = wheel_callback
        self.ctrl_left_callback = ctrl_left_callback
        self.draw_button = draw_button
        self.pan_button = pan_button
        self.pan_scroll_area = pan_scroll_area
        self.is_panning = False
        self.pan_start_position = None
        self.pan_start_h = 0
        self.pan_start_v = 0
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def mousePressEvent(self, event):
        if (
            event.button() == Qt.MouseButton.LeftButton
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.ctrl_left_callback
        ):
            self.ctrl_left_callback(self, event.position().x(), event.position().y())
            event.accept()
            return
        if self._is_pan_button(event.button()):
            self.is_panning = True
            self.pan_start_position = event.globalPosition()
            self.pan_start_h = self.pan_scroll_area.horizontalScrollBar().value()
            self.pan_start_v = self.pan_scroll_area.verticalScrollBar().value()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if self._is_draw_button(event.button()) and self.start_callback:
            self.start_callback(self, event.position().x(), event.position().y())
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton and self.cancel_callback:
            self.cancel_callback()

    def mouseMoveEvent(self, event):
        if self.is_panning and self.pan_scroll_area is not None and self.pan_start_position is not None:
            delta = event.globalPosition() - self.pan_start_position
            self.pan_scroll_area.horizontalScrollBar().setValue(int(self.pan_start_h - delta.x()))
            self.pan_scroll_area.verticalScrollBar().setValue(int(self.pan_start_v - delta.y()))
            event.accept()
            return
        if self.drag_callback:
            self.drag_callback(self, event.position().x(), event.position().y())

    def mouseReleaseEvent(self, event):
        if self.is_panning and self._is_pan_button(event.button()):
            self.is_panning = False
            self.pan_start_position = None
            self.unsetCursor()
            event.accept()
            return
        if self._is_draw_button(event.button()) and self.finish_callback:
            self.finish_callback(self, event.position().x(), event.position().y())
            event.accept()

    def mouseDoubleClickEvent(self, event):
        if self._is_draw_button(event.button()) and self.start_callback:
            self.start_callback(self, event.position().x(), event.position().y())
            event.accept()
            return
        if self.double_click_callback:
            if self.cancel_callback:
                self.cancel_callback()
            self.double_click_callback()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        if self.wheel_callback:
            self.wheel_callback(event.angleDelta().y(), self, event.position().x(), event.position().y())
            event.accept()
        else:
            super().wheelEvent(event)

    def _is_draw_button(self, button):
        return self.draw_button is not None and button == self.draw_button

    def _is_pan_button(self, button):
        return (
            self.pan_button is not None
            and self.pan_scroll_area is not None
            and button == self.pan_button
        )
