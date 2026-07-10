from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QTableWidgetItem


class ResultsPresenterMixin:
    def refresh_analysis_images(self):
        if not hasattr(self, "result_images_table"):
            return
        self.clear_result_indexes()
        selected = self.current_result_image_stem()
        entries = self.result_image_entries()
        self.build_result_status_index(entries)
        self.result_row_by_stem = {}
        self.result_images_table.blockSignals(True)
        self.result_images_table.setRowCount(len(entries))
        for row_index, stem in enumerate(entries):
            self.result_row_by_stem[stem] = row_index

            check_item = QTableWidgetItem()
            check_item.setFlags(
                (check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable
            )
            check_item.setCheckState(Qt.CheckState.Unchecked)
            check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_images_table.setItem(row_index, 0, check_item)

            image_item = QTableWidgetItem(stem)
            image_item.setData(Qt.ItemDataRole.UserRole, stem)
            self.result_images_table.setItem(row_index, 1, image_item)

            overlay_item = self.result_status_item(self.result_overlay_exists(stem))
            overlay_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_images_table.setItem(row_index, 2, overlay_item)

            metrics_item = self.result_status_item(self.result_metrics_exists(stem))
            metrics_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_images_table.setItem(row_index, 3, metrics_item)
        self.result_images_table.blockSignals(False)
        if hasattr(self, "results_list_status"):
            overlay_count = len(self.result_status_index.get("overlays", set()))
            metrics_count = len(self.result_status_index.get("metrics", set()))
            model_name = self.config.get("active_model") or "nenhum modelo"
            self.results_list_status.setText(
                f"{len(entries)} imagem(ns) para {model_name}. "
                f"Overlays: {overlay_count} | Metricas: {metrics_count}."
            )
        if selected:
            row = self.result_table_row_for_stem(selected)
            if row >= 0:
                self.result_images_table.setCurrentCell(row, 1)
            elif self.result_images_table.rowCount() > 0:
                self.result_images_table.setCurrentCell(0, 1)
            else:
                self.preview_label.setText("Nenhuma imagem encontrada.")
                self.preview_label.setPixmap(QPixmap())
        elif self.result_images_table.rowCount() > 0:
            self.result_images_table.setCurrentCell(0, 1)
        else:
            self.preview_label.setText("Nenhuma imagem encontrada.")
            self.preview_label.setPixmap(QPixmap())

    def show_result_table_row(self, row):
        if row < 0:
            return
        stem = self.result_table_stem(row)
        if stem:
            self.show_analysis_image(stem)

    def result_status_item(self, exists):
        item = QTableWidgetItem("âœ“" if exists else "âœ–")
        item.setForeground(QColor("#00b341" if exists else "#e00000"))
        item.setText("OK" if exists else "X")
        font = item.font()
        font.setBold(True)
        item.setFont(font)
        return item

    def result_table_stem(self, row):
        if not hasattr(self, "result_images_table") or row < 0:
            return None
        item = self.result_images_table.item(row, 1)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def result_table_row_for_stem(self, stem):
        if not hasattr(self, "result_images_table"):
            return -1
        cached_row = getattr(self, "result_row_by_stem", {}).get(stem)
        if cached_row is not None:
            return cached_row
        for row in range(self.result_images_table.rowCount()):
            if self.result_table_stem(row) == stem:
                return row
        return -1

    def checked_result_image_stems(self):
        if not hasattr(self, "result_images_table"):
            return []
        stems = []
        for row in range(self.result_images_table.rowCount()):
            check_item = self.result_images_table.item(row, 0)
            if check_item is None or check_item.checkState() != Qt.CheckState.Checked:
                continue
            stem = self.result_table_stem(row)
            if stem:
                stems.append(stem)
        return stems

