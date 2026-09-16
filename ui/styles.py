from pathlib import Path

from ui import palette as c

_CHECK_SVG = (Path(__file__).parent / "assets" / "check.svg").as_posix()

_APP_STYLE_TEMPLATE = f"""
            QWidget {{
                background: transparent;
                color: {c.TEXT};
                font-family: Segoe UI;
                font-size: 10pt;
            }}
            QMainWindow, QDialog, QWidget#appRoot, QWidget#page {{
                background: {c.BACKGROUND};
                color: {c.TEXT};
                font-family: Segoe UI;
                font-size: 10pt;
            }}
            QMenuBar {{
                background: {c.BACKGROUND};
                color: {c.TEXT};
                border-bottom: 1px solid {c.BORDER};
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 5px 10px;
            }}
            QMenuBar::item:selected {{
                background: {c.HOVER_BG};
                color: {c.TEXT};
            }}
            QMenu {{
                background: {c.SURFACE};
                color: {c.TEXT};
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                background: transparent;
                padding: 6px 28px 6px 24px;
            }}
            QMenu::item:selected {{
                background: {c.HOVER_BG};
                color: {c.TEXT};
            }}
            QMenu::separator {{
                height: 1px;
                background: {c.DIVIDER};
                margin: 4px 6px;
            }}
            QLabel#subtitle, QLabel#status, QLabel#cardTitle {{
                color: {c.TEXT_SECONDARY};
                background: transparent;
            }}
            QLabel#hint {{
                color: {c.TEXT_SECONDARY};
                background: transparent;
            }}
            QLabel#sidebarSection {{
                color: {c.TEXT_SECONDARY};
                font-size: 8pt;
                font-weight: 700;
                letter-spacing: 0.5px;
                text-transform: uppercase;
                background: transparent;
                padding-top: 4px;
            }}
            QLabel#imageSetBadge {{
                color: {c.PRIMARY_ACTIVE};
                background: {c.SURFACE_ALT};
                border: 1px solid {c.NAV_ACTIVE_BORDER};
                border-radius: 8px;
                padding: 4px 8px;
                font-weight: 600;
            }}
            QLabel#errorTitle {{
                color: {c.ERROR_TEXT};
                font-family: {c.FONT_DISPLAY};
                font-size: 16pt;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#errorMessage {{
                color: {c.TEXT};
                background: transparent;
            }}
            QTextEdit#errorDetails {{
                background: {c.ERROR_SURFACE};
                color: {c.TEXT};
                border: 1px solid {c.ERROR_BORDER};
                border-radius: 6px;
                font-family: Consolas;
            }}
            QLabel#statusCardTitle {{
                color: {c.TEXT_SECONDARY};
                font-size: 8pt;
                font-weight: 700;
                letter-spacing: 0px;
                background: transparent;
            }}
            QLabel#statusCardValue {{
                color: {c.TEXT};
                font-family: {c.FONT_DISPLAY};
                font-size: 15pt;
                font-weight: 650;
                padding-top: 6px;
                background: transparent;
            }}
            QLabel#largeText {{
                font-family: {c.FONT_DISPLAY};
                font-size: 14pt;
                font-weight: 600;
                background: transparent;
            }}
            QLabel#metricTitle {{
                color: {c.TEXT_SECONDARY};
                font-size: 8pt;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#metricValue {{
                color: {c.PRIMARY_ACTIVE};
                font-size: 12pt;
                font-weight: 700;
                background: transparent;
            }}
            QLabel#mono {{
                font-family: Consolas;
                background: {c.SURFACE_MUTED};
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                padding: 10px;
            }}
            QFrame#sidebar {{
                background: {c.SURFACE};
                border: 1px solid {c.BORDER};
                border-bottom: 2px solid {c.BORDER_STRONG};
                border-radius: 12px;
                min-width: 150px;
                max-width: 150px;
            }}
            QPushButton {{
                background: {c.NEUTRAL_TINT};
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                padding: 8px 12px;
                color: {c.TEXT};
            }}
            QPushButton:hover {{
                background: {c.HOVER_BG};
                border: 1px solid {c.HOVER_BORDER};
                color: {c.TEXT};
            }}
            QPushButton:pressed {{
                background: {c.PRESSED_BG};
                border: 1px solid {c.PRESSED_BORDER};
            }}
            QPushButton#primary {{
                background: {c.PRIMARY};
                border: 1px solid {c.PRIMARY};
                color: {c.ON_PRIMARY};
            }}
            QPushButton#primary:hover {{
                background: {c.PRIMARY_HOVER};
                border: 1px solid {c.PRIMARY_HOVER};
            }}
            QPushButton#primary:pressed {{
                background: {c.PRIMARY_ACTIVE};
                border: 1px solid {c.PRIMARY_ACTIVE};
            }}
            QPushButton#accent {{
                background: {c.ACCENT};
                border: 1px solid {c.ACCENT_ACTIVE};
                color: {c.ON_ACCENT};
                font-weight: 700;
            }}
            QPushButton#accent:hover {{
                background: {c.ACCENT_HOVER};
                border: 1px solid {c.ACCENT_ACTIVE};
            }}
            QPushButton#accent:pressed {{
                background: {c.ACCENT_ACTIVE};
                border: 1px solid {c.ACCENT_ACTIVE};
            }}
            QPushButton#nav {{
                text-align: left;
                background: transparent;
                border: 1px solid transparent;
                padding: 10px 12px;
            }}
            QPushButton#nav:hover {{
                background: {c.HOVER_BG};
                border: 1px solid {c.HOVER_BORDER};
            }}
            QPushButton#nav[active="true"] {{
                background: {c.NAV_ACTIVE_BG};
                border: 1px solid {c.NAV_ACTIVE_BORDER};
                color: {c.NAV_ACTIVE_TEXT};
                font-weight: 700;
            }}
            QPushButton#nav[active="true"]:hover {{
                background: {c.PRESSED_BG};
                border: 1px solid {c.PRESSED_BORDER};
            }}
            QWidget#wizardNav {{
                background: {c.SURFACE};
                border-top: 1px solid {c.BORDER};
            }}
            QPushButton#mode:hover {{
                background: {c.HOVER_BG};
                border: 1px solid {c.HOVER_BORDER};
            }}
            QPushButton#mode[active="true"] {{
                background: {c.PRIMARY};
                border: 1px solid {c.PRIMARY};
                color: {c.ON_PRIMARY};
            }}
            QGroupBox#panel, QGroupBox#logPanel {{
                background: {c.SURFACE};
                border: 1px solid {c.BORDER};
                border-bottom: 2px solid {c.BORDER_STRONG};
                border-radius: 12px;
                margin-top: 10px;
                padding: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                font-family: {c.FONT_DISPLAY};
                font-size: 11pt;
                font-weight: 600;
            }}
            QFrame#dialogSection {{
                background: {c.SURFACE};
                border: 1px solid {c.BORDER};
                border-bottom: 2px solid {c.BORDER_STRONG};
                border-radius: 12px;
            }}
            QFrame#card {{
                background: {c.SURFACE};
                border: 1px solid {c.BORDER};
                border-bottom: 2px solid {c.BORDER_STRONG};
                border-radius: 12px;
            }}
            QFrame#statusCard {{
                background: {c.SURFACE};
                border: 1px solid {c.BORDER};
                border-bottom: 2px solid {c.BORDER_STRONG};
                border-radius: 12px;
            }}
            QFrame#trainingMetrics {{
                background: {c.SURFACE_MUTED};
                border: 1px solid {c.BORDER};
                border-radius: 10px;
            }}
            QFrame#subtleDivider {{
                background: {c.DIVIDER};
                border: 0;
                min-height: 1px;
                max-height: 1px;
                margin-top: 4px;
                margin-bottom: 8px;
            }}
            QLabel#cardValue {{
                color: {c.PRIMARY_ACTIVE};
                font-family: {c.FONT_DISPLAY};
                font-size: 13pt;
                font-weight: 600;
                line-height: 150%;
                background: transparent;
            }}
            QLabel#preview {{
                background: {c.SURFACE_MUTED};
                border: 1px solid {c.BORDER};
                border-radius: 14px;
            }}
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QListWidget, QTableWidget {{
                background: {c.SURFACE};
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                padding: 4px;
            }}
            QComboBox::drop-down {{
                border: 0;
                width: 24px;
            }}
            QCheckBox {{
                spacing: 8px;
                background: transparent;
            }}
            QCheckBox::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {c.CONTROL_BORDER};
                border-radius: 4px;
                background: {c.SURFACE};
            }}
            QCheckBox::indicator:hover {{
                border: 1px solid {c.GREEN_400};
            }}
            QCheckBox::indicator:checked {{
                background: {c.PRIMARY};
                border: 1px solid {c.PRIMARY};
                image: url(__CHECK_SVG__);
            }}
            QCheckBox::indicator:disabled {{
                background: {c.DISABLED_BG};
                border: 1px solid {c.DISABLED_BORDER};
            }}
            QRadioButton#choice {{
                background: {c.SURFACE_MUTED};
                border: 1px solid {c.BORDER};
                border-radius: 10px;
                padding: 8px 12px;
                spacing: 8px;
            }}
            QRadioButton#choice:hover {{
                border: 1px solid {c.HOVER_BORDER};
                background: {c.HOVER_BG};
            }}
            QRadioButton#choice[selected="true"] {{
                border: 1px solid {c.PRIMARY};
                background: {c.NAV_ACTIVE_BG};
                color: {c.PRIMARY_ACTIVE};
                font-weight: 700;
            }}
            QRadioButton#choice::indicator {{
                width: 14px;
                height: 14px;
                border: 1px solid {c.CONTROL_BORDER};
                border-radius: 7px;
                background: {c.SURFACE};
            }}
            QRadioButton#choice::indicator:checked {{
                border: 4px solid {c.PRIMARY};
                background: {c.SURFACE};
            }}
            QTableWidget {{
                alternate-background-color: {c.SURFACE_MUTED};
                selection-background-color: {c.SELECTED_BG};
                selection-color: {c.SELECTED_TEXT};
                gridline-color: {c.DIVIDER};
            }}
            QTableWidget::indicator {{
                width: 16px;
                height: 16px;
                border: 1px solid {c.CONTROL_BORDER};
                border-radius: 3px;
                background: {c.SURFACE};
            }}
            QTableWidget::indicator:checked {{
                background: {c.PRIMARY};
                border: 1px solid {c.PRIMARY};
                image: url(__CHECK_SVG__);
            }}
            QTableWidget::indicator:unchecked {{
                background: {c.SURFACE};
            }}
            QListWidget {{
                outline: 0;
            }}
            QListWidget::item {{
                border-bottom: 1px solid {c.DIVIDER};
                border-radius: 3px;
                padding: 5px 8px;
                margin: 0;
            }}
            QListWidget::item:hover {{
                background: {c.NAV_ACTIVE_BG};
                color: {c.TEXT};
            }}
            QListWidget::item:selected {{
                background: {c.SELECTED_BG};
                color: {c.SELECTED_TEXT};
            }}
            QListWidget::item:selected:active,
            QListWidget::item:selected:!active {{
                background: {c.SELECTED_BG};
                color: {c.SELECTED_TEXT};
            }}
            QTableWidget::item {{
                padding: 6px;
            }}
            QTableWidget::item:hover {{
                background: {c.NAV_ACTIVE_BG};
                color: {c.TEXT};
            }}
            QTableWidget::item:selected {{
                background: {c.SELECTED_BG};
                color: {c.SELECTED_TEXT};
            }}
            QTableWidget::item:selected:active,
            QTableWidget::item:selected:!active {{
                background: {c.SELECTED_BG};
                color: {c.SELECTED_TEXT};
            }}
            QTabWidget::pane {{
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                background: {c.SURFACE};
                top: -1px;
            }}
            QTabBar::tab {{
                background: {c.NEUTRAL_TINT};
                color: {c.TEXT};
                border: 1px solid {c.BORDER};
                border-bottom: 0;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                padding: 7px 12px;
                margin-right: 2px;
            }}
            QTabBar::tab:selected {{
                background: {c.SELECTED_BG};
                color: {c.SELECTED_TEXT};
                border-color: {c.SELECTED_BG};
                font-weight: 700;
            }}
            QTabBar::tab:hover:!selected {{
                background: {c.NAV_ACTIVE_BG};
                color: {c.TEXT};
            }}
            QProgressBar {{
                background: {c.NEUTRAL_TINT};
                border: 1px solid {c.BORDER};
                border-radius: 8px;
                color: {c.TEXT};
                font-weight: 700;
                min-height: 18px;
                max-height: 18px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background: {c.PRIMARY};
                border-radius: 6px;
            }}
            QTextEdit#log {{
                background: {c.LOG_BACKGROUND};
                color: {c.LOG_TEXT};
                border-radius: 8px;
                font-family: Consolas;
            }}
            QHeaderView::section {{
                background: {c.NEUTRAL_TINT};
                border: 0;
                border-right: 1px solid {c.BORDER};
                padding: 6px;
                font-weight: 600;
            }}
            QHeaderView::section:last {{
                border-right: 0;
            }}
            /* Qt/Windows pinta o texto do botao "default" de um dialogo com a cor
               de destaque nativa a menos que a regra :default seja a ultima do
               stylesheet a casar; por isso este bloco fica no final do arquivo. */
            QPushButton:default {{
                color: {c.TEXT};
            }}
            QPushButton#primary:default {{
                color: {c.ON_PRIMARY};
            }}
            QPushButton#accent:default {{
                color: {c.ON_ACCENT};
            }}
            QPushButton#mode:default {{
                color: {c.TEXT};
            }}
            QPushButton#mode[active="true"]:default {{
                color: {c.ON_PRIMARY};
            }}
            QPushButton#nav:default {{
                color: {c.TEXT};
            }}
            QPushButton#nav[active="true"]:default {{
                color: {c.NAV_ACTIVE_TEXT};
            }}
            """

APP_STYLE = _APP_STYLE_TEMPLATE.replace("__CHECK_SVG__", _CHECK_SVG)
