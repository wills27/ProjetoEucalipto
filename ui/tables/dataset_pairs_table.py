from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMenu, QTableWidget


class DatasetPairsTable(QTableWidget):
    def __init__(self, delete_callback, move_callback=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.delete_callback = delete_callback
        self.move_callback = move_callback
        self.select_visible_callback = None
        self.clear_action_selection_callback = None

    def contextMenuEvent(self, event):
        row = self.rowAt(event.pos().y())
        if row < 0:
            super().contextMenuEvent(event)
            return

        if not self.selectionModel().isRowSelected(row, self.rootIndex()):
            self.selectRow(row)
        menu = QMenu(self)
        delete_action = menu.addAction("Deletar selecionadas")
        move_menu = None
        move_actions = {}
        if self.move_callback:
            menu.addSeparator()
            move_menu = menu.addMenu("Mover para grupo")
            for group_value, label in [
                ("uncategorized", "Sem categoria"),
                ("auto", "Auto"),
                ("train", "Treino"),
                ("val", "Validacao"),
                ("test", "Teste"),
            ]:
                move_actions[move_menu.addAction(label)] = group_value
        chosen_action = menu.exec(event.globalPos())
        if chosen_action == delete_action and self.delete_callback:
            self.delete_callback()
        elif chosen_action in move_actions and self.move_callback:
            self.move_callback(move_actions[chosen_action])
        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete and self.delete_callback:
            self.delete_callback()
            event.accept()
            return
        super().keyPressEvent(event)
