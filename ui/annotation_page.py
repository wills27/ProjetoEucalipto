import shutil
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PIL import Image

from services.annotation import (
    add_non_overlapping_area,
    apply_brush,
    connected_component_at,
    contour_area,
    draw_contour_preview,
    draw_stroke_preview,
    overlay_mask,
    validate_mask_file,
)
from ui.mask_edit_target import DatasetMaskTarget
from services.paths import conversion_excluded_dir, conversion_input_dir
from ui.annotation_editor import AnnotationEditorDialog
from ui.widgets import AnnotationPreviewLabel

IMAGE_EXTENSIONS = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]


class AnnotationPage(QWidget):
    def __init__(self, window, build_ui=True):
        super().__init__()
        self.window = window
        self.build_ui = build_ui
        self.view_buttons = {}
        self.view_mode = "overlay"
        self.tool = "contour"
        self.base_image = None
        self.mask = None
        self.current_image_entry = None
        self.mask_history = []
        self.drawing = False
        self.contour_points = []
        self.stroke_points = []
        self.editor = None
        self.current_stroke_label = None
        self.is_busy = False
        self.busy_controls = []
        self._init_controls()
        if build_ui:
            self.build()

    def _init_controls(self):
        self.model_label = QLabel("Modelo ativo: -")
        self.model_label.setWordWrap(True)
        self.model_label.setObjectName("mono")
        self.status_label = QLabel("Selecione uma imagem para anotar.")
        self.status_label.setWordWrap(True)
        self.status_label.setObjectName("hint")
        self.tool_hint_label = QLabel(
            "Edicao manual disponivel na janela maior. De duplo clique na imagem para abrir."
        )
        self.tool_hint_label.setWordWrap(True)
        self.tool_hint_label.setObjectName("hint")

        self.padding = QSpinBox()
        self.padding.setRange(0, 2048)
        self.padding.setValue(int(self.window.config["padding_pixels"]))
        self.diameter = QLineEdit(str(self.window.config["diameter"]))
        self.cellprob = QLineEdit(str(self.window.config["cellprob_threshold"]))
        self.flow = QLineEdit(str(self.window.config["flow_threshold"]))
        self.brush_size = QSpinBox()
        self.brush_size.setRange(1, 200)
        self.brush_size.setValue(16)

        self.contour_button = None
        self.eraser_button = None

    def build(self):
        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        left = self.window.panel("Fila de anotacao")
        left_layout = QVBoxLayout(left)
        self.summary = QLabel("Aguardando imagens.")
        self.summary.setObjectName("mono")
        self.image_list = QListWidget()
        self.image_list.currentItemChanged.connect(self.show_item)
        left_layout.addWidget(self.summary)
        left_layout.addWidget(self.image_list, 1)
        refresh_button = self.window.add_button(left_layout, "Atualizar", self.refresh_images)
        self.busy_controls.append(refresh_button)
        layout.addWidget(left, 0)

        center = self.window.panel("Pre-visualizacao")
        center_layout = QVBoxLayout(center)
        mode_layout = QHBoxLayout()
        for label, mode in [("Original", "original"), ("Overlay", "overlay")]:
            button = QPushButton(label)
            button.setObjectName("mode")
            button.setProperty("active", mode == "overlay")
            button.clicked.connect(lambda checked=False, selected=mode: self.set_view_mode(selected))
            self.view_buttons[mode] = button
            mode_layout.addWidget(button)
        mode_layout.addStretch()
        center_layout.addLayout(mode_layout)
        self.preview_label = AnnotationPreviewLabel(
            self.start_draw,
            self.drag_draw,
            self.finish_draw,
            self.cancel_draw,
            self.open_editor,
            draw_button=None,
        )
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 520)
        center_layout.addWidget(self.preview_label, 1)
        layout.addWidget(center, 1)

        right = self.window.panel("Acoes")
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.model_label)

        params_box = self.window.panel("Parametros do modelo")
        params_layout = QGridLayout(params_box)
        params_layout.addWidget(QLabel("Padding"), 0, 0)
        params_layout.addWidget(self.padding, 0, 1)
        params_layout.addWidget(QLabel("Diametro"), 1, 0)
        params_layout.addWidget(self.diameter, 1, 1)
        params_layout.addWidget(QLabel("Cell prob threshold"), 2, 0)
        params_layout.addWidget(self.cellprob, 2, 1)
        params_layout.addWidget(QLabel("Flow threshold"), 3, 0)
        params_layout.addWidget(self.flow, 3, 1)
        right_layout.addWidget(params_box)

        predict_button = self.window.add_button(
            right_layout,
            "Gerar mascara automatica",
            self.window.run_annotation_mask_prediction,
            primary=True,
        )
        edit_button = self.window.add_button(right_layout, "Editar em janela maior", self.open_editor)
        self.busy_controls.extend([predict_button, edit_button])

        tools_box = self.window.panel("Edicao manual")
        tools_layout = QGridLayout(tools_box)
        self.contour_button = QPushButton("Contorno")
        self.contour_button.setObjectName("mode")
        self.contour_button.setProperty("active", True)
        self.contour_button.setVisible(False)
        self.contour_button.clicked.connect(lambda: self.set_tool("contour"))
        self.eraser_button = QPushButton("Borracha")
        self.eraser_button.setObjectName("mode")
        self.eraser_button.setVisible(False)
        self.eraser_button.clicked.connect(lambda: self.set_tool("eraser"))

        save_mask_button = QPushButton("Salvar mascara")
        save_mask_button.setObjectName("primary")
        save_mask_button.clicked.connect(self.save_mask)
        self.busy_controls.append(save_mask_button)
        tools_layout.addWidget(save_mask_button, 0, 0, 1, 2)
        clear_mask_button = QPushButton("Limpar mascara")
        clear_mask_button.clicked.connect(self.clear_mask)
        undo_mask_button = QPushButton("Desfazer")
        undo_mask_button.clicked.connect(self.undo_mask)
        self.busy_controls.extend([clear_mask_button, undo_mask_button])
        tools_layout.addWidget(clear_mask_button, 1, 0)
        tools_layout.addWidget(undo_mask_button, 1, 1)
        right_layout.addWidget(tools_box)

        exclude_button = self.window.add_button(right_layout, "Excluir da base", self.exclude_image)
        open_folder_button = self.window.add_button(
            right_layout,
            "Abrir pasta de entrada",
            lambda: self.window.open_folder(conversion_input_dir(self.window.config)),
        )
        self.busy_controls.extend([exclude_button, open_folder_button])
        self.busy_progress = QProgressBar()
        self.busy_progress.setRange(0, 0)
        self.busy_progress.setTextVisible(False)
        self.busy_progress.setVisible(False)
        right_layout.addWidget(self.busy_progress)
        right_layout.addWidget(self.status_label)
        right_layout.addStretch()
        layout.addWidget(right, 0)

    def refresh_images(self):
        if not self.build_ui:
            if self.current_image_entry:
                self.current_image_entry.refresh_state()
            return
        input_dir = conversion_input_dir(self.window.config)
        input_dir.mkdir(parents=True, exist_ok=True)
        selected = self.window.pending_annotation_image_name
        if selected is None and self.image_list.currentItem():
            current_entry = self.image_list.currentItem().data(Qt.ItemDataRole.UserRole)
            selected = current_entry.path.name if current_entry else None
        entries = self.image_entries()
        self.image_list.clear()
        for entry in entries:
            item = QListWidgetItem(f"{entry.label}  {entry.path.name}")
            item.setData(Qt.ItemDataRole.UserRole, entry)
            self.image_list.addItem(item)
        missing_count = sum(1 for entry in entries if not entry.has_mask)
        masked_count = len(entries) - missing_count
        self.summary.setText(
            f"Sem mascara: {missing_count}\n"
            f"Com mascara: {masked_count}\n"
            f"Pasta: {input_dir}"
        )
        self.model_label.setText(f"Modelo ativo: {self.window.config.get('active_model') or 'Nenhum'}")
        if selected:
            for index in range(self.image_list.count()):
                item = self.image_list.item(index)
                entry = item.data(Qt.ItemDataRole.UserRole) or {}
                if entry and entry.path.name == selected:
                    self.image_list.setCurrentItem(item)
                    self.window.pending_annotation_image_name = None
                    return
        if entries:
            self.image_list.setCurrentRow(0)
        else:
            self.preview_label.setText("Nenhuma imagem encontrada.")
            self.preview_label.setPixmap(QPixmap())
            self.status_label.setText("A pasta de entrada nao tem imagens.")

    def image_entries(self):
        input_dir = conversion_input_dir(self.window.config)
        images = []
        for ext in IMAGE_EXTENSIONS:
            images.extend(input_dir.glob(f"*{ext}"))
        image_paths = sorted(
            path
            for path in images
            if not path.stem.endswith("_masks")
            and not path.stem.endswith("_pred_mask")
        )
        entries = []
        for path in image_paths:
            seg_path = path.with_name(f"{path.stem}_seg.npy")
            tif_mask_path = path.with_name(f"{path.stem}_masks.tif")
            validation = validate_mask_file(seg_path, tif_mask_path)
            has_mask = validation["valid"]
            entries.append(
                DatasetMaskTarget(
                    path=path,
                    seg_path=seg_path,
                    tif_mask_path=tif_mask_path,
                    has_mask=has_mask,
                    label="[Com mascara]" if has_mask else "[Sem mascara]",
                    window=self.window,
                )
            )
        return sorted(entries, key=lambda entry: (entry.has_mask, entry.path.name.lower()))

    def current_image_path(self):
        if not self.build_ui:
            entry = self.current_image_entry
            path = entry.path if entry else None
            return path if path and path.exists() else None
        current = self.image_list.currentItem()
        if current is None:
            return None
        entry = current.data(Qt.ItemDataRole.UserRole)
        path = entry.path if entry else None
        return path if path and path.exists() else None

    def current_entry(self):
        if not self.build_ui:
            return self.current_image_entry
        current = self.image_list.currentItem()
        if current is None:
            return None
        return current.data(Qt.ItemDataRole.UserRole)

    def show_item(self, current, _previous=None):
        if current is None:
            return
        entry = current.data(Qt.ItemDataRole.UserRole)
        if not entry:
            return
        self.show_image(entry)

    def show_image(self, entry):
        image_path = entry.path
        if not image_path.exists():
            if self.build_ui:
                self.preview_label.setText("Imagem nao encontrada.")
                self.preview_label.setPixmap(QPixmap())
            self.set_status("Imagem nao encontrada.")
            return
        try:
            self.current_image_entry = entry
            self.base_image = Image.open(image_path).convert("RGB")
            self.mask = entry.load_mask(self.base_image.size)
            self.mask_history = []
            self.reset_transient_drawing()
            self.update_preview()
            self.set_status(entry.status_text())
        except Exception as exc:
            if self.build_ui:
                self.preview_label.setText(f"Nao foi possivel carregar preview:\n{exc}")
                self.preview_label.setPixmap(QPixmap())
            self.set_status(f"Nao foi possivel carregar preview: {exc}")
            if hasattr(self.window, "show_error"):
                self.window.show_error(
                    "Erro ao carregar preview",
                    "Nao foi possivel carregar a imagem ou a mascara.",
                    traceback.format_exc(),
                )

    def update_preview(self):
        if self.base_image is None:
            return
        image = self.render_image()
        if self.build_ui:
            self.window.set_label_pixmap(self.preview_label, image)
        if self.editor is not None:
            self.editor.set_image(image)

    def render_image(self):
        image = self.base_image
        if self.view_mode == "overlay":
            image = overlay_mask(image, self.mask)
        if self.contour_points:
            image = draw_contour_preview(image, self.contour_points)
        if self.stroke_points:
            image = draw_stroke_preview(
                image,
                self.stroke_points,
                self.brush_size.value(),
                self.tool,
            )
        return image

    def set_view_mode(self, mode):
        self.view_mode = mode
        for key, button in self.view_buttons.items():
            button.setProperty("active", key == mode)
            button.style().unpolish(button)
            button.style().polish(button)
        if self.current_entry():
            self.update_preview()

    def set_tool(self, tool):
        self.tool = tool
        hints = {
            "contour": "Janela maior: botao direito desenha/fecha; Ctrl + esquerdo remove a mascara clicada.",
            "eraser": "Janela maior: arraste com o botao direito para apagar; Ctrl + esquerdo remove a mascara clicada.",
        }
        if tool not in hints:
            tool = "contour"
            self.tool = tool
        self.tool_hint_label.setText(hints[tool])
        for button, active in [
            (self.contour_button, tool == "contour"),
            (self.eraser_button, tool == "eraser"),
        ]:
            if button is None:
                continue
            button.setProperty("active", active)
            button.style().unpolish(button)
            button.style().polish(button)

    def set_status(self, text):
        self.status_label.setText(text)

    def model_parameters(self):
        return {
            "padding": self.padding.value(),
            "diameter": self.diameter.text().strip(),
            "cellprob_threshold": self.cellprob.text().strip(),
            "flow_threshold": self.flow.text().strip(),
        }

    def save_model_parameters_to_config(self, config, parse_float):
        params = self.model_parameters()
        config["padding_pixels"] = params["padding"]
        config["diameter"] = parse_float(params["diameter"], 0.0)
        config["cellprob_threshold"] = parse_float(params["cellprob_threshold"], 0.0)
        config["flow_threshold"] = parse_float(params["flow_threshold"], 0.4)

    def sync_from_config(self, config):
        self.padding.setValue(int(config["padding_pixels"]))
        self.diameter.setText(str(config["diameter"]))
        self.cellprob.setText(str(config["cellprob_threshold"]))
        self.flow.setText(str(config["flow_threshold"]))

    def open_editor(self):
        if self.is_busy:
            QMessageBox.information(self.window, "Anotar", "Aguarde a mascara automatica terminar.")
            return
        if self.current_image_entry is None or self.base_image is None:
            QMessageBox.information(self.window, "Editar mascara", "Selecione uma imagem para editar.")
            return

        dialog = AnnotationEditorDialog(
            self.window,
            self.current_image_entry.display_name,
            {
                "start": self.start_draw,
                "drag": self.drag_draw,
                "finish": self.finish_draw,
                "cancel": self.cancel_draw,
            },
            self.delete_object_at,
            self.set_view_mode,
            self.set_tool,
            self.brush_size.value(),
            self.brush_size.setValue,
            self.current_prediction_callback(),
            self.save_mask,
            self.clear_mask,
            self.undo_mask,
        )
        dialog.set_refresh_callback(self.update_preview)
        dialog.finished.connect(self.close_editor)
        self.editor = dialog
        self.editor.set_busy(self.is_busy)
        self.editor.reset_zoom()
        self.update_preview()
        dialog.exec()

    def set_busy(self, busy, message=None):
        self.is_busy = busy
        self.reset_transient_drawing()
        if self.build_ui:
            self.preview_label.setEnabled(not busy)
            self.image_list.setEnabled(not busy)
            if hasattr(self, "busy_progress"):
                self.busy_progress.setVisible(busy)
        for widget in self.busy_controls:
            widget.setEnabled(not busy)
        if self.editor is not None:
            self.editor.set_busy(busy)
        if message:
            self.set_status(message)

    def current_prediction_callback(self):
        if self.current_image_entry and getattr(self.current_image_entry, "prediction_callback", None):
            return self.current_image_entry.prediction_callback
        return self.window.run_annotation_mask_prediction

    def close_editor(self):
        self.editor = None
        self.reset_transient_drawing()
        if self.current_image_entry and self.current_image_entry.commit_on_close:
            self.save_mask(
                silent=False,
                recalculate=self.current_image_entry.recalculate_on_close,
            )
            self.update_preview()
            return
        self.save_mask(silent=True)
        self.update_preview()

    def reload_current_image(self):
        if self.current_image_entry is None:
            return
        self.current_image_entry.refresh_state()
        self.show_image(self.current_image_entry)

    def widget_to_image_xy(self, source_label, x, y, clamp_to_image=False):
        if self.base_image is None:
            return None
        image_width, image_height = self.base_image.size
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
        if clamp_to_image:
            image_x = max(0, min(image_width - 1, image_x))
            image_y = max(0, min(image_height - 1, image_y))
            return image_x, image_y
        if image_x < 0 or image_y < 0 or image_x >= image_width or image_y >= image_height:
            return None
        return image_x, image_y

    def snap_contour_point_to_edge(self, point, tolerance=4):
        if self.base_image is None:
            return point
        image_width, image_height = self.base_image.size
        image_x, image_y = point
        if image_x <= tolerance:
            image_x = 0
        elif image_x >= image_width - 1 - tolerance:
            image_x = image_width - 1
        if image_y <= tolerance:
            image_y = 0
        elif image_y >= image_height - 1 - tolerance:
            image_y = image_height - 1
        return image_x, image_y

    def push_history(self):
        if self.mask is None:
            return
        self.mask_history.append(self.mask.copy())
        self.mask_history = self.mask_history[-20:]

    def delete_object_at(self, source_label, x, y):
        if self.mask is None or self.base_image is None:
            return
        point = self.widget_to_image_xy(source_label, x, y)
        if point is None:
            return
        image_x, image_y = point
        label_value = int(self.mask[image_y, image_x])
        if label_value == 0:
            self.status_label.setText("Nenhuma mascara nesse ponto.")
            return
        component, label_value = connected_component_at(self.mask, point)
        if component is None:
            self.status_label.setText("Nenhuma mascara nesse ponto.")
            return
        self.push_history()
        self.reset_transient_drawing()
        self.mask[component] = 0
        self.update_preview()
        self.status_label.setText(f"Mascara removida no ponto clicado: rotulo {label_value}.")

    def start_draw(self, source_label, x, y):
        if self.is_busy:
            return
        if self.mask is None or self.base_image is None:
            return
        point = self.widget_to_image_xy(source_label, x, y, clamp_to_image=True)
        if point is None:
            return
        if self.tool == "contour":
            point = self.snap_contour_point_to_edge(point)
            if self.drawing:
                if self.distance_between_points(point, self.contour_points[-1]) >= 3:
                    self.contour_points.append(point)
                self.push_history()
                self.close_contour()
            else:
                self.drawing = True
                self.contour_points = [point]
            self.update_preview()
            return
        self.push_history()
        self.drawing = True
        self.current_stroke_label = None
        self.stroke_points = [point]
        self.update_preview()

    def drag_draw(self, source_label, x, y):
        if self.is_busy:
            return
        if not self.drawing:
            return
        point = self.widget_to_image_xy(source_label, x, y, clamp_to_image=True)
        if point is None:
            return
        if self.tool == "contour":
            point = self.snap_contour_point_to_edge(point)
            if self.should_auto_close_contour(point):
                self.push_history()
                self.close_contour()
                self.update_preview()
                return
            if not self.contour_points or self.distance_between_points(point, self.contour_points[-1]) >= 3:
                self.contour_points.append(point)
                self.update_preview()
            return
        if not self.stroke_points or self.distance_between_points(point, self.stroke_points[-1]) >= 2:
            self.stroke_points.append(point)
            self.update_preview()

    def finish_draw(self, source_label, x, y):
        if self.is_busy:
            return
        if not self.drawing:
            return
        if self.tool == "contour":
            return
        point = self.widget_to_image_xy(source_label, x, y, clamp_to_image=True)
        if point is not None and (
            not self.stroke_points
            or self.distance_between_points(point, self.stroke_points[-1]) >= 2
        ):
            self.stroke_points.append(point)
        self.apply_stroke()
        self.stroke_points = []
        self.drawing = False
        self.current_stroke_label = None

    def cancel_draw(self):
        if self.tool != "contour" or not self.drawing:
            return
        self.drawing = False
        self.contour_points = []
        self.stroke_points = []
        self.update_preview()
        self.status_label.setText("Contorno cancelado.")

    def distance_between_points(self, first, second):
        return ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5

    def apply_stroke(self):
        for point in self.interpolated_stroke_points():
            self.apply_brush_at(point)
        self.update_preview()

    def interpolated_stroke_points(self):
        if len(self.stroke_points) < 2:
            return list(self.stroke_points)
        points = [self.stroke_points[0]]
        step = max(1.0, self.brush_size.value() / 3)
        for start, end in zip(self.stroke_points, self.stroke_points[1:]):
            distance = self.distance_between_points(start, end)
            segments = max(1, int(distance / step))
            for index in range(1, segments + 1):
                ratio = index / segments
                points.append(
                    (
                        int(round(start[0] + (end[0] - start[0]) * ratio)),
                        int(round(start[1] + (end[1] - start[1]) * ratio)),
                    )
                )
        return points

    def apply_brush_at(self, point):
        apply_brush(self.mask, point, self.brush_size.value(), self.tool, self.current_stroke_label)

    def fill_contour(self):
        if self.mask is None or len(self.contour_points) < 3:
            return
        area = contour_area(self.mask.shape, self.contour_points)
        add_non_overlapping_area(self.mask, area)

    def should_auto_close_contour(self, point):
        if not self.drawing or len(self.contour_points) < 8:
            return False
        start_point = self.contour_points[0]
        path_distance = sum(
            self.distance_between_points(previous, current)
            for previous, current in zip(self.contour_points, self.contour_points[1:])
        )
        return path_distance >= 40 and self.distance_between_points(point, start_point) <= 6

    def close_contour(self):
        self.fill_contour()
        self.drawing = False
        self.contour_points = []

    def reset_transient_drawing(self):
        self.drawing = False
        self.contour_points = []
        self.stroke_points = []
        self.current_stroke_label = None

    def clear_mask(self):
        if self.is_busy:
            return
        if self.mask is None:
            return
        self.push_history()
        self.reset_transient_drawing()
        self.mask[:] = 0
        self.update_preview()
        self.status_label.setText("Mascara limpa em memoria. Clique em salvar para gravar.")

    def undo_mask(self):
        if self.is_busy:
            return
        if not self.mask_history:
            return
        self.reset_transient_drawing()
        self.mask = self.mask_history.pop()
        self.update_preview()

    def save_mask(self, silent=False, recalculate=False):
        if self.is_busy:
            return
        target = self.current_image_entry
        if not target or self.mask is None:
            if not silent:
                QMessageBox.information(self.window, "Anotar", "Selecione uma imagem para salvar a mascara.")
            return
        target.save(self.mask, self, silent=silent, recalculate=recalculate)

    def exclude_image(self):
        image_path = self.current_image_path()
        if image_path is None:
            QMessageBox.information(self.window, "Anotar", "Selecione uma imagem.")
            return
        excluded_dir = conversion_excluded_dir(self.window.config)
        excluded_dir.mkdir(parents=True, exist_ok=True)
        target = excluded_dir / image_path.name
        counter = 1
        while target.exists():
            target = excluded_dir / f"{image_path.stem}_{counter}{image_path.suffix}"
            counter += 1
        shutil.move(str(image_path), str(target))
        for sidecar in [
            image_path.with_name(f"{image_path.stem}_seg.npy"),
            image_path.with_name(f"{image_path.stem}_masks.tif"),
        ]:
            if sidecar.exists():
                sidecar_target = excluded_dir / sidecar.name
                sidecar_counter = 1
                while sidecar_target.exists():
                    sidecar_target = excluded_dir / f"{sidecar.stem}_{sidecar_counter}{sidecar.suffix}"
                    sidecar_counter += 1
                shutil.move(str(sidecar), str(sidecar_target))
        self.status_label.setText(f"Imagem excluida da base: {target.name}")
        self.refresh_images()
        self.window.refresh_dataset_import()
