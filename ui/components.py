"""Fabricas de widgets reutilizados em varias paginas e dialogos.

Cada widget aqui e estilizado via objectName no QSS (ui/styles.py), entao
qualquer tela que precise de um cartao com titulo, um botao de alternancia
de modo ou um popup de parametros avancados deve usar essas fabricas em vez
de recriar o widget na mao — isso mantem a aparencia (e a paleta) consistente
em todo o app.
"""

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
    QWidgetAction,
)


def apply_elevation(widget, blur=22, y_offset=5):
    """Sombra suave para cartoes estaticos (nao usar em widgets com preview/
    tabela ao vivo: um QGraphicsEffect forca renderizacao via software e pesa
    em conteudo que repinta com frequencia)."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y_offset)
    effect.setColor(QColor(22, 46, 32, 45))
    widget.setGraphicsEffect(effect)


def make_panel(title):
    """Cartao com titulo (QGroupBox#panel)."""
    box = QGroupBox(title)
    box.setObjectName("panel")
    return box


def make_mode_button(text, callback, active=False):
    """Botao de alternancia de modo/ferramenta (QPushButton#mode)."""
    button = QPushButton(text)
    button.setObjectName("mode")
    button.setProperty("active", active)
    button.setAutoDefault(False)
    button.clicked.connect(callback)
    return button


def make_advanced_params_button(fields):
    """Botao 'Avancados' com um menu popup contendo pares rotulo/campo."""
    button = QToolButton()
    button.setText("Avancados")
    button.setArrowType(Qt.ArrowType.DownArrow)
    button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    menu = QMenu(button)
    widget = QWidget()
    layout = QGridLayout(widget)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setHorizontalSpacing(8)
    layout.setVerticalSpacing(6)
    for row, (label, field) in enumerate(fields):
        layout.addWidget(QLabel(label), row, 0)
        layout.addWidget(field, row, 1)
    layout.setColumnStretch(1, 1)
    action = QWidgetAction(menu)
    action.setDefaultWidget(widget)
    menu.addAction(action)
    button.setMenu(menu)
    return button
