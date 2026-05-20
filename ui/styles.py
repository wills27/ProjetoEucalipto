APP_STYLE = r"""
            QMainWindow, QWidget {
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
            QLineEdit, QSpinBox, QTextEdit, QListWidget, QTableWidget {
                background: #ffffff;
                border: 1px solid #d9dfd8;
                border-radius: 6px;
                padding: 4px;
            }
            QTableWidget {
                alternate-background-color: #fbfbfa;
                selection-background-color: #5fa08f;
                selection-color: #ffffff;
                gridline-color: #e8ece6;
            }
            QTableWidget::item {
                padding: 6px;
            }
            QTableWidget::item:selected {
                background: #5fa08f;
                color: #ffffff;
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
                padding: 6px;
                font-weight: 600;
            }
            """
