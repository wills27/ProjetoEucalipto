"""Fabricas de widgets reutilizados em varias paginas e dialogos.

Cada widget aqui e estilizado via objectName no QSS (ui/styles.py), entao
qualquer tela que precise de um cartao com titulo, um botao de alternancia
de modo ou um popup de parametros avancados deve usar essas fabricas em vez
de recriar o widget na mao — isso mantem a aparencia (e a paleta) consistente
em todo o app.
"""

from PyQt6.QtCore import QPointF, QRect, Qt
from PyQt6.QtGui import QColor, QPen, QPolygonF
from PyQt6.QtWidgets import (
    QGraphicsDropShadowEffect,
    QGridLayout,
    QGroupBox,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QToolButton,
    QWidget,
    QWidgetAction,
)

from ui import palette


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


class CheckBoxHeaderView(QHeaderView):
    """Cabecalho de tabela com um quadrado de checkbox desenhado numa coluna,
    para deixar visualmente claro que clicar ali marca/desmarca todas as
    linhas visiveis de uma vez (em vez de um cabecalho vazio sem nenhuma pista).
    Desenhado manualmente (em vez do CE_CheckBox nativo do estilo) para bater
    exatamente com a aparencia do QTableWidget::indicator definida no QSS
    (ui/styles.py) — senao fica com um visual de checkbox diferente do resto
    da tabela."""

    _SIZE = 16
    _RADIUS = 3

    def __init__(self, checkable_column, parent=None):
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._checkable_column = checkable_column
        self._checked = False
        # Um QHeaderView criado do zero nao herda o sectionsClickable=True que
        # o cabecalho padrao do QTableWidget tem; sem isso, sectionClicked
        # nunca dispara e o clique de marcar/desmarcar tudo para de funcionar.
        self.setSectionsClickable(True)

    def set_checked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.updateSection(self._checkable_column)

    def paintSection(self, painter, rect, logical_index):
        # O paintSection padrao do Qt deixa uma regiao de recorte (clip) ativa
        # apos desenhar o fundo/texto do cabecalho; sem isolar isso com
        # save/restore, o desenho do checkbox feito depois nao aparece.
        painter.save()
        super().paintSection(painter, rect, logical_index)
        painter.restore()
        if logical_index != self._checkable_column:
            return
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        box_rect = QRect(
            rect.x() + (rect.width() - self._SIZE) // 2,
            rect.y() + (rect.height() - self._SIZE) // 2,
            self._SIZE,
            self._SIZE,
        )
        if self._checked:
            painter.setBrush(QColor(palette.PRIMARY))
            painter.setPen(QColor(palette.PRIMARY))
        else:
            painter.setBrush(QColor(palette.SURFACE))
            painter.setPen(QColor(palette.CONTROL_BORDER))
        painter.drawRoundedRect(box_rect, self._RADIUS, self._RADIUS)
        if self._checked:
            # check.png (usado em outros lugares) nao tem canal alfa e cobriria
            # o preenchimento verde com um quadrado preto; desenha a marca na
            # mao para garantir fundo transparente sobre o box ja pintado.
            pen = QPen(QColor(palette.SURFACE))
            pen.setWidthF(1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            x, y, s = box_rect.x(), box_rect.y(), box_rect.width()
            points = [
                QPointF(x + s * 0.22, y + s * 0.52),
                QPointF(x + s * 0.42, y + s * 0.72),
                QPointF(x + s * 0.80, y + s * 0.28),
            ]
            painter.drawPolyline(QPolygonF(points))
        painter.restore()


def make_checkbox_header(checkable_column, parent=None):
    """Cabecalho horizontal com checkbox visual na coluna informada."""
    return CheckBoxHeaderView(checkable_column, parent=parent)


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
