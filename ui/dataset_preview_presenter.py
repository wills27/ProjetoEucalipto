from pathlib import Path
import traceback

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QMessageBox

from services.annotation import validate_mask_file
from services.dataset_preview import build_dataset_preview_image
from ui.mask_edit_target import DatasetMaskTarget


class DatasetPreviewPresenterMixin:
    def show_selected_dataset_pair(self):
        row = self.dataset_pairs_table.currentRow()
        if row < 0:
            return
        # column 4 holds the image item (Imagem)
        item = self.dataset_pairs_table.item(row, 4)
        if item is None:
            return
        row_data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.show_dataset_preview(row_data)

    def show_dataset_preview(self, row_data):
        image_path = Path(row_data.get("image_path", ""))
        if not image_path.exists():
            self.dataset_preview_label.setText("Imagem nao encontrada.")
            self.dataset_preview_label.setPixmap(QPixmap())
            return
        try:
            preview_size = (
                max(1, self.dataset_preview_label.width()),
                max(1, self.dataset_preview_label.height()),
            )
            image = build_dataset_preview_image(row_data, preview_size)
            if image is None:
                self.dataset_preview_label.setText("Imagem nao encontrada.")
                self.dataset_preview_label.setPixmap(QPixmap())
                return
            self.set_dataset_preview_pixmap(image)
            self.dataset_preview_info.setText(
                f"{image_path.name}\n{row_data.get('status', '')}\nDuplo clique para editar a mascara."
            )
        except Exception as exc:
            self.dataset_preview_label.setText(f"Nao foi possivel carregar preview:\n{exc}")
            self.dataset_preview_label.setPixmap(QPixmap())
            self.show_error(
                "Erro ao carregar preview",
                "Nao foi possivel carregar a imagem de preview.",
                traceback.format_exc(),
            )

    def set_dataset_preview_pixmap(self, image):
        from ui.widgets import qimage_from_pil

        qimage = qimage_from_pil(image)
        if qimage is None:
            self.dataset_preview_label.setText("Nao foi possivel converter a imagem para preview.")
            self.dataset_preview_label.setPixmap(QPixmap())
            return
        pixmap = QPixmap.fromImage(qimage)
        self.dataset_preview_label._display_scale = 1.0
        self.dataset_preview_label._display_offset_x = 0
        self.dataset_preview_label._display_offset_y = 0
        self.dataset_preview_label.setPixmap(pixmap)

    def select_dataset_annotation_row(self, row_data):
        if not hasattr(self, "annotation_page"):
            return
        image_path = Path(row_data.get("image_path", ""))
        if not image_path.exists():
            return
        seg_path = Path(row_data.get("seg_path", ""))
        tif_mask_path = Path(row_data.get("tif_mask_path", ""))
        validation = validate_mask_file(seg_path, tif_mask_path)
        has_mask = validation["valid"]
        target = DatasetMaskTarget(
            path=image_path,
            seg_path=seg_path,
            tif_mask_path=tif_mask_path,
            has_mask=has_mask,
            label="[Com mascara]" if has_mask else "[Sem mascara]",
            window=self,
        )
        self.annotation_page.show_image(target)

    def open_selected_dataset_editor(self):
        row = self.dataset_pairs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Editar mascara", "Selecione uma imagem na tabela.")
            return
        item = self.dataset_pairs_table.item(row, 4)
        if item is None:
            return
        row_data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.select_dataset_annotation_row(row_data)
        self.annotation_page.open_editor()
