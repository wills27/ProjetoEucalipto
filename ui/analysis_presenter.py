from pathlib import Path

import numpy as np
import tifffile as tiff
from PIL import Image
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QTableWidgetItem

from services.csv_files import load_semicolon_csv as read_semicolon_csv
from services.image_arrays import normalize_array
from services.metrics import read_metrics
from services.overlay_rendering import (
    build_label_index,
    overlay_colored_mask_on_image as render_colored_mask_overlay,
    render_colored_id_overlay as render_id_overlay,
    render_measurement_overlay as render_measurement_mask_overlay,
)
from services.paths import cell_counts_csv_path, cell_measurements_csv_path, metrics_csv_path, predictions_dir


class AnalysisPresenterMixin:
    def refresh_analysis_metrics(self):
        self.metrics_by_image = {
            row["image"]: row for row in read_metrics(metrics_csv_path(self.config))
        }
        stem = self.current_result_image_stem() if hasattr(self, "result_images_table") else None
        self.update_metric_panel(stem)

    def refresh_measurement_tables(self):
        if not hasattr(self, "cell_counts_table"):
            return
        counts_path = cell_counts_csv_path(self.config)
        measurements_path = cell_measurements_csv_path(self.config)
        counts_rows = self.load_semicolon_csv(counts_path)
        measurement_rows = self.load_semicolon_csv(measurements_path)
        self.populate_csv_table(self.cell_counts_table, counts_rows)
        self.populate_csv_table(self.cell_measurements_table, measurement_rows)

        if counts_path.exists() and measurements_path.exists():
            self.measurements_status_label.setText(
                f"Contagens: {max(len(counts_rows) - 1, 0)} imagens | "
                f"Medidas: {max(len(measurement_rows) - 1, 0)} objetos"
            )
        else:
            missing = []
            if not counts_path.exists():
                missing.append("cell_counts.csv")
            if not measurements_path.exists():
                missing.append("cell_measurements.csv")
            self.measurements_status_label.setText(
                "Arquivos ainda nao encontrados: " + ", ".join(missing)
            )

    def load_semicolon_csv(self, path):
        return read_semicolon_csv(path)

    def populate_csv_table(self, table, rows):
        table.setSortingEnabled(False)
        table.clear()
        if not rows:
            table.setRowCount(0)
            table.setColumnCount(0)
            table.setSortingEnabled(True)
            return
        headers = rows[0]
        body = rows[1:]
        has_cal = self._csv_has_calibration(headers, body)
        visible = self._csv_visible_columns(headers, has_cal)
        filtered_headers = [headers[i] for i in visible]
        table.setColumnCount(len(filtered_headers))
        table.setHorizontalHeaderLabels(filtered_headers)
        table.setRowCount(len(body))
        for row_index, row in enumerate(body):
            for col_pos, col_idx in enumerate(visible):
                value = row[col_idx] if col_idx < len(row) else ""
                table.setItem(row_index, col_pos, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)

    def _csv_has_calibration(self, headers, body):
        if "unidade" not in headers:
            return False
        unit_col = headers.index("unidade")
        return any(unit_col < len(row) and row[unit_col].strip() for row in body)

    def _csv_visible_columns(self, headers, has_calibration):
        px_cols = {
            "area_px", "perimeter_px", "diametro_elipse_menor_px",
            "media_area_px", "media_diametro_px",
        }
        cal_cols = {
            "area_calibrada", "perimeter_calibrado", "diametro_elipse_menor_calibrado",
            "media_area_calibrada", "media_diametro_calibrado", "unidade",
        }
        return [
            i for i, h in enumerate(headers)
            if not (has_calibration and h in px_cols)
            and not (not has_calibration and h in cal_cols)
        ]

    def show_analysis_image(self, image_stem):
        if not image_stem:
            return
        self.update_metric_panel(image_stem)
        image = self.analysis_preview_image(image_stem, self.current_view_mode)
        if image is not None:
            self.set_analysis_preview_pixmap(image_stem, self.current_view_mode, image)
            QTimer.singleShot(0, lambda stem=image_stem: self.preload_fast_result_views(stem))
            return

        if self.current_view_mode in {"overlay", "overlay_50pct", "overlay_inteiros", "overlay_diametro"}:
            image_path = self.analysis_image_path(image_stem, "original")
            if image_path is not None and image_path.exists():
                self.show_image_file(image_path)
            else:
                self.preview_label.setText("Imagem ou predicao nao encontrada para este modo.")
                self.preview_label.setPixmap(QPixmap())
            return

        image_path = self.analysis_image_path(image_stem, self.current_view_mode)
        if image_path is None or not image_path.exists():
            self.preview_label.setText("Arquivo nao encontrado para este modo.")
            self.preview_label.setPixmap(QPixmap())
            return
        self.show_image_file(image_path)

    def analysis_preview_image(self, stem, mode):
        cache_key = self.analysis_render_cache_key(stem, mode)
        if cache_key is None:
            return None
        if cache_key not in self.analysis_render_cache:
            if mode == "original":
                image_path = self.analysis_image_path(stem, mode)
                if image_path is None or not image_path.exists():
                    return None
                image = self.load_image_as_rgb(image_path)
            else:
                image = self.render_measurement_overlay(stem, mode)
                if image is None:
                    return None
            self.analysis_render_cache[cache_key] = image.copy()
        return self.analysis_render_cache[cache_key].copy()

    def preload_fast_result_views(self, stem):
        if stem != self.current_result_image_stem():
            return
        for mode in ["original", "overlay"]:
            image = self.analysis_preview_image(stem, mode)
            if image is not None:
                self.analysis_pixmap_data(stem, mode, image)

    def analysis_render_cache_key(self, stem, mode):
        image_path = self.result_image_path(stem)
        if image_path is None or not image_path.exists():
            return None
        image_key = self.cache_key("image", image_path)
        if mode == "original":
            return "render", stem, mode, image_key
        if mode in {"overlay", "overlay_50pct", "overlay_inteiros", "overlay_diametro"}:
            pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
            if not pred_path.exists():
                return None
            return "render", stem, mode, image_key, self.cache_key("mask", pred_path)
        return None

    def set_analysis_preview_pixmap(self, stem, mode, image):
        pixmap, scale, offset_x, offset_y = self.analysis_pixmap_data(stem, mode, image)
        self.preview_label._display_scale = scale
        self.preview_label._display_offset_x = offset_x
        self.preview_label._display_offset_y = offset_y
        self.preview_label.setPixmap(pixmap)

    def analysis_pixmap_data(self, stem, mode, image):
        render_key = self.analysis_render_cache_key(stem, mode)
        pixmap_key = (
            render_key,
            self.preview_label.width(),
            self.preview_label.height(),
            image.size,
        )
        if pixmap_key not in self.analysis_pixmap_cache:
            image = image.convert("RGB")
            width, height = image.size
            qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
            source_pixmap = QPixmap.fromImage(qimage)
            pixmap = source_pixmap.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scale = pixmap.width() / width
            offset_x = (self.preview_label.width() - pixmap.width()) / 2
            offset_y = (self.preview_label.height() - pixmap.height()) / 2
            self.analysis_pixmap_cache[pixmap_key] = (pixmap, scale, offset_x, offset_y)
        return self.analysis_pixmap_cache[pixmap_key]

    def analysis_image_path(self, stem, mode):
        if mode == "original":
            return self.result_image_path(stem)
        return None

    def render_measurement_overlay(self, stem, mode):
        image_path = self.result_image_path(stem)
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if image_path is None or not image_path.exists() or not pred_path.exists():
            return None

        base_image = self.load_image_as_rgb(image_path)
        mask = self.load_mask_array(pred_path)
        if mask is None:
            return None

        if mode == "overlay":
            # Mesma fonte (mascara atual + numeracao sequencial) usada pelo
            # dialogo "Visualizar resultados", pra nunca mostrar uma imagem
            # diferente entre as duas telas.
            label_to_cell_id, centroids = build_label_index(mask)
            return render_id_overlay(base_image, mask, label_texts=label_to_cell_id, centroids=centroids)

        return render_measurement_mask_overlay(base_image, mask, mode)

    def load_image_as_rgb(self, path):
        cache_key = self.cache_key("image", path)
        if cache_key not in self.analysis_cache:
            image = Image.open(path)
            array = np.array(image)
            if array.ndim == 2:
                array = normalize_array(array)
                image = Image.fromarray(array).convert("RGB")
            else:
                image = image.convert("RGB")
            self.analysis_cache[cache_key] = image
        return self.analysis_cache[cache_key].copy()

    def load_mask_array(self, path):
        cache_key = self.cache_key("mask", path)
        if cache_key not in self.analysis_cache:
            mask = np.asarray(tiff.imread(path)).astype(np.uint16)
            if mask.ndim > 2:
                mask = np.squeeze(mask)
            if mask.ndim != 2:
                return None
            self.analysis_cache[cache_key] = mask
        return self.analysis_cache[cache_key]

    def clear_analysis_caches(self):
        self.analysis_cache.clear()
        self.analysis_render_cache.clear()
        self.analysis_pixmap_cache.clear()
        self.viewer_render_cache.clear()
        self.clear_result_indexes()

    def clear_result_indexes(self):
        self.result_entries_cache = None
        self.result_status_index = {}
        self.result_status_index_model = None
        self.result_row_by_stem = {}
        if hasattr(self, "runtime_overlay_ready_stems"):
            self.runtime_overlay_ready_stems.clear()
        if hasattr(self, "runtime_metrics_ready_stems"):
            self.runtime_metrics_ready_stems.clear()

    def cache_key(self, kind, path):
        path = Path(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0
        return kind, str(path), mtime

    def render_colored_id_overlay(self, image, mask, selected_label=None, label_texts=None, centroids=None):
        return render_id_overlay(image, mask, selected_label=selected_label, label_texts=label_texts, centroids=centroids)

    def overlay_colored_mask_on_image(self, image, mask, selected_label=None, alpha=118):
        return render_colored_mask_overlay(image, mask, selected_label=selected_label, alpha=alpha)

    def show_image_file(self, path):
        image = self.load_image_as_rgb(path)
        self.set_label_pixmap(self.preview_label, image)

    def set_label_pixmap(self, label, image):
        from ui.widgets import qimage_from_pil

        qimage = qimage_from_pil(image)
        if qimage is None:
            return None
        source_pixmap = QPixmap.fromImage(qimage)
        pixmap = source_pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        # original image width (pixels)
        try:
            orig_width = qimage.width()
        except Exception:
            orig_width = source_pixmap.width()

        label._display_scale = pixmap.width() / max(1, orig_width)
        label._display_offset_x = (label.width() - pixmap.width()) / 2
        label._display_offset_y = (label.height() - pixmap.height()) / 2
        label.setPixmap(pixmap)

    def update_metric_panel(self, image_stem):
        if not getattr(self, "analysis_metric_labels", None):
            return
        row = getattr(self, "metrics_by_image", {}).get(image_stem) if image_stem else None
        values = {
            "Dice": "-",
            "IoU": "-",
            "Precision": "-",
            "Recall": "-",
            "GT objects": "-",
            "Pred objects": "-",
        }
        if row:
            values.update(
                {
                    "Dice": f"{float(row['dice']):.4f}",
                    "IoU": f"{float(row['iou']):.4f}",
                    "Precision": f"{float(row['precision']):.4f}",
                    "Recall": f"{float(row['recall']):.4f}",
                    "GT objects": row["gt_objects"],
                    "Pred objects": row["pred_objects"],
                }
            )
        for key, value in values.items():
            self.analysis_metric_labels[key].setText(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        stem = self.current_result_image_stem() if hasattr(self, "result_images_table") else None
        if stem:
            self.show_analysis_image(stem)
