from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QApplication, QTableWidgetItem


class ResultsPresenterMixin:
    def refresh_analysis_images(self):
        if not hasattr(self, "result_images_table"):
            return
        self.clear_result_indexes()
        selected = self.current_result_image_stem()
        checked_stems = set(self.checked_result_image_stems())
        entries = self.result_image_entries()
        self.build_result_status_index(entries)
        self.result_row_by_stem = {}
        self.result_images_table.blockSignals(True)
        self.result_images_table.setRowCount(len(entries))
        for row_index, stem in enumerate(entries):
            self.result_row_by_stem[stem] = row_index
            check_item = QTableWidgetItem()
            check_item.setFlags(
                check_item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setFlags(check_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            check_item.setCheckState(
                Qt.CheckState.Checked if stem in checked_stems else Qt.CheckState.Unchecked
            )
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

    def on_result_image_check_changed(self, item):
        if item.column() != 0:
            return
        row = item.row()
        state = item.checkState()
        modifiers = QApplication.keyboardModifiers()
        rows = []

        if modifiers & Qt.KeyboardModifier.ShiftModifier and self.last_result_check_row is not None:
            start = min(self.last_result_check_row, row)
            end = max(self.last_result_check_row, row)
            rows = list(range(start, end + 1))
        elif modifiers & Qt.KeyboardModifier.ControlModifier:
            rows = sorted({index.row() for index in self.result_images_table.selectedIndexes()})

        if rows:
            self.set_result_rows_checked(rows, state)

        self.last_result_check_row = row

    def set_result_rows_checked(self, rows, state):
        if not hasattr(self, "result_images_table"):
            return
        self.result_images_table.blockSignals(True)
        for row in rows:
            check_item = self.result_images_table.item(row, 0)
            if check_item:
                check_item.setCheckState(state)
        self.result_images_table.blockSignals(False)

    def on_result_images_header_clicked(self, section):
        if section != 0 or not hasattr(self, "result_images_table"):
            return
        total = self.result_images_table.rowCount()
        if total == 0:
            return
        checked = len(self.checked_result_image_stems())
        state = Qt.CheckState.Unchecked if checked > total / 2 else Qt.CheckState.Checked
        self.set_result_rows_checked(range(total), state)

    def sync_result_checkboxes_from_selection(self):
        if not hasattr(self, "result_images_table"):
            return
        selected_rows = sorted({index.row() for index in self.result_images_table.selectedIndexes()})
        if len(selected_rows) <= 1:
            return
        self.set_result_rows_checked(selected_rows, Qt.CheckState.Checked)

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
            stem = self.result_table_stem(row)
            if stem and check_item and check_item.checkState() == Qt.CheckState.Checked:
                stems.append(stem)
        return stems

