from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui.annotation_page import AnnotationPage
from ui.tables.dataset_pairs_table import DatasetPairsTable
from ui.widgets import AnnotationPreviewLabel


class UiBuilderMixin:
    def build_ui(self):
        root = QWidget()
        root.setObjectName("appRoot")
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(14, 14, 14, 14)
        root_layout.setSpacing(12)

        body = QHBoxLayout()
        body.setSpacing(12)
        root_layout.addLayout(body, 1)

        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 10, 10, 10)
        sidebar_layout.setSpacing(8)
        body.addWidget(sidebar, 0)

        self.stack = QStackedWidget()
        body.addWidget(self.stack, 1)

        for label, builder in [
            ("Inicio", self.build_project_page),
            ("Resultados", self.build_results_page),
        ]:
            button = QPushButton(label)
            button.setObjectName("nav")
            button.clicked.connect(lambda checked=False, index=len(self.nav_buttons): self.set_page(index))
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
            page = QWidget()
            page.setObjectName("page")
            builder(page)
            self.stack.addWidget(page)

        sidebar_layout.addStretch()
        self.add_button(sidebar_layout, "Atualizar", self.refresh_all)

        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.hide()

        self.task_progress_label = QLabel()
        self.task_progress_bar = QProgressBar()
        self.task_progress_bar.setMinimumWidth(160)
        self.task_progress_bar.setTextVisible(True)
        self.task_progress_label.hide()
        self.task_progress_bar.hide()
        self.statusBar().addPermanentWidget(self.task_progress_label)
        self.statusBar().addPermanentWidget(self.task_progress_bar)

        self.set_page(0)
        self.apply_style()

    def build_project_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        project_box = self.panel("Projeto atual")
        project_layout = QGridLayout(project_box)
        project_layout.setContentsMargins(10, 8, 10, 10)
        project_layout.setHorizontalSpacing(10)
        project_layout.setVerticalSpacing(6)
        self.project_combo = QComboBox()
        self.project_combo.currentTextChanged.connect(self.select_project)
        self.home_model_combo = QComboBox()
        self.home_model_combo.currentIndexChanged.connect(self.on_home_model_changed)
        project_layout.addWidget(QLabel("Projeto"), 0, 0)
        project_layout.addWidget(self.project_combo, 0, 1)
        create_project_button = QPushButton("Criar projeto")
        create_project_button.clicked.connect(self.create_project)
        project_layout.addWidget(create_project_button, 0, 2)
        project_layout.addWidget(QLabel("Modelo"), 0, 3)
        project_layout.addWidget(self.home_model_combo, 0, 4)
        import_model_button = QPushButton("Importar modelo")
        import_model_button.clicked.connect(self.import_prediction_model)
        project_layout.addWidget(import_model_button, 0, 5)
        project_layout.setColumnStretch(1, 1)
        project_layout.setColumnStretch(4, 1)
        layout.addWidget(project_box)

        self.build_dataset_section(layout, show_import_actions=False)

    def build_dataset_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        self.build_dataset_section(layout)

    def build_dataset_section(self, layout, show_import_actions=True):
        validation_box = self.panel("Selecao e divisao do dataset")
        validation_layout = QHBoxLayout(validation_box)
        table_layout = QVBoxLayout()
        self.dataset_validation_summary = QLabel()
        self.dataset_validation_summary.setObjectName("mono")
        table_layout.addWidget(self.dataset_validation_summary)
        self.dataset_calibration_label = QLabel("Calibracao: nao definida")
        self.dataset_calibration_label.setObjectName("hint")
        table_layout.addWidget(self.dataset_calibration_label)
        filters_layout = QHBoxLayout()
        self.dataset_filter = QLineEdit()
        self.dataset_filter.setPlaceholderText("Buscar por numero ou nome")
        self.dataset_filter.textChanged.connect(self.apply_dataset_filter)
        self.dataset_status_filter = QComboBox()
        self.dataset_status_filter.addItem("Status: todos", "")
        self.dataset_status_filter.addItem("Com mascara", "Com mascara")
        self.dataset_status_filter.addItem("Sem mascara", "Sem mascara")
        self.dataset_status_filter.currentIndexChanged.connect(self.apply_dataset_filter)
        self.dataset_group_filter = QComboBox()
        self.dataset_group_filter.addItem("Grupo: todos", "")
        self.dataset_group_filter.addItem("Sem categoria", "uncategorized")
        self.dataset_group_filter.addItem("Auto", "auto")
        self.dataset_group_filter.addItem("Treino", "train")
        self.dataset_group_filter.addItem("Validacao", "val")
        self.dataset_group_filter.addItem("Teste", "test")
        self.dataset_group_filter.currentIndexChanged.connect(self.apply_dataset_filter)
        self.dataset_include_filter = QComboBox()
        self.dataset_include_filter.addItem("Uso: todos", "")
        self.dataset_include_filter.addItem("Selecionadas", "selected")
        self.dataset_include_filter.addItem("Nao selecionadas", "unselected")
        self.dataset_include_filter.currentIndexChanged.connect(self.apply_dataset_filter)
        clear_filter_button = QPushButton("Limpar filtros")
        clear_filter_button.clicked.connect(self.clear_dataset_filters)
        filters_layout.addWidget(self.dataset_filter, 1)
        filters_layout.addWidget(self.dataset_status_filter)
        filters_layout.addWidget(self.dataset_group_filter)
        filters_layout.addWidget(self.dataset_include_filter)
        filters_layout.addWidget(clear_filter_button)
        table_layout.addLayout(filters_layout)
        self.dataset_pairs_table = DatasetPairsTable(
            self.delete_selected_dataset_pair,
            self.move_selected_dataset_rows_to_group,
            0,
            4,
        )
        self.dataset_pairs_table.setHorizontalHeaderLabels(["#", "Grupo", "Imagem", "Status"])
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.verticalHeader().setVisible(False)
        self.dataset_pairs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dataset_pairs_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.dataset_pairs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dataset_pairs_table.itemSelectionChanged.connect(self.on_dataset_table_selection_changed)
        self.dataset_pairs_table.currentCellChanged.connect(self.on_dataset_pair_current_cell_changed)
        table_layout.addWidget(self.dataset_pairs_table, 1)
        validation_actions = QHBoxLayout()
        if show_import_actions:
            self.add_button(validation_actions, "Importar imagens", self.import_dataset_folder)
        self.add_button(validation_actions, "Separar treino/teste", self.auto_split_dataset_table)
        validation_actions.addStretch()
        table_layout.addLayout(validation_actions)
        validation_layout.addLayout(table_layout, 1)

        preview_layout = QVBoxLayout()
        self.dataset_preview_label = AnnotationPreviewLabel(
            lambda *_args: None,
            lambda *_args: None,
            lambda *_args: None,
            double_click_callback=self.open_selected_dataset_editor,
            draw_button=None,
        )
        self.dataset_preview_label.setObjectName("preview")
        self.dataset_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.dataset_preview_label.setMinimumSize(200, 160)
        self.dataset_preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.dataset_preview_label.setWordWrap(True)
        self.dataset_preview_info = QLabel(
            "Imagens sem mascara entram como teste para Resultados. Duplo clique para editar/criar mascara."
        )
        self.dataset_preview_info.setObjectName("hint")
        self.dataset_preview_info.setWordWrap(True)
        prediction_params = QGridLayout()
        prediction_params.setContentsMargins(0, 0, 0, 0)
        prediction_params.setHorizontalSpacing(8)
        self.dataset_prediction_diameter = QLineEdit(str(self.config["diameter"]))
        self.dataset_prediction_diameter.setMinimumWidth(72)
        prediction_params.addWidget(QLabel("Diametro da predicao"), 0, 0)
        prediction_params.addWidget(self.dataset_prediction_diameter, 0, 1)
        prediction_params.setColumnStretch(2, 1)
        preview_actions = QHBoxLayout()
        self.dataset_predict_mask_button = self.add_button(
            preview_actions,
            "Criar mascara com modelo",
            self.run_annotation_mask_prediction,
        )
        self.dataset_edit_mask_button = self.add_button(
            preview_actions,
            "Editar/desenhar mascara",
            self.open_selected_dataset_editor,
            primary=True,
        )
        preview_actions.addStretch()
        self.dataset_mask_progress = QProgressBar()
        self.dataset_mask_progress.setRange(0, 0)
        self.dataset_mask_progress.setTextVisible(False)
        self.dataset_mask_progress.setVisible(False)
        preview_layout.addWidget(self.dataset_preview_label, 1)
        preview_layout.addLayout(prediction_params)
        preview_layout.addLayout(preview_actions)
        preview_layout.addWidget(self.dataset_mask_progress)
        preview_layout.addWidget(self.dataset_preview_info)
        validation_layout.addLayout(preview_layout, 2)
        layout.addWidget(validation_box, 1)

        self.annotation_page = AnnotationPage(self, build_ui=False)

    def panel(self, title):
        box = QGroupBox(title)
        box.setObjectName("panel")
        return box

    def metric_card(self, label):
        frame = QFrame()
        frame.setObjectName("card")
        frame.setMinimumHeight(118)
        frame.setMaximumHeight(118)
        frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        title = QLabel(label)
        title.setObjectName("cardTitle")
        divider = QFrame()
        divider.setObjectName("subtleDivider")
        divider.setFrameShape(QFrame.Shape.HLine)
        value = QLabel("-")
        value.setObjectName("cardValue")
        value.setWordWrap(True)
        value.setMinimumHeight(64)
        value.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)
        layout.addWidget(divider)
        layout.addWidget(value, 1)
        return frame, value

    def path_field(self, line_edit):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(line_edit, 1)
        button = QPushButton("Escolher")
        button.clicked.connect(lambda: self.choose_folder(line_edit))
        layout.addWidget(button)
        return widget

    def add_button(self, layout, text, callback, primary=False):
        button = QPushButton(text)
        if primary:
            button.setObjectName("primary")
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

