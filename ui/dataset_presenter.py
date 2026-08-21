from pathlib import Path

from PyQt6.QtCore import QItemSelectionModel, QThread, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QComboBox, QHeaderView, QMessageBox, QTableWidgetItem

from services.paths import dataset_images_dir, dataset_masks_dir, dataset_plan_path
from services.conversion_scan import conversion_row_for_image_path, scan_conversion_input_rows
from services.dataset_plan import auto_split_indices, load_plan, save_plan
from services.dataset_service import (
    dataset_pair_removal_targets as collect_dataset_pair_removal_targets,
    dataset_plan_entry,
    dataset_row_matches_filters,
    dataset_selection_summary_text,
    remove_dataset_plan_entries as remove_dataset_entries_from_plan,
)
from workers.dataset_scan_worker import DatasetScanWorker


DATASET_CHECK_COL = 0
DATASET_NUMBER_COL = 1
DATASET_GROUP_COL = 2
DATASET_IMAGE_COL = 3
DATASET_STATUS_COL = 4


class DatasetPresenterMixin:
    def refresh_dataset_import(self):
        if not hasattr(self, "dataset_pairs_table"):
            return
        if self.dataset_scan_thread is not None:
            self.dataset_validation_summary.setText("Carregando dataset...")
            return

        input_dir = dataset_images_dir(self.config)
        input_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "conversion_input_label"):
            self.conversion_input_label.setText(str(input_dir))

        selected_image = self.pending_annotation_image_name
        if selected_image is None and self.dataset_pairs_table.currentRow() >= 0:
            current_item = self.dataset_pairs_table.item(self.dataset_pairs_table.currentRow(), DATASET_IMAGE_COL)
            if current_item is not None:
                selected_image = current_item.text()

        self.pending_dataset_selected_image = selected_image
        self.dataset_validation_summary.setText("Carregando dataset...")
        self.dataset_scan_thread = QThread(self)
        self.dataset_scan_worker = DatasetScanWorker(self.config)
        self.dataset_scan_worker.moveToThread(self.dataset_scan_thread)
        self.dataset_scan_thread.started.connect(self.dataset_scan_worker.run)
        self.dataset_scan_worker.finished.connect(self.finish_dataset_scan)
        self.dataset_scan_worker.finished.connect(self.dataset_scan_thread.quit)
        self.dataset_scan_worker.finished.connect(self.dataset_scan_worker.deleteLater)
        self.dataset_scan_thread.finished.connect(self.dataset_scan_thread.deleteLater)
        self.dataset_scan_thread.start()

    def finish_dataset_scan(self, rows, error):
        self.dataset_scan_thread = None
        self.dataset_scan_worker = None
        if error:
            self.dataset_validation_summary.setText(f"Erro ao carregar dataset:\n{error}")
            return
        self.populate_dataset_import(rows, getattr(self, "pending_dataset_selected_image", None))

    def populate_dataset_import(self, rows, selected_image=None):
        input_dir = dataset_images_dir(self.config)
        masks_dir = dataset_masks_dir(self.config)
        plan = self.load_dataset_plan()
        image_count = len(rows)
        valid_count = sum(1 for row in rows if row["status"] == "Com mascara")
        missing_count = sum(1 for row in rows if row["status"] == "Sem mascara")
        invalid_count = image_count - valid_count - missing_count
        removed_invalid_count = sum(1 for row in rows if row.get("removed_invalid_mask"))
        seg_count = len(list(masks_dir.glob("*_seg.npy")))
        tif_mask_count = (
            len(list(masks_dir.glob("*_masks.tif")))
            + len(list(masks_dir.glob("*_masks.tiff")))
        )
        selected_count = sum(
            1
            for row in rows
            if row["status"] in {"Com mascara", "Sem mascara"}
            and plan.get(row["image"], {}).get("group", "auto") != "uncategorized"
        )

        self.dataset_validation_summary.setText(
            f"Imagens: {image_count}\n"
            f"Mascaras: {seg_count + tif_mask_count}\n"
            f"Pares validos: {valid_count}\n"
            f"Selecionadas: {selected_count}\n"
            f"Sem mascara: {missing_count}\n"
            f"Mascaras removidas: {removed_invalid_count}\n"
            f"Outros status: {invalid_count}"
        )

        self.dataset_pairs_table.setUpdatesEnabled(False)
        self.dataset_pairs_table.blockSignals(True)
        self.bulk_updating_dataset_selection = True
        try:
            self.dataset_pairs_table.setRowCount(len(rows))
            for row_index, row in enumerate(rows):
                saved = plan.get(row["image"], {})
                can_include = row["status"] in {"Com mascara", "Sem mascara"}
                group = saved.get("group", "auto")

                check_item = QTableWidgetItem()
                check_item.setFlags(
                    (check_item.flags() | Qt.ItemFlag.ItemIsUserCheckable) & ~Qt.ItemFlag.ItemIsEditable
                )
                check_item.setCheckState(Qt.CheckState.Unchecked)
                check_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.dataset_pairs_table.setItem(row_index, DATASET_CHECK_COL, check_item)

                number_item = QTableWidgetItem(str(row_index + 1))
                number_item.setFlags(number_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                number_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                number_item.setData(Qt.ItemDataRole.UserRole, row)
                self.dataset_pairs_table.setItem(row_index, DATASET_NUMBER_COL, number_item)

                group_combo = QComboBox()
                group_options = [
                    ("uncategorized", "Sem categoria"),
                    ("auto", "Auto"),
                    ("train", "Treino"),
                    ("val", "Validacao"),
                    ("test", "Teste"),
                ]
                for key, label in group_options:
                    group_combo.addItem(label, key)
                group_index = group_combo.findData(group)
                group_combo.setCurrentIndex(group_index if group_index >= 0 else 0)
                group_combo.setEnabled(can_include)
                group_combo.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                group_combo.currentIndexChanged.connect(
                    lambda _index, selected_row=row_index: self.on_dataset_group_changed(selected_row)
                )
                self.dataset_pairs_table.setCellWidget(row_index, DATASET_GROUP_COL, group_combo)

                values = [row["image"], row["status"]]
                for col, value in enumerate(values):
                    item = QTableWidgetItem(value)
                    if col == 1:
                        self.apply_dataset_status_style(item, value)
                    item.setData(Qt.ItemDataRole.UserRole, row)
                    self.dataset_pairs_table.setItem(row_index, col + DATASET_IMAGE_COL, item)
                self.dataset_pairs_table.setRowHeight(row_index, 30)

            for row_index, row in enumerate(rows):
                saved = plan.get(row["image"], {})
                can_include = row["status"] in {"Com mascara", "Sem mascara"}
                in_dataset = can_include and saved.get("group", "auto") != "uncategorized"
                if in_dataset:
                    index = self.dataset_pairs_table.model().index(row_index, DATASET_IMAGE_COL)
                    self.dataset_pairs_table.selectionModel().select(
                        index,
                        QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows,
                    )
        finally:
            self.bulk_updating_dataset_selection = False
            self.dataset_pairs_table.blockSignals(False)
            self.dataset_pairs_table.setUpdatesEnabled(True)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(DATASET_CHECK_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(DATASET_NUMBER_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(DATASET_GROUP_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(DATASET_IMAGE_COL, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(DATASET_STATUS_COL, QHeaderView.ResizeMode.ResizeToContents)
        self.apply_dataset_filter()
        if rows:
            selected_row = 0
            if selected_image:
                for row_index, row in enumerate(rows):
                    if row["image"] == selected_image:
                        selected_row = row_index
                        break
            current_index = self.dataset_pairs_table.model().index(selected_row, DATASET_IMAGE_COL)
            self.dataset_pairs_table.selectionModel().setCurrentIndex(
                current_index,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
            self.show_selected_dataset_pair()
        else:
            self.dataset_preview_label.setText("Nenhuma imagem encontrada.")
            self.dataset_preview_label.setPixmap(QPixmap())

    def scan_conversion_input(self):
        return scan_conversion_input_rows(self.config)

    def conversion_row_for_image(self, image_path):
        masks_dir = dataset_masks_dir(self.config) if image_path.parent == dataset_images_dir(self.config) else image_path.parent
        return conversion_row_for_image_path(image_path, masks_dir)

    def refresh_dataset_row_for_image(self, image_name):
        if not hasattr(self, "dataset_pairs_table"):
            return False
        target_row = -1
        for row in range(self.dataset_pairs_table.rowCount()):
            image_item = self.dataset_pairs_table.item(row, DATASET_IMAGE_COL)
            if image_item is not None and image_item.text() == image_name:
                target_row = row
                break
        if target_row < 0:
            return False

        row_data = self.dataset_pair_row_data(target_row)
        image_path = Path(row_data.get("image_path", "")) if row_data else dataset_images_dir(self.config) / image_name
        if not image_path.exists():
            return False
        row_data = self.conversion_row_for_image(image_path)
        can_include = row_data["status"] in {"Com mascara", "Sem mascara"}

        self.dataset_pairs_table.blockSignals(True)
        group_combo = self.dataset_pairs_table.cellWidget(target_row, DATASET_GROUP_COL)
        if group_combo:
            group_combo.setEnabled(can_include)

        for col, value in [(DATASET_IMAGE_COL, row_data["image"]), (DATASET_STATUS_COL, row_data["status"])]:
            item = self.dataset_pairs_table.item(target_row, col)
            if item is None:
                item = QTableWidgetItem()
                self.dataset_pairs_table.setItem(target_row, col, item)
            item.setText(value)
            if col == DATASET_STATUS_COL:
                self.apply_dataset_status_style(item, value)
            item.setData(Qt.ItemDataRole.UserRole, row_data)
        self.dataset_pairs_table.blockSignals(False)

        self.pending_annotation_image_name = image_name
        self.update_dataset_selection_summary()
        self.apply_dataset_filter()
        if self.dataset_pairs_table.currentRow() == target_row:
            self.show_dataset_preview(row_data)
        return True

    def apply_dataset_status_style(self, item, status):
        if status == "Com mascara":
            item.setForeground(QColor("#16803a"))
        elif status == "Sem mascara":
            item.setForeground(QColor("#b42318"))
        else:
            item.setForeground(QColor("#1f2933"))

    def load_dataset_plan(self):
        return load_plan(dataset_plan_path(self.config))

    def save_dataset_plan_from_table(self):
        if not hasattr(self, "dataset_pairs_table") or self.dataset_pairs_table.signalsBlocked():
            return
        entries = self.dataset_plan_entries_from_table()
        save_plan(dataset_plan_path(self.config), entries)
        self.update_dataset_selection_summary()

    def on_dataset_table_selection_changed(self):
        if getattr(self, "bulk_updating_dataset_selection", False):
            return
        self.save_dataset_plan_from_table()

    def on_dataset_group_changed(self, row):
        if self.bulk_updating_dataset_groups:
            return
        self.save_dataset_plan_from_table()
        self.result_entries_cache = None
        if hasattr(self, "result_images_table"):
            self.refresh_analysis_images()

    def selected_dataset_rows(self):
        if not hasattr(self, "dataset_pairs_table"):
            return []
        return sorted({index.row() for index in self.dataset_pairs_table.selectedIndexes()})

    def visible_dataset_rows(self):
        if not hasattr(self, "dataset_pairs_table"):
            return []
        return [
            row
            for row in range(self.dataset_pairs_table.rowCount())
            if not self.dataset_pairs_table.isRowHidden(row)
        ]

    def checked_dataset_rows(self):
        if not hasattr(self, "dataset_pairs_table"):
            return []
        rows = []
        for row in range(self.dataset_pairs_table.rowCount()):
            item = self.dataset_pairs_table.item(row, DATASET_CHECK_COL)
            if item is not None and item.checkState() == Qt.CheckState.Checked:
                rows.append(row)
        return rows

    def move_selected_dataset_rows_to_group(self, group=None):
        rows = self.checked_dataset_rows() or self.selected_dataset_rows()
        if not rows:
            QMessageBox.information(self, "Mover grupo", "Selecione uma ou mais imagens na tabela.")
            return
        if group is None:
            group = self.dataset_move_group_combo.currentData()
        changed = 0
        self.dataset_pairs_table.blockSignals(True)
        self.bulk_updating_dataset_groups = True
        try:
            for row in rows:
                if self.dataset_pairs_table.isRowHidden(row):
                    continue
                combo = self.dataset_pairs_table.cellWidget(row, DATASET_GROUP_COL)
                if combo is None or not combo.isEnabled():
                    continue
                index = combo.findData(group)
                if index >= 0 and combo.currentIndex() != index:
                    combo.setCurrentIndex(index)
                    changed += 1
        finally:
            self.bulk_updating_dataset_groups = False
            self.dataset_pairs_table.blockSignals(False)
        if changed == 0:
            QMessageBox.information(self, "Mover grupo", "Nenhuma imagem selecionada pode mudar para esse grupo.")
            return
        self.save_dataset_plan_from_table()
        self.result_entries_cache = None
        if hasattr(self, "result_images_table"):
            self.refresh_analysis_images()
        self.dataset_validation_summary.setText(
            self.dataset_validation_summary.text() + f"\nGrupo alterado em {changed} imagem(ns)."
        )

    def apply_dataset_filter(self):
        if not hasattr(self, "dataset_pairs_table"):
            return
        filters = {
            "text": self.dataset_filter.text().strip().lower() if hasattr(self, "dataset_filter") else "",
            "status": self.dataset_status_filter.currentData() if hasattr(self, "dataset_status_filter") else "",
            "group": self.dataset_group_filter.currentData() if hasattr(self, "dataset_group_filter") else "",
            "include": self.dataset_include_filter.currentData() if hasattr(self, "dataset_include_filter") else "",
        }
        first_visible = -1
        for row in range(self.dataset_pairs_table.rowCount()):
            row_data = self.dataset_pair_row_data(row) or {}
            group_combo = self.dataset_pairs_table.cellWidget(row, DATASET_GROUP_COL)
            group_text = group_combo.currentText().lower() if group_combo else ""
            group_value = group_combo.currentData() if group_combo and group_combo.currentData() else ""
            is_selected = (
                group_value not in ("", "uncategorized")
                and row_data.get("status") in {"Com mascara", "Sem mascara"}
            )
            visible = dataset_row_matches_filters(
                row + 1,
                row_data,
                group_text,
                group_value,
                is_selected,
                filters,
            )
            self.dataset_pairs_table.setRowHidden(row, not visible)
            if visible and first_visible < 0:
                first_visible = row
        if first_visible >= 0 and self.dataset_pairs_table.currentRow() >= 0:
            current_row = self.dataset_pairs_table.currentRow()
            if self.dataset_pairs_table.isRowHidden(current_row):
                current_index = self.dataset_pairs_table.model().index(first_visible, DATASET_IMAGE_COL)
                self.dataset_pairs_table.selectionModel().setCurrentIndex(
                    current_index,
                    QItemSelectionModel.SelectionFlag.NoUpdate,
                )
        self.update_dataset_selection_summary()

    def clear_dataset_filters(self):
        if hasattr(self, "dataset_filter"):
            self.dataset_filter.clear()
        for combo_name in ["dataset_status_filter", "dataset_group_filter", "dataset_include_filter"]:
            if hasattr(self, combo_name):
                getattr(self, combo_name).setCurrentIndex(0)
        self.apply_dataset_filter()

    def update_dataset_selection_summary(self):
        if not hasattr(self, "dataset_validation_summary"):
            return
        visible = sum(
            1
            for row in range(self.dataset_pairs_table.rowCount())
            if not self.dataset_pairs_table.isRowHidden(row)
        )
        self.dataset_validation_summary.setText(
            dataset_selection_summary_text(self.dataset_plan_entries_from_table(), visible)
        )

    def dataset_plan_entries_from_table(self):
        entries = []
        for row in range(self.dataset_pairs_table.rowCount()):
            status_item = self.dataset_pairs_table.item(row, DATASET_STATUS_COL)
            group_combo = self.dataset_pairs_table.cellWidget(row, DATASET_GROUP_COL)
            image_item = self.dataset_pairs_table.item(row, DATASET_IMAGE_COL)
            if status_item is None or image_item is None:
                continue
            entries.append(
                dataset_plan_entry(
                    image_item.text(),
                    group_combo.currentData() if group_combo else "uncategorized",
                    status_item.text(),
                )
            )
        return entries

    def dataset_pair_row_data(self, row):
        if not hasattr(self, "dataset_pairs_table") or row < 0:
            return None
        item = self.dataset_pairs_table.item(row, DATASET_IMAGE_COL)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def selected_dataset_pair_row(self):
        if not hasattr(self, "dataset_pairs_table"):
            return -1
        return self.dataset_pairs_table.currentRow()

    def dataset_pair_removal_targets(self, row_data):
        return collect_dataset_pair_removal_targets(row_data)

    def remove_dataset_plan_entries(self, image_names):
        return remove_dataset_entries_from_plan(dataset_plan_path(self.config), image_names)

    def dataset_delete_confirmation(self, image_names, targets):
        count = len(image_names)
        if count == 1:
            title = "Deletar imagem"
            summary = f"Deletar a imagem {image_names[0]}?"
            details = "\n".join(f"- {path.name}" for path in targets)
        elif count <= 3:
            title = "Deletar imagens"
            summary = f"Deletar estas {count} imagens?\n\n" + "\n".join(f"- {name}" for name in image_names)
            details = "\n".join(f"- {path.name}" for path in targets)
        else:
            title = "Deletar imagens"
            summary = f"Deletar {count} imagens?"
            details = f"Arquivos que serao removidos:\n" + "\n".join(f"- {path.name}" for path in targets)
        return title, summary, details

    def delete_selected_dataset_pair(self):
        rows = self.checked_dataset_rows() or self.selected_dataset_rows()
        if not rows:
            row = self.selected_dataset_pair_row()
            rows = [row] if row >= 0 else []
        if not rows:
            QMessageBox.information(self, "Deletar conjunto", "Selecione uma ou mais imagens na tabela para deletar.")
            return

        row_data_list = [self.dataset_pair_row_data(row) for row in rows]
        row_data_list = [row_data for row_data in row_data_list if row_data]
        if not row_data_list:
            QMessageBox.information(self, "Deletar conjunto", "Nenhuma imagem selecionada pode ser deletada.")
            return

        image_names = [row_data["image"] for row_data in row_data_list]
        targets = [path for row_data in row_data_list for path in self.dataset_pair_removal_targets(row_data)]
        title, summary, details = self.dataset_delete_confirmation(image_names, targets)
        reply = QMessageBox.question(
            self,
            title,
            (
                f"{summary}\n\n"
                f"{details}\n\n"
                "Essa acao nao pode ser desfeita."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        deleted_paths = []
        missing_paths = []
        failed_paths = []
        for target_path in targets:
            if not target_path.exists():
                missing_paths.append(target_path)
                continue
            try:
                target_path.unlink()
                deleted_paths.append(target_path)
            except OSError as exc:
                failed_paths.append(f"{target_path.name}: {exc}")

        removed_plan_entries = self.remove_dataset_plan_entries(set(image_names))
        self.pending_annotation_image_name = None

        self.dataset_pairs_table.blockSignals(True)
        for row in sorted(rows, reverse=True):
            if 0 <= row < self.dataset_pairs_table.rowCount():
                self.dataset_pairs_table.removeRow(row)
        self.dataset_pairs_table.blockSignals(False)
        if self.dataset_pairs_table.rowCount() > 0:
            next_row = min(rows[0], self.dataset_pairs_table.rowCount() - 1)
            current_index = self.dataset_pairs_table.model().index(next_row, DATASET_IMAGE_COL)
            self.dataset_pairs_table.selectionModel().setCurrentIndex(
                current_index,
                QItemSelectionModel.SelectionFlag.NoUpdate,
            )
        self.update_dataset_selection_summary()

        self.append_log(
            f"\n>>> Deletar conjunto imagem/mascara\n"
            f"Imagens: {', '.join(image_names)}\n"
            f"Arquivos removidos: {len(deleted_paths)}\n"
            f"Arquivos ausentes: {len(missing_paths)}\n"
            f"Entradas removidas do plano: {removed_plan_entries}\n"
        )

        if failed_paths:
            QMessageBox.warning(
                self,
                "Deletar conjunto",
                "Alguns arquivos nao puderam ser removidos:\n\n" + "\n".join(failed_paths),
            )

    def auto_split_dataset_table(self):
        assignments = auto_split_indices(self.dataset_plan_entries_from_table())

        self.dataset_pairs_table.blockSignals(True)
        self.bulk_updating_dataset_groups = True
        try:
            for row, group in assignments.items():
                combo = self.dataset_pairs_table.cellWidget(row, DATASET_GROUP_COL)
                if combo:
                    index = combo.findData(group)
                    if index >= 0:
                        combo.setCurrentIndex(index)
        finally:
            self.bulk_updating_dataset_groups = False
            self.dataset_pairs_table.blockSignals(False)
        self.save_dataset_plan_from_table()
        self.result_entries_cache = None
        if hasattr(self, "result_images_table"):
            self.refresh_analysis_images()

    def on_dataset_pair_current_cell_changed(self, current_row, _current_column, _previous_row, _previous_column):
        if current_row < 0:
            return
        self.show_selected_dataset_pair()
