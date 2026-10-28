from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtWidgets import QLabel, QScrollArea, QWidget
from PyQt6.QtGui import QImage, QPainter, QPen, QColor
import io
import math


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


def displayed_pixmap_geometry(label, image_width, image_height):
    scale = getattr(label, "_display_scale", None)
    pixmap = label.pixmap()
    if pixmap is not None and not pixmap.isNull():
        display_width = pixmap.width()
        display_height = pixmap.height()
        if scale is None:
            scale = display_width / max(1, image_width)
        offset_x = (label.width() - display_width) / 2
        offset_y = (label.height() - display_height) / 2
        return scale, offset_x, offset_y

    offset_x = getattr(label, "_display_offset_x", 0)
    offset_y = getattr(label, "_display_offset_y", 0)
    if scale is None:
        label_width = label.width()
        label_height = label.height()
        scale = min(label_width / image_width, label_height / image_height)
        display_width = image_width * scale
        display_height = image_height * scale
        offset_x = (label_width - display_width) / 2
        offset_y = (label_height - display_height) / 2
    return scale, offset_x, offset_y


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
        self.overlay_points = None
        # Chamado sempre que o pixmap muda (escala de exibicao pode ter
        # mudado) - usado pelo DiameterPreviewWidget do card de predicao.
        self.pixmap_changed_callback = None
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

    def paintEvent(self, event):
        super().paintEvent(event)
        points = self.overlay_points
        if not points:
            return
        scale = getattr(self, "_display_scale", 1.0)
        offset_x = getattr(self, "_display_offset_x", 0)
        offset_y = getattr(self, "_display_offset_y", 0)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        widget_points = [QPointF(p[0] * scale + offset_x, p[1] * scale + offset_y) for p in points]

        if len(widget_points) == 2:
            line_pen = QPen(QColor(255, 214, 74))
            line_pen.setWidthF(1.4)
            line_pen.setCosmetic(True)
            painter.setPen(line_pen)
            painter.drawLine(widget_points[0], widget_points[1])

        outline_pen = QPen(QColor(0, 46, 40))
        outline_pen.setWidthF(1.3)
        outline_pen.setCosmetic(True)
        radius = 3.0
        for widget_point in widget_points:
            painter.setPen(outline_pen)
            painter.setBrush(QColor(255, 214, 74))
            painter.drawEllipse(widget_point, radius, radius)

        painter.end()

    def setPixmap(self, pixmap):
        super().setPixmap(pixmap)
        if self.pixmap_changed_callback:
            self.pixmap_changed_callback()

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


class DiameterPreviewWidget(QWidget):
    """Circulo de referencia do 'Diametro estimado', desenhado abaixo da
    imagem do Visualizador na mesma escala dela (acompanha o zoom), pra
    comparar visualmente com o tamanho real dos vasos."""

    FILL_COLOR = QColor(90, 170, 255)
    OUTLINE_WIDTH = 2.0

    def __init__(self):
        super().__init__()
        self.diameter_px = None
        self.scale = 1.0
        self._apply_size()

    def set_diameter(self, diameter_px):
        self.diameter_px = diameter_px if diameter_px and diameter_px > 0 else None
        self._apply_size()

    def set_scale(self, scale):
        self.scale = scale
        self._apply_size()

    def _apply_size(self):
        if not self.diameter_px:
            self.setFixedSize(0, 0)
            return
        size = math.ceil(self.diameter_px * self.scale + self.OUTLINE_WIDTH * 2)
        self.setFixedSize(size, size)
        self.update()

    def paintEvent(self, event):
        if not self.diameter_px:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(self.FILL_COLOR.darker(150))
        pen.setWidthF(self.OUTLINE_WIDTH)
        painter.setPen(pen)
        painter.setBrush(self.FILL_COLOR)
        inset = self.OUTLINE_WIDTH / 2
        painter.drawEllipse(QRectF(self.rect()).adjusted(inset, inset, -inset, -inset))
        painter.end()


class ZoomScrollArea(QScrollArea):
    """QScrollArea que repassa a roda do mouse (em coordenadas do viewport)
    pra um callback de zoom em vez de rolar."""

    def __init__(self, wheel_callback):
        super().__init__()
        self.wheel_callback = wheel_callback

    def wheelEvent(self, event):
        position = event.position()
        self.wheel_callback(event.angleDelta().y(), position.x(), position.y())
        event.accept()
