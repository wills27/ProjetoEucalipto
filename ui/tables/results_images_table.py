from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QTableWidget

from ui import components

# Coluna 0 e o checkbox de acao em lote (marcar imagens pra gerar/excluir em
# lote), separado do destaque de linha do Qt usado so pra escolher o preview.
CHECK_COLUMN = 0
IMAGE_COLUMN = 1


class ResultsImagesTable(QTableWidget):
    def __init__(self, actions=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.actions = actions or {}
        self.setHorizontalHeader(components.make_checkbox_header(CHECK_COLUMN, self))
        self.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

    def _visible_rows_all_checked(self):
        visible_rows = [r for r in range(self.rowCount()) if not self.isRowHidden(r)]
        return visible_rows, all(
            self.item(r, CHECK_COLUMN) is not None
            and self.item(r, CHECK_COLUMN).checkState() == Qt.CheckState.Checked
            for r in visible_rows
        )

    def _sync_header_checked(self):
        """Recalcula o estado do quadrado do cabecalho a partir das linhas
        visiveis, para nao ficar dessincronizado quando uma linha e marcada
        individualmente (fora do clique no proprio cabecalho)."""
        _, all_checked = self._visible_rows_all_checked()
        self.horizontalHeader().set_checked(all_checked)

    def _on_header_clicked(self, section):
        if section != CHECK_COLUMN:
            return
        visible_rows, all_checked = self._visible_rows_all_checked()
        new_state = Qt.CheckState.Unchecked if all_checked else Qt.CheckState.Checked
        self.blockSignals(True)
        for r in visible_rows:
            item = self.item(r, CHECK_COLUMN)
            if item is not None:
                item.setCheckState(new_state)
        self.blockSignals(False)
        self.horizontalHeader().set_checked(new_state == Qt.CheckState.Checked)

    def mousePressEvent(self, event):
        index = self.indexAt(event.pos())
        if index.isValid() and index.column() == CHECK_COLUMN and event.button() == Qt.MouseButton.LeftButton:
            item = self.item(index.row(), CHECK_COLUMN)
            if item is not None:
                checked = item.checkState() == Qt.CheckState.Checked
                item.setCheckState(Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked)
                self._sync_header_checked()
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
            recalc_metrics_action = menu.addAction("Recalcular metricas selecionadas")
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
