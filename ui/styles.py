from pathlib import Path

_CHECK_SVG = (Path(__file__).parent / "assets" / "check.svg").as_posix()

_APP_STYLE_TEMPLATE = r"""
            QWidget {
                background: transparent;
                color: #1f2933;
                font-family: Segoe UI;
                font-size: 10pt;
            }
            QMainWindow, QDialog, QWidget#appRoot, QWidget#page {
                background: #f6f7f5;
                color: #1f2933;
                font-family: Segoe UI;
                font-size: 10pt;
            }
            QMenuBar {
                background: #f6f7f5;
                color: #1f2933;
                border-bottom: 1px solid #d9dfd8;
            }
            QMenuBar::item {
                background: transparent;
                padding: 5px 10px;
            }
            QMenuBar::item:selected {
                background: #e8f1fb;
                color: #1f2933;
            }
            QMenu {
                background: #ffffff;
                color: #1f2933;
                border: 1px solid #b8c3bc;
                padding: 4px;
            }
            QMenu::item {
                background: transparent;
                padding: 6px 28px 6px 24px;
            }
            QMenu::item:selected {
                background: #e8f1fb;
                color: #1f2933;
            }
            QMenu::separator {
                height: 1px;
                background: #d9dfd8;
                margin: 4px 6px;
            }
            QLabel#subtitle, QLabel#status, QLabel#cardTitle {
                color: #69736d;
                background: transparent;
            }
            QLabel#hint {
                color: #69736d;
                background: transparent;
            }
            QLabel#errorTitle {
                color: #9f1d1d;
                font-size: 15pt;
                font-weight: 700;
                background: transparent;
            }
            QLabel#errorMessage {
                color: #1f2933;
                background: transparent;
            }
            QTextEdit#errorDetails {
                background: #fffafa;
                color: #1f2933;
                border: 1px solid #e5b5b5;
                border-radius: 6px;
                font-family: Consolas;
            }
            QLabel#statusCardTitle {
                color: #69736d;
                font-size: 8pt;
                font-weight: 700;
                letter-spacing: 0px;
                background: transparent;
            }
            QLabel#statusCardValue {
                color: #1f2933;
                font-size: 13pt;
                font-weight: 650;
                padding-top: 6px;
                background: transparent;
            }
            QLabel#largeText {
                font-size: 13pt;
                font-weight: 600;
                background: transparent;
            }
            QLabel#metricTitle {
                color: #69736d;
                font-size: 8pt;
                font-weight: 700;
                background: transparent;
            }
            QLabel#metricValue {
                color: #166b5c;
                font-size: 12pt;
                font-weight: 700;
                background: transparent;
            }
            QLabel#mono {
                font-family: Consolas;
                background: #fbfbfa;
                border: 1px solid #d9dfd8;
                border-radius: 6px;
                padding: 10px;
            }
            QFrame#sidebar {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
                min-width: 150px;
                max-width: 150px;
            }
            QPushButton {
                background: #f3f4f2;
                border: 1px solid #d4dad3;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover {
                background: #e8f1fb;
                border: 1px solid #8ab4e1;
                color: #1f2933;
            }
            QPushButton:pressed {
                background: #d9eafa;
                border: 1px solid #5e9bd3;
            }
            QPushButton#primary {
                background: #166b5c;
                border: 1px solid #166b5c;
                color: #ffffff;
            }
            QPushButton#primary:hover {
                background: #1f7f6e;
                border: 1px solid #145d51;
            }
            QPushButton#primary:pressed {
                background: #13574d;
                border: 1px solid #0f463e;
            }
            QPushButton#accent {
                background: #f0b429;
                border: 1px solid #d99718;
                color: #1f2933;
                font-weight: 700;
            }
            QPushButton#accent:hover {
                background: #ffd166;
                border: 1px solid #c9850f;
            }
            QPushButton#accent:pressed {
                background: #d99718;
                border: 1px solid #a8640b;
            }
            QPushButton#nav {
                text-align: left;
                background: transparent;
                border: 1px solid transparent;
                padding: 10px 12px;
            }
            QPushButton#nav:hover {
                background: #e8f1fb;
                border: 1px solid #8ab4e1;
            }
            QPushButton#nav[active="true"] {
                background: #e7f0ec;
                border: 1px solid #b9d6cb;
                color: #166b5c;
                font-weight: 700;
            }
            QPushButton#nav[active="true"]:hover {
                background: #dcece6;
                border: 1px solid #8fc2ae;
            }
            QPushButton#mode:hover {
                background: #e8f1fb;
                border: 1px solid #8ab4e1;
            }
            QPushButton#mode[active="true"] {
                background: #166b5c;
                border: 1px solid #166b5c;
                color: white;
            }
            QGroupBox#panel, QGroupBox#logPanel {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
                margin-top: 10px;
                padding: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 4px;
                font-weight: 700;
            }
            QFrame#dialogSection {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
            }
            QFrame#card {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
            }
            QFrame#statusCard {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
            }
            QFrame#trainingMetrics {
                background: #fbfbfa;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
            }
            QFrame#subtleDivider {
                background: #e8ece6;
                border: 0;
                min-height: 1px;
                max-height: 1px;
                margin-top: 4px;
                margin-bottom: 8px;
            }
            QLabel#cardValue {
                color: #166b5c;
                font-size: 11pt;
                font-weight: 600;
                line-height: 150%;
                background: transparent;
            }
            QLabel#preview {
                background: #fbfbfa;
                border: 1px solid #d9dfd8;
                border-radius: 8px;
            }
            QLineEdit, QSpinBox, QComboBox, QTextEdit, QListWidget, QTableWidget {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 6px;
                padding: 4px;
            }
            QComboBox::drop-down {
                border: 0;
                width: 24px;
            }
            QCheckBox {
                spacing: 8px;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #9aa8a0;
                border-radius: 3px;
                background: #ffffff;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #5fa08f;
            }
            QCheckBox::indicator:checked {
                background: #166b5c;
                border: 1px solid #166b5c;
                image: url(__CHECK_SVG__);
            }
            QCheckBox::indicator:disabled {
                background: #eef0ed;
                border: 1px solid #c8d0c8;
            }
            QRadioButton#choice {
                background: #fbfbfa;
                border: 1px solid #d9dfd8;
                border-radius: 6px;
                padding: 8px 12px;
                spacing: 8px;
            }
            QRadioButton#choice:hover {
                border: 1px solid #8ab4e1;
                background: #f3f8fd;
            }
            QRadioButton#choice[selected="true"] {
                border: 1px solid #166b5c;
                background: #e7f0ec;
                color: #166b5c;
                font-weight: 700;
            }
            QRadioButton#choice::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #9aa8a0;
                border-radius: 7px;
                background: #ffffff;
            }
            QRadioButton#choice::indicator:checked {
                border: 4px solid #166b5c;
                background: #ffffff;
            }
            QTableWidget {
                alternate-background-color: #fbfbfa;
                selection-background-color: #5fa08f;
                selection-color: #ffffff;
                gridline-color: #e8ece6;
            }
            QTableWidget::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #9aa8a0;
                border-radius: 3px;
                background: #ffffff;
            }
            QTableWidget::indicator:checked {
                background: #166b5c;
                border: 1px solid #166b5c;
                image: url(__CHECK_SVG__);
            }
            QTableWidget::indicator:unchecked {
                background: #ffffff;
            }
            QListWidget {
                outline: 0;
            }
            QListWidget::item {
                border-bottom: 1px solid #e8ece6;
                border-radius: 3px;
                padding: 5px 8px;
                margin: 0;
            }
            QListWidget::item:hover {
                background: #e7f0ec;
                color: #1f2933;
            }
            QListWidget::item:selected {
                background: #5fa08f;
                color: #ffffff;
            }
            QListWidget::item:selected:active,
            QListWidget::item:selected:!active {
                background: #5fa08f;
                color: #ffffff;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:hover {
                background: #e7f0ec;
                color: #1f2933;
            }
            QTableWidget::item:selected {
                background: #5fa08f;
                color: #ffffff;
            }
            QTableWidget::item:selected:active,
            QTableWidget::item:selected:!active {
                background: #5fa08f;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 1px solid #d9dfd8;
                border-radius: 6px;
                background: #ffffff;
                top: -1px;
            }
            QTabBar::tab {
                background: #eef0ed;
                color: #1f2933;
                border: 1px solid #d9dfd8;
                border-bottom: 0;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 7px 12px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background: #5fa08f;
                color: #ffffff;
                border-color: #5fa08f;
                font-weight: 700;
            }
            QTabBar::tab:hover:!selected {
                background: #e7f0ec;
                color: #1f2933;
            }
            QProgressBar {
                background: #eef0ed;
                border: 1px solid #d9dfd8;
                border-radius: 6px;
                color: #1f2933;
                font-weight: 700;
                min-height: 18px;
                max-height: 18px;
                text-align: center;
            }
            QProgressBar::chunk {
                background: #166b5c;
                border-radius: 5px;
            }
            QTextEdit#log {
                background: #111827;
                color: #e5e7eb;
                border-radius: 8px;
                font-family: Consolas;
            }
            QHeaderView::section {
                background: #eef0ed;
                border: 0;
                border-right: 1px solid #d9dfd8;
                padding: 6px;
                font-weight: 600;
            }
            QHeaderView::section:last {
                border-right: 0;
            }
            """

APP_STYLE = _APP_STYLE_TEMPLATE.replace("__CHECK_SVG__", _CHECK_SVG)
