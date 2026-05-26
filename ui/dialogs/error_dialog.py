from PyQt6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLabel, QPushButton, QTextEdit, QVBoxLayout


class ErrorDialog(QDialog):
    def __init__(self, parent, title, message, details=""):
        super().__init__(parent)
        self.setWindowTitle(title or "Erro")
        self.resize(680, 420)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        header = QLabel(title or "Erro")
        header.setObjectName("errorTitle")
        header.setWordWrap(True)
        layout.addWidget(header)

        body = QLabel(message or "Ocorreu um erro inesperado.")
        body.setObjectName("errorMessage")
        body.setWordWrap(True)
        layout.addWidget(body)

        self.details_text = QTextEdit()
        self.details_text.setObjectName("errorDetails")
        self.details_text.setReadOnly(True)
        self.details_text.setPlainText(details or message or "")
        layout.addWidget(self.details_text, 1)

        actions = QHBoxLayout()
        copy_button = QPushButton("Copiar detalhes")
        copy_button.clicked.connect(self.copy_details)
        close_button = QPushButton("Fechar")
        close_button.setObjectName("primary")
        close_button.clicked.connect(self.accept)
        actions.addWidget(copy_button)
        actions.addStretch()
        actions.addWidget(close_button)
        layout.addLayout(actions)

    def copy_details(self):
        QApplication.clipboard().setText(self.details_text.toPlainText())
