from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QHeaderView,
    QSizePolicy,
)

from services.paths import dataset_images_dir, relative_to_project
from ui.widgets import AnnotationPreviewLabel
from ui.tables.results_images_table import ResultsImagesTable


class ResultsPageBuilderMixin:
    def build_results_page(self, page):
        layout = QHBoxLayout(page)
        layout.setSpacing(12)

        left_column = QVBoxLayout()
        left_column.setSpacing(12)

        model_box = self.panel("Predicao")
        model_layout = QGridLayout(model_box)
        model_layout.setContentsMargins(10, 8, 10, 10)
        model_layout.setHorizontalSpacing(10)
        model_layout.setVerticalSpacing(6)
        self.predict_model_label = QLabel()
        self.predict_model_label.setObjectName("largeText")
        self.pred_input = QLineEdit(relative_to_project(dataset_images_dir(self.config), self.config))
        self.pred_output = QLineEdit(self.config["predictions_dir"])
        self.pred_output.setReadOnly(True)
        self.pred_padding = QLineEdit(str(self.config["padding_pixels"]))
        self.pred_diameter = QLineEdit(str(self.config["diameter"]))
        self.pred_cellprob = QLineEdit(str(self.config["cellprob_threshold"]))
        self.pred_flow = QLineEdit(str(self.config["flow_threshold"]))
        for field in [self.pred_padding, self.pred_diameter, self.pred_cellprob, self.pred_flow]:
            field.setMinimumWidth(64)
        self.results_calibration_label = QLabel("Calibracao: nao definida")
        self.results_calibration_label.setObjectName("hint")

        params_row = QWidget()
        params_layout = QVBoxLayout(params_row)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(6)

        diameter_row = QWidget()
        diameter_layout = QHBoxLayout(diameter_row)
        diameter_layout.setContentsMargins(0, 0, 0, 0)
        diameter_layout.setSpacing(8)
        diameter_label = QLabel("Diametro")
        diameter_label.setObjectName("largeText")
        self.pred_diameter.setMinimumWidth(96)
        diameter_layout.addWidget(diameter_label)
        diameter_layout.addWidget(self.pred_diameter)
        diameter_layout.addStretch()
        params_layout.addWidget(diameter_row)

        self.advanced_prediction_button = QToolButton()
        self.advanced_prediction_button.setText("Avancados")
        self.advanced_prediction_button.setArrowType(Qt.ArrowType.DownArrow)
        self.advanced_prediction_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.advanced_prediction_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        advanced_menu = QMenu(self.advanced_prediction_button)
        advanced_widget = QWidget()
        advanced_params_layout = QGridLayout(advanced_widget)
        advanced_params_layout.setContentsMargins(10, 8, 10, 8)
        advanced_params_layout.setHorizontalSpacing(8)
        advanced_params_layout.setVerticalSpacing(6)
        for row, (label, field) in enumerate(
            [
                ("Padding", self.pred_padding),
                ("Cell prob", self.pred_cellprob),
                ("Flow", self.pred_flow),
            ]
        ):
            advanced_params_layout.addWidget(QLabel(label), row, 0)
            advanced_params_layout.addWidget(field, row, 1)
        advanced_params_layout.setColumnStretch(1, 1)
        advanced_action = QWidgetAction(advanced_menu)
        advanced_action.setDefaultWidget(advanced_widget)
        advanced_menu.addAction(advanced_action)
        self.advanced_prediction_button.setMenu(advanced_menu)
        params_layout.addWidget(self.advanced_prediction_button)

        self.prediction_model_combo = QComboBox()
        self.prediction_model_combo.currentIndexChanged.connect(self.on_prediction_model_changed)

        model_header = QWidget()
        model_header_layout = QHBoxLayout(model_header)
        model_header_layout.setContentsMargins(0, 0, 0, 0)
        model_header_layout.setSpacing(8)
        model_header_layout.addWidget(self.prediction_model_combo, 1)
        self.add_button(model_header_layout, "Importar modelo", self.import_prediction_model)

        model_layout.addWidget(QLabel("Modelo usado"), 0, 0)
        model_layout.addWidget(model_header, 0, 1)
        model_layout.addWidget(QLabel("Parametros"), 1, 0)
        model_layout.addWidget(params_row, 1, 1)
        model_layout.addWidget(self.results_calibration_label, 2, 1)
        predict_actions = QHBoxLayout()
        self.generate_results_button = self.add_button(
            predict_actions,
            "Gerar resultados",
            self.run_missing_result_outputs,
            primary=True,
        )
        results_menu = QMenu(self.generate_results_button)
        all_images_action = results_menu.addAction("Todas as imagens")
        current_image_action = results_menu.addAction("Imagem atual")
        selected_images_action = results_menu.addAction("Imagens selecionadas")
        missing_outputs_action = results_menu.addAction("Imagens sem resultado")
        all_images_action.triggered.connect(lambda _checked=False: self.run_results())
        current_image_action.triggered.connect(lambda _checked=False: self.run_results_for_current_image())
        selected_images_action.triggered.connect(lambda _checked=False: self.run_results_for_selected_images())
        missing_outputs_action.triggered.connect(lambda _checked=False: self.run_missing_result_outputs())
        self.generate_results_button.setMenu(results_menu)
        view_results_button = self.add_button(predict_actions, "Visualizar resultados", self.open_results_viewer)
        view_results_button.setObjectName("accent")
        predict_actions.addStretch()
        model_layout.addLayout(predict_actions, 3, 1)
        self.result_progress_label = QLabel("Aguardando processo.")
        self.result_progress_label.setObjectName("hint")
        self.result_progress_label.setWordWrap(True)
        self.result_progress_bar = QProgressBar()
        self.result_progress_bar.setRange(0, 100)
        self.result_progress_bar.setValue(0)
        self.result_progress_bar.setFormat("%p%")
        self.result_progress_bar.setTextVisible(True)
        model_layout.addWidget(self.result_progress_label, 4, 1)
        model_layout.addWidget(self.result_progress_bar, 5, 1)
        left = self.panel("Imagens")
        left_layout = QVBoxLayout(left)
        self.result_images_table = ResultsImagesTable(
            {
                "import": self.open_prediction_image_import_dialog,
                "refresh": self.refresh_analysis_images,
                "generate_current": self.run_results_for_current_image,
                "generate_selected": self.run_results_for_context_images,
                "edit_mask": self.open_selected_result_mask_editor,
                "recalc_metrics": self.run_metrics_for_current_result_image,
                "remove": self.remove_context_result_images,
            },
            0,
            4,
        )
        self.result_images_table.setHorizontalHeaderLabels(["Usar", "Imagem", "Overlay", "Metricas"])
        self.result_images_table.verticalHeader().setVisible(False)
        self.result_images_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_images_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_images_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_images_table.currentCellChanged.connect(
            lambda row, _col, _previous_row, _previous_col: self.show_result_table_row(row)
        )
        self.result_images_table.itemChanged.connect(self.on_result_image_check_changed)
        self.result_images_table.itemSelectionChanged.connect(self.sync_result_checkboxes_from_selection)
        self.result_images_table.horizontalHeader().sectionClicked.connect(self.on_result_images_header_clicked)
        self.last_result_check_row = None
        self.result_images_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.result_images_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.result_images_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.result_images_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        left_layout.addWidget(self.result_images_table, 1)
        self.results_list_status = QLabel()
        self.results_list_status.setObjectName("hint")
        self.results_list_status.setWordWrap(True)
        left_layout.addWidget(self.results_list_status)
        left_column.addWidget(left, 1)
        left_column.addWidget(model_box)
        layout.addLayout(left_column, 0)

        center = self.panel("Visualizador")
        center_layout = QVBoxLayout(center)
        mode_layout = QHBoxLayout()
        self.view_buttons = {}
        for label, mode in [
            ("Original", "original"),
            ("Overlay", "overlay"),
            ("50%+", "overlay_50pct"),
            ("Inteiros", "overlay_inteiros"),
            ("Diametro", "overlay_diametro"),
        ]:
            button = QPushButton(label)
            button.setObjectName("mode")
            button.clicked.connect(lambda checked=False, selected=mode: self.set_view_mode(selected))
            self.view_buttons[mode] = button
            mode_layout.addWidget(button)
        mode_layout.addStretch()
        self.add_button(mode_layout, "Editar mascara", self.open_selected_result_mask_editor)
        self.add_button(mode_layout, "Recalcular metrica", self.run_metrics_for_current_result_image, primary=True)
        center_layout.addLayout(mode_layout)
        self.preview_label = AnnotationPreviewLabel(
            None,
            None,
            None,
            double_click_callback=self.open_selected_result_mask_editor,
            draw_button=None,
        )
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(320, 240)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        center_layout.addWidget(self.preview_label, 1)
        layout.addWidget(center, 1)
