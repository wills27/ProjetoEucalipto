from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QTableWidget


class DatasetPairsTable(QTableWidget):
    def __init__(self, delete_callback, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delete_callback = delete_callback
        self.select_visible_callback = None
        self.clear_action_selection_callback = None

    def contextMenuEvent(self, event):
        row = self.rowAt(event.pos().y())
        if row < 0:
            super().contextMenuEvent(event)
            return

        self.selectRow(row)
        menu = QMenu(self)
        delete_action = menu.addAction("Deletar")
        chosen_action = menu.exec(event.globalPos())
        if chosen_action == delete_action and self.delete_callback:
            self.delete_callback()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space:
            row = self.currentRow()
            if row >= 0:
                item = self.item(row, 1)
                if item is not None and (item.flags() & Qt.ItemFlag.ItemIsEnabled):
                    next_state = (
                        Qt.CheckState.Unchecked
                        if item.checkState() == Qt.CheckState.Checked
                        else Qt.CheckState.Checked
                    )
                    self.set_action_checked(row, next_state)
                    event.accept()
                    return
        if event.key() == Qt.Key.Key_Delete and self.delete_callback:
            self.delete_callback()
            event.accept()
            return
        super().keyPressEvent(event)

    def set_action_checked(self, row, state):
        item = self.item(row, 1)
        if item is None or not (item.flags() & Qt.ItemFlag.ItemIsEnabled):
            return
        item.setCheckState(state)
