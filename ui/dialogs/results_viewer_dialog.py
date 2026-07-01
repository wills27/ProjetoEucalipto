import json
import threading
import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)
from skimage.segmentation import find_boundaries

from services.overlay_rendering import draw_mask_ids
from services.paths import cell_counts_csv_path, cell_measurements_csv_path, overlays_dir, predictions_dir
from ui.widgets import AnnotationPreviewLabel, displayed_pixmap_geometry, qimage_from_pil


class _OverlaySignals(QObject):
    ready = pyqtSignal(str, object, object, object, object)


def _compute_overlay(window, image_stem, image_path, pred_path):
    from skimage.measure import regionprops as skimage_regionprops
    try:
        mask = window.load_mask_array(pred_path)
        if mask is None:
            return None, None, {}, {}

        label_to_cell_id = {}
        region_values_by_label = {}
        centroids = {}
        unit, unit_per_pixel = window.calibration()
        has_calibration = unit_per_pixel > 0
        for index, region in enumerate(skimage_regionprops(mask), start=1):
            label_value = int(region.label)
            label_to_cell_id[label_value] = index
            centroids[label_value] = region.centroid
            perimeter = getattr(region, "perimeter", None)
            area = float(region.area)
            perimeter_value = float(perimeter) if perimeter is not None else 0.0
            region_values_by_label[label_value] = {
                "filename": image_stem,
                "cell_id": str(index),
                "area_px": f"{area:.3f}",
                "perimeter_px": f"{perimeter_value:.3f}" if perimeter is not None else "",
                "centroid_x": f"{float(region.centroid[1]):.3f}",
                "centroid_y": f"{float(region.centroid[0]):.3f}",
                "area_calibrada": f"{area * (unit_per_pixel ** 2):.3f}" if has_calibration else "",
                "perimeter_calibrado": f"{perimeter_value * unit_per_pixel:.3f}" if has_calibration and perimeter is not None else "",
                "unidade": unit if has_calibration else "",
            }

        disk_path = overlays_dir(window.config) / f"{image_stem}_viewer_overlay.png"
        index_path = overlays_dir(window.config) / f"{image_stem}_viewer_index.json"

        if disk_path.exists() and index_path.exists():
            try:
                mask_mtime = pred_path.stat().st_mtime
                if disk_path.stat().st_mtime >= mask_mtime and index_path.stat().st_mtime >= mask_mtime:
                    with Image.open(disk_path) as img:
                        overlay = img.convert("RGB").copy()
                    with open(index_path, "r", encoding="utf-8") as f:
                        index_data = json.load(f)
                    label_to_cell_id = {int(k): v for k, v in index_data["label_to_cell_id"].items()}
                    region_values_by_label = {int(k): v for k, v in index_data["region_values_by_label"].items()}
                    return overlay, mask, label_to_cell_id, region_values_by_label
            except (OSError, KeyError, ValueError, json.JSONDecodeError):
                pass

        results_cache_key = window.analysis_render_cache_key(image_stem, "overlay")
        if results_cache_key and results_cache_key in window.analysis_render_cache:
            colored_base = window.analysis_render_cache[results_cache_key].copy()
            draw_mask_ids(colored_base, mask, label_texts=label_to_cell_id, centroids=centroids)
            overlay = colored_base
        else:
            base_image = window.load_image_as_rgb(image_path)
            overlay = window.render_colored_id_overlay(
                base_image, mask, label_texts=label_to_cell_id, centroids=centroids
            )

        try:
            disk_path.parent.mkdir(parents=True, exist_ok=True)
            overlay.save(str(disk_path), format="PNG", optimize=True)
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump({
                    "label_to_cell_id": {str(k): v for k, v in label_to_cell_id.items()},
                    "region_values_by_label": {str(k): v for k, v in region_values_by_label.items()},
                }, f)
        except OSError:
            pass

        return overlay, mask, label_to_cell_id, region_values_by_label
    except Exception:
        return None, None, {}, {}


class ResultsViewerDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.current_stem = None
        self._measurements_rows = []
        self.current_mask = None
        self.current_base_overlay = None
        self.current_preview_image = None
        self.current_preview_pixmap = None
        self.selected_label = None
        self.label_to_cell_id = {}
        self.region_values_by_label = {}
        self.measurements_by_image = {}
        self.zoom = 1.0
        self._overlay_signals = _OverlaySignals()
        self._overlay_signals.ready.connect(self._on_overlay_ready)
        self._loading_stem = None
        self.setWindowTitle("Visualizar resultados")
        self.resize(1280, 820)

        layout = QHBoxLayout(self)
        layout.setSpacing(12)

        # LEFT: image list
        left = window.panel("Imagens")
        left_layout = QVBoxLayout(left)
        left.setMinimumWidth(180)
        left.setMaximumWidth(220)
        self.image_list = QListWidget()
        self.image_list.currentItemChanged.connect(
            lambda current, _prev: self.show_image(
                current.data(Qt.ItemDataRole.UserRole) if current else None
            )
        )
        left_layout.addWidget(self.image_list, 1)
        window.add_button(left_layout, "Atualizar", self.refresh_all)
        layout.addWidget(left, 0)

        # CENTER: splitter vertical (imagem em cima, medidas embaixo)
        center_splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(center_splitter, 1)

        # topo: tabs (visual + contagens)
        self.tabs = QTabWidget()
        center_splitter.addWidget(self.tabs)

        visual_tab = QWidget()
        visual_layout = QVBoxLayout(visual_tab)
        visual_layout.setContentsMargins(8, 8, 8, 8)
        visual_layout.setSpacing(8)
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
        self.result_preview.setMinimumSize(360, 200)
        self.result_preview.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.preview_scroll_area = QScrollArea()
        self.preview_scroll_area.setWidgetResizable(True)
        self.preview_scroll_area.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll_area.setWidget(self.result_preview)
        self.result_preview.pan_scroll_area = self.preview_scroll_area
        visual_layout.addWidget(self.preview_scroll_area, 1)
        self.tabs.addTab(visual_tab, "Visualizacao")

        self.counts_table = self.create_result_table()
        self.tabs.addTab(self.counts_table, "Contagens")

        # baixo: tabela de medidas
        self.measurements_table = self.create_result_table()
        center_splitter.addWidget(self.measurements_table)
        center_splitter.setStretchFactor(0, 3)
        center_splitter.setStretchFactor(1, 1)
        self._syncing_selection = False
        self.measurements_table.itemSelectionChanged.connect(self._on_measurements_row_selected)

        self.calibration_label = QLabel()
        self.image_stats_label = QLabel()

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
        selected_stem = (
            self.image_list.currentItem().data(Qt.ItemDataRole.UserRole)
            if self.image_list.currentItem() else None
        )

        self.load_measurement_index()
        counts_rows = self.window.load_semicolon_csv(cell_counts_csv_path(self.window.config))
        self.window.populate_csv_table(self.counts_table, counts_rows)
        self._measurements_rows = self.window.load_semicolon_csv(cell_measurements_csv_path(self.window.config))

        cell_count_by_stem = {}
        if counts_rows and len(counts_rows) > 1:
            headers = counts_rows[0]
            try:
                fn_idx = headers.index("filename")
                cc_idx = headers.index("cell_count")
                for row in counts_rows[1:]:
                    if len(row) > max(fn_idx, cc_idx):
                        try:
                            cell_count_by_stem[row[fn_idx]] = int(float(row[cc_idx]))
                        except (ValueError, TypeError):
                            pass
            except ValueError:
                pass

        self.image_list.clear()
        for stem in self.window.result_image_entries():
            count = cell_count_by_stem.get(stem)
            display = f"{stem}  ({count})" if count is not None else stem
            item = QListWidgetItem(display)
            item.setData(Qt.ItemDataRole.UserRole, stem)
            self.image_list.addItem(item)

        if selected_stem:
            for i in range(self.image_list.count()):
                if self.image_list.item(i).data(Qt.ItemDataRole.UserRole) == selected_stem:
                    self.image_list.setCurrentRow(i)
                    return
        if self.image_list.count() > 0:
            self.image_list.setCurrentRow(0)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.set_preview_pixmap()

    def showEvent(self, event):
        super().showEvent(event)
        self.set_preview_pixmap()

    def _refresh_measurements_table(self):
        rows = self._measurements_rows
        if not rows or not self.current_stem:
            self.window.populate_csv_table(self.measurements_table, [])
            return
        headers = rows[0]
        try:
            fn_idx = headers.index("filename")
        except ValueError:
            self.window.populate_csv_table(self.measurements_table, rows)
            return
        keep = [i for i, h in enumerate(headers) if i != fn_idx]
        filtered_headers = [headers[i] for i in keep]
        filtered = [
            [row[i] if i < len(row) else "" for i in keep]
            for row in rows[1:]
            if (row[fn_idx] if fn_idx < len(row) else "") == self.current_stem
        ]
        self.window.populate_csv_table(self.measurements_table, [filtered_headers] + filtered)

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
        self._refresh_measurements_table()
        self.current_mask = None
        self.current_base_overlay = None
        self.current_preview_image = None
        self.current_preview_pixmap = None
        self.selected_label = None
        self.label_to_cell_id = {}
        self.region_values_by_label = {}
        self.zoom = 1.0
        self.clear_cell_values()
        self.image_stats_label.setText("")

        image_path = self.window.result_image_path(image_stem)
        pred_path = predictions_dir(self.window.config) / f"{image_stem}_pred_masks.tif"
        if image_path is None or not image_path.exists() or not pred_path.exists():
            self.result_preview.setText("Imagem ou predicao nao encontrada.")
            self.result_preview.setPixmap(QPixmap())
            return

        cache_key = (
            self.window.cache_key("image", image_path),
            self.window.cache_key("mask", pred_path),
        )
        cached = self.window.viewer_render_cache.get(cache_key)
        if cached is not None:
            self.current_mask, self.label_to_cell_id, self.region_values_by_label, self.current_base_overlay = cached
            self.set_preview_image(self.current_base_overlay)
            self.update_image_stats()
            return

        quick_image = self._quick_preview_image(image_stem)
        if quick_image is not None:
            self.set_preview_image(quick_image)
            self.result_preview.setText("")

        self._loading_stem = image_stem
        self.image_stats_label.setText("Carregando...")
        signals = self._overlay_signals
        window = self.window

        def worker():
            overlay, mask, label_to_cell_id, region_values = _compute_overlay(window, image_stem, image_path, pred_path)
            signals.ready.emit(image_stem, overlay, mask, label_to_cell_id, region_values)

        threading.Thread(target=worker, daemon=True).start()

    def _quick_preview_image(self, image_stem):
        results_cache_key = self.window.analysis_render_cache_key(image_stem, "overlay")
        if results_cache_key and results_cache_key in self.window.analysis_render_cache:
            return self.window.analysis_render_cache[results_cache_key].copy()
        image_path = self.window.result_image_path(image_stem)
        if image_path and image_path.exists():
            return self.window.load_image_as_rgb(image_path)
        return None

    def _on_overlay_ready(self, stem, overlay, mask, label_to_cell_id, region_values):
        if stem != self.current_stem:
            return
        if overlay is None:
            if self.current_preview_image is None:
                self.result_preview.setText("Imagem ou predicao nao encontrada.")
                self.result_preview.setPixmap(QPixmap())
            return
        self.current_mask = mask
        self.label_to_cell_id = label_to_cell_id
        self.region_values_by_label = region_values
        self.current_base_overlay = overlay
        pred_path = predictions_dir(self.window.config) / f"{stem}_pred_masks.tif"
        image_path = self.window.result_image_path(stem)
        cache_key = (
            self.window.cache_key("image", image_path),
            self.window.cache_key("mask", pred_path),
        )
        self.window.viewer_render_cache[cache_key] = (
            mask, label_to_cell_id.copy(), region_values.copy(), overlay.copy()
        )
        self.set_preview_image(overlay)
        self.update_image_stats()

    def update_image_stats(self):
        total = len(self.region_values_by_label)
        if total == 0:
            self.image_stats_label.setText("Sem células detectadas")
            return
        unit, unit_per_pixel = self.window.calibration()
        has_calibration = unit_per_pixel > 0
        areas = []
        for values in self.region_values_by_label.values():
            key = "area_calibrada" if has_calibration else "area_px"
            try:
                areas.append(float(values.get(key, 0) or 0))
            except ValueError:
                pass
        lines = [f"Total: {total} células"]
        if areas:
            avg = sum(areas) / len(areas)
            suffix = f" {unit}²" if has_calibration else " px²"
            lines.append(f"Área média: {avg:.2f}{suffix}")
        self.image_stats_label.setText("\n".join(lines))

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

    def _measurements_col_index(self):
        cols = {}
        for col in range(self.measurements_table.columnCount()):
            header = self.measurements_table.horizontalHeaderItem(col)
            if header:
                cols[header.text().lower()] = col
        return cols

    def _measurements_row_for_label(self, label_value):
        region_vals = self.region_values_by_label.get(label_value)
        if not region_vals:
            return None, None
        # viewer: centroid_x=col(centroid[1]), centroid_y=row(centroid[0])
        # csv:    centroid_x=row(centroid[0]), centroid_y=col(centroid[1])
        try:
            target_row = float(region_vals["centroid_y"])
            target_col = float(region_vals["centroid_x"])
        except (KeyError, ValueError):
            return None, None
        cols = self._measurements_col_index()
        cx_col = cols.get("centroid_x")
        cy_col = cols.get("centroid_y")
        if cx_col is None or cy_col is None:
            return None, None
        for row in range(self.measurements_table.rowCount()):
            cx_item = self.measurements_table.item(row, cx_col)
            cy_item = self.measurements_table.item(row, cy_col)
            if not cx_item or not cy_item:
                continue
            try:
                csv_row = float(cx_item.text())
                csv_col = float(cy_item.text())
            except ValueError:
                continue
            if abs(csv_row - target_row) < 1.0 and abs(csv_col - target_col) < 1.0:
                return row, cx_item
        return None, None

    def _label_for_measurements_row(self, table_row):
        cols = self._measurements_col_index()
        cx_col = cols.get("centroid_x")
        cy_col = cols.get("centroid_y")
        if cx_col is None or cy_col is None:
            return None
        cx_item = self.measurements_table.item(table_row, cx_col)
        cy_item = self.measurements_table.item(table_row, cy_col)
        if not cx_item or not cy_item:
            return None
        try:
            csv_row = float(cx_item.text().replace(",", "."))
            csv_col = float(cy_item.text().replace(",", "."))
        except ValueError:
            return None
        for label_value, region_vals in self.region_values_by_label.items():
            try:
                v_row = float(region_vals["centroid_y"])
                v_col = float(region_vals["centroid_x"])
            except (KeyError, ValueError):
                continue
            if abs(csv_row - v_row) < 1.0 and abs(csv_col - v_col) < 1.0:
                return label_value
        return None

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
                self._update_overlay_pixmap(image)
            self.clear_cell_values()
            return
        self.selected_label = label_value
        image = self.render_selected_overlay(label_value)
        if image is not None:
            self._update_overlay_pixmap(image)
        self._syncing_selection = True
        mrow, mitem = self._measurements_row_for_label(label_value)
        if mrow is not None:
            self.measurements_table.selectRow(mrow)
            self.measurements_table.scrollToItem(mitem, QAbstractItemView.ScrollHint.PositionAtCenter)
        else:
            self.measurements_table.clearSelection()
        cell_id = self.label_to_cell_id.get(label_value)
        self.highlight_csv_row(self.counts_table, self.current_stem, cell_id)
        self._syncing_selection = False

    def _on_measurements_row_selected(self):
        if self._syncing_selection or self.current_mask is None or self.current_stem is None:
            return
        rows = self.measurements_table.selectionModel().selectedRows()
        if not rows:
            return
        table_row = rows[0].row()
        label_value = self._label_for_measurements_row(table_row)
        if label_value is None:
            return
        self.selected_label = label_value
        image = self.render_selected_overlay(label_value)
        if image is not None:
            self._update_overlay_pixmap(image)
        self._syncing_selection = True
        cell_id = self.label_to_cell_id.get(label_value)
        self.highlight_csv_row(self.counts_table, self.current_stem, cell_id)
        self._syncing_selection = False

    def calibration_status_text(self):
        unit, unit_per_pixel = self.window.calibration()
        if unit_per_pixel <= 0:
            return "Calibração: não definida"
        return f"Calibração: {unit_per_pixel:.6g} {unit}/px"

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

    def _update_overlay_pixmap(self, image):
        """Swap overlay without recalculating scale — avoids zoom drift on cell selection."""
        scale = getattr(self.result_preview, "_display_scale", None)
        if scale is None:
            self.set_preview_image(image)
            return
        qimage = qimage_from_pil(image)
        if qimage is None:
            return
        self.current_preview_image = image
        self.current_preview_pixmap = QPixmap.fromImage(qimage)
        width, height = image.size
        target_w = max(1, int(width * scale))
        target_h = max(1, int(height * scale))
        pixmap = self.current_preview_pixmap.scaled(
            target_w,
            target_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.result_preview.setPixmap(pixmap)

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
        self.zoom = max(0.2, min(30.0, self.zoom * factor))
        self.set_preview_pixmap()
        if point is not None and viewport_x is not None and viewport_y is not None:
            scale = getattr(self.result_preview, "_display_scale", 1.0)
            self.preview_scroll_area.horizontalScrollBar().setValue(int(point[0] * scale - viewport_x))
            self.preview_scroll_area.verticalScrollBar().setValue(int(point[1] * scale - viewport_y))

    def reset_zoom(self):
        self.zoom = 1.0
        self.set_preview_pixmap()

    def highlight_csv_row(self, table, stem, cell_id):
        if not stem or not cell_id:
            return
        filename_col = cell_id_col = None
        for col in range(table.columnCount()):
            header = table.horizontalHeaderItem(col)
            if header is None:
                continue
            text = header.text().lower()
            if text == "filename":
                filename_col = col
            elif text == "cell_id":
                cell_id_col = col
        if filename_col is None or cell_id_col is None:
            return
        for row in range(table.rowCount()):
            fn_item = table.item(row, filename_col)
            cid_item = table.item(row, cell_id_col)
            if fn_item and cid_item and fn_item.text() == stem and cid_item.text() == str(cell_id):
                table.selectRow(row)
                table.scrollToItem(fn_item, QAbstractItemView.ScrollHint.PositionAtCenter)
                return

    def clear_cell_values(self):
        self._syncing_selection = True
        self.counts_table.clearSelection()
        self.measurements_table.clearSelection()
        self._syncing_selection = False
