from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QTableWidget

# Coluna 0 e o checkbox de acao em lote (marcar imagens pra gerar/excluir em
# lote), separado do destaque de linha do Qt usado so pra escolher o preview.
CHECK_COLUMN = 0
IMAGE_COLUMN = 1


class ResultsImagesTable(QTableWidget):
    def __init__(self, actions=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actions = actions or {}

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid() and index.column() == CHECK_COLUMN and event.button() == Qt.MouseButton.LeftButton:
            item = self.item(index.row(), CHECK_COLUMN)
            if item is not None:
                checked = item.checkState() == Qt.CheckState.Checked
                item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
                event.accept()
                return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        row = self.rowAt(event.pos().y())
        if row >= 0 and not self.selectionModel().isRowSelected(row, self.rootIndex()):
            self.selectRow(row)
            self.setCurrentCell(row, IMAGE_COLUMN)

        menu = QMenu(self)
        import_action = menu.addAction("Importar imagens")
        refresh_action = menu.addAction("Recarregar imagens")

        has_row = row >= 0
        if has_row:
            menu.addSeparator()
            generate_current_action = menu.addAction("Gerar resultado da imagem")
            generate_selected_action = menu.addAction("Gerar resultados selecionados")
            edit_mask_action = menu.addAction("Editar mascara")
            recalc_metrics_action = menu.addAction("Recalcular metrica")
            menu.addSeparator()
            remove_action = menu.addAction("Excluir imagem")
        else:
            generate_current_action = None
            generate_selected_action = None
            edit_mask_action = None
            recalc_metrics_action = None
            remove_action = None

        chosen_action = menu.exec(event.globalPos())
        callbacks = self.actions
        if chosen_action == import_action:
            callbacks.get("import", lambda: None)()
        elif chosen_action == refresh_action:
            callbacks.get("refresh", lambda: None)()
        elif has_row and chosen_action == generate_current_action:
            callbacks.get("generate_current", lambda: None)()
        elif has_row and chosen_action == generate_selected_action:
            callbacks.get("generate_selected", lambda: None)()
        elif has_row and chosen_action == edit_mask_action:
            callbacks.get("edit_mask", lambda: None)()
        elif has_row and chosen_action == recalc_metrics_action:
            callbacks.get("recalc_metrics", lambda: None)()
        elif has_row and chosen_action == remove_action:
            callbacks.get("remove", lambda: None)()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            callback = self.actions.get("remove")
            if callback:
                callback()
                event.accept()
                return
        super().keyPressEvent(event)
