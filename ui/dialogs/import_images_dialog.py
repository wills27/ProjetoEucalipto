from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QRadioButton,
    QVBoxLayout,
)


class ImportImagesDialog(QDialog):
    """
    Dialog unificado de importação de imagens.

    Parâmetros
    ----------
    allow_files : bool
        Se True, exibe opção de importar arquivos individuais além de pasta.
    show_prefix : bool
        Se True, exibe opção de usar nome das subpastas como prefixo.
    defaults : dict
        Valores iniciais para os campos (lidos do config pelo chamador).
    """

    def __init__(self, parent, allow_files=True, show_prefix=False, defaults=None):
        super().__init__(parent)
        defaults = defaults or {}
        self.setWindowTitle("Importar imagens")
        self.setModal(True)
        self.setMinimumWidth(380)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Modo: arquivos / pasta
        self._files_radio = None
        self._folder_radio = None
        if allow_files:
            mode_box = QFrame()
            mode_box.setObjectName("dialogSection")
            mode_layout = QVBoxLayout(mode_box)
            mode_layout.setContentsMargins(12, 10, 12, 10)
            mode_layout.setSpacing(8)
            self._mode_group = QButtonGroup(self)
            self._files_radio = QRadioButton("Imagens selecionadas")
            self._folder_radio = QRadioButton("Pasta")
            self._files_radio.setObjectName("choice")
            self._folder_radio.setObjectName("choice")
            self._mode_group.addButton(self._files_radio)
            self._mode_group.addButton(self._folder_radio)
            self._files_radio.setChecked(True)
            row = QHBoxLayout()
            row.setSpacing(18)
            row.addWidget(self._files_radio)
            row.addWidget(self._folder_radio)
            row.addStretch()
            mode_layout.addLayout(row)
            layout.addWidget(mode_box)

        # Opções
        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(8)

        self._skip_keyword = QLineEdit(str(defaults.get("skip_keyword", "")))
        self._skip_keyword.setPlaceholderText("mask, overlay, temp")
        form.addRow("Ignorar contendo", self._skip_keyword)

        self._recursive = QCheckBox("Incluir subpastas")
        self._recursive.setChecked(bool(defaults.get("recursive", True)))
        form.addRow("", self._recursive)

        self._grayscale = QCheckBox("Converter para cinza")
        self._grayscale.setChecked(bool(defaults.get("grayscale", False)))
        form.addRow("", self._grayscale)

        self._prefix = None
        if show_prefix:
            self._prefix = QCheckBox("Usar nome das pastas como prefixo")
            self._prefix.setChecked(bool(defaults.get("prefix", False)))
            form.addRow("", self._prefix)

        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Continuar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        if allow_files:
            self._files_radio.toggled.connect(self._update_folder_options)
            self._update_folder_options()

    def _update_folder_options(self):
        folder_mode = self._folder_radio.isChecked()
        self._recursive.setEnabled(folder_mode)
        self._skip_keyword.setEnabled(folder_mode)
        for radio in (self._files_radio, self._folder_radio):
            radio.setProperty("selected", radio.isChecked())
            radio.style().unpolish(radio)
            radio.style().polish(radio)

    def result_options(self):
        """Retorna dict com as opções selecionadas. Chamar após exec() == Accepted."""
        mode = "files"
        if self._folder_radio is not None and self._folder_radio.isChecked():
            mode = "folder"
        elif self._files_radio is None:
            mode = "folder"
        return {
            "mode": mode,
            "recursive": self._recursive.isChecked(),
            "keyword": self._skip_keyword.text().strip().lower(),
            "grayscale": self._grayscale.isChecked(),
            "prefix": self._prefix.isChecked() if self._prefix else False,
        }
