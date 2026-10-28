from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QVBoxLayout,
    QWidget,
    QHeaderView,
    QSizePolicy,
)

from services.i18n import tr
from services.paths import active_image_set_dir, relative_to_project
from ui.analysis_presenter import VIEWER_CIRCLE_GAP
from ui.widgets import AnnotationPreviewLabel, DiameterPreviewWidget, ZoomScrollArea
from ui.tables.results_images_table import ResultsImagesTable


class ResultsPageBuilderMixin:
    def build_results_page(self, page):
        # Grid: sidebar (col 0) e Imagens (col 1) em cima, card de Predicao
        # embaixo ocupando as duas colunas, Visualizador (col 2) na altura
        # inteira. A sidebar e movida pra results_sidebar_host em set_page.
        layout = QGridLayout(page)
        layout.setSpacing(12)

        self.results_sidebar_host = QWidget()
        results_sidebar_layout = QVBoxLayout(self.results_sidebar_host)
        results_sidebar_layout.setContentsMargins(0, 0, 0, 0)

        self._results_prediction_panel = self.panel(tr("results.prediction"))
        model_box = self._results_prediction_panel
        card_layout = QHBoxLayout(model_box)
        card_layout.setContentsMargins(10, 8, 10, 10)
        card_layout.setSpacing(10)
        card_content = QWidget()
        model_layout = QGridLayout(card_content)
        model_layout.setContentsMargins(0, 0, 0, 0)
        model_layout.setHorizontalSpacing(10)
        model_layout.setVerticalSpacing(6)
        self.predict_model_label = QLabel()
        self.predict_model_label.setObjectName("largeText")
        self.pred_input = QLineEdit(relative_to_project(active_image_set_dir(self.config), self.config))
        self.pred_output = QLineEdit(self.config["predictions_dir"])
        self.pred_output.setReadOnly(True)
        self.pred_padding = QLineEdit(str(self.config["padding_pixels"]))
        self.pred_diameter = QLineEdit(str(self.config["diameter"]))
        self.pred_cellprob = QLineEdit(str(self.config["cellprob_threshold"]))
        self.pred_flow = QLineEdit(str(self.config["flow_threshold"]))
        for field in [self.pred_padding, self.pred_diameter, self.pred_cellprob, self.pred_flow]:
            field.setMinimumWidth(64)
        self.pred_diameter.textChanged.connect(self.update_diameter_preview)
        self.results_calibration_label = QLabel(tr("calibration.not_set"))
        self.results_calibration_label.setObjectName("hint")

        params_row = QWidget()
        params_layout = QVBoxLayout(params_row)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(6)

        diameter_row = QWidget()
        diameter_layout = QHBoxLayout(diameter_row)
        diameter_layout.setContentsMargins(0, 0, 0, 0)
        diameter_layout.setSpacing(8)
        self.diameter_label = QLabel(tr("results.diameter_estimate"))
        self.diameter_label.setObjectName("largeText")
        self.pred_diameter.setMinimumWidth(96)
        diameter_layout.addWidget(self.diameter_label)
        diameter_layout.addWidget(self.pred_diameter)
        diameter_layout.addStretch()
        params_layout.addWidget(diameter_row)

        self.advanced_prediction_button = self.advanced_params_button(
            [
                (tr("results.padding"), self.pred_padding),
                (tr("results.cellprob"), self.pred_cellprob),
                (tr("results.flow"), self.pred_flow),
            ]
        )
        params_layout.addWidget(self.advanced_prediction_button)

        # O nome do modelo ativo (self.predict_model_label) continua sendo
        # atualizado em ui/model_presenter.py, mas nao e mais exibido aqui -
        # e redundante com a selecao de modelo na barra lateral.
        self.results_parameters_label = QLabel(tr("results.parameters"))
        model_layout.addWidget(self.results_parameters_label, 0, 0)
        model_layout.addWidget(params_row, 0, 1)
        model_layout.addWidget(self.results_calibration_label, 1, 1)
        # Botoes ficam numa segunda coluna do card, empilhados.
        predict_actions = QVBoxLayout()
        predict_actions.setSpacing(6)
        self.generate_results_button = self.add_button(
            predict_actions,
            tr("results.generate"),
            self.run_results_for_selected_images,
            primary=True,
        )
        self.view_results_button = self.add_button(predict_actions, tr("results.view"), self.open_results_viewer)
        self.view_results_button.setObjectName("accent")
        self.export_results_button = self.add_button(
            predict_actions, tr("results.export"), self.export_result_csvs
        )
        self.export_results_button.hide()
        predict_actions.addStretch()
        self.result_progress_label = QLabel(tr("results.waiting"))
        self.result_progress_label.setObjectName("hint")
        self.result_progress_label.setWordWrap(True)
        self.result_progress_bar = QProgressBar()
        self.result_progress_bar.setRange(0, 100)
        self.result_progress_bar.setValue(0)
        self.result_progress_bar.setFormat("%p%")
        self.result_progress_bar.setTextVisible(True)
        model_layout.addWidget(self.result_progress_label, 2, 1)
        model_layout.addWidget(self.result_progress_bar, 3, 1)
        model_layout.setRowStretch(4, 1)
        card_layout.addWidget(card_content, 1)
        card_layout.addLayout(predict_actions, 1)
        self._results_images_panel = self.panel(tr("results.images"))
        left = self._results_images_panel
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
        self.result_images_table.setHorizontalHeaderLabels(
            ["", tr("results.header_image"), tr("results.header_overlay"), tr("results.header_metrics")]
        )
        self.result_images_table.verticalHeader().setVisible(False)
        self.result_images_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.result_images_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.result_images_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.result_images_table.currentCellChanged.connect(
            lambda row, _col, _previous_row, _previous_col: self.show_result_table_row(row)
        )
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
        layout.addWidget(self.results_sidebar_host, 0, 0)
        layout.addWidget(left, 0, 1)
        layout.addWidget(model_box, 1, 0, 1, 2)
        layout.setRowStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        self._results_viewer_panel = self.panel(tr("results.viewer"))
        center = self._results_viewer_panel
        center_layout = QVBoxLayout(center)
        mode_layout = QHBoxLayout()
        self.view_buttons = {}
        self._view_mode_keys = {
            "original": "results.mode_original",
            "overlay": "results.mode_mask",
            "overlay_50pct": "results.mode_freq_50",
            "overlay_inteiros": "results.mode_freq_100",
            "overlay_diametro": "results.mode_diameter",
            "overlay_diametro_cruzado": "results.mode_diameter_cross",
        }
        for mode, key in self._view_mode_keys.items():
            button = self.add_mode_button(
                mode_layout, tr(key), lambda checked=False, selected=mode: self.set_view_mode(selected)
            )
            self.view_buttons[mode] = button
        mode_layout.addStretch()
        self.vessel_colorful_checkbox = QCheckBox(tr("results.colorful"))
        self.vessel_colorful_checkbox.setChecked(True)
        self.vessel_colorful_checkbox.toggled.connect(self.set_vessel_colorful)
        mode_layout.addWidget(self.vessel_colorful_checkbox)
        center_layout.addLayout(mode_layout)
        self.preview_label = AnnotationPreviewLabel(
            None,
            None,
            None,
            double_click_callback=self.open_selected_result_mask_editor,
            draw_button=None,
        )
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        # Imagem + circulo de referencia do diametro logo abaixo, alinhado a
        # esquerda da imagem, dentro de uma area com zoom pela roda do mouse
        # (ver zoom_viewer em ui/analysis_presenter.py).
        self.diameter_preview = DiameterPreviewWidget()
        viewer_column = QWidget()
        viewer_column_layout = QVBoxLayout(viewer_column)
        viewer_column_layout.setContentsMargins(0, 0, 0, 0)
        viewer_column_layout.setSpacing(VIEWER_CIRCLE_GAP)
        viewer_column_layout.addWidget(self.preview_label, 1)
        viewer_column_layout.addWidget(self.diameter_preview, 0, Qt.AlignmentFlag.AlignLeft)
        viewer_canvas = QWidget()
        viewer_canvas.setObjectName("viewerCanvas")
        canvas_layout = QHBoxLayout(viewer_canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.addWidget(viewer_column, 0, Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll = ZoomScrollArea(self.zoom_viewer)
        self.preview_scroll.setObjectName("viewerScroll")
        self.preview_scroll.setWidgetResizable(True)
        self.preview_scroll.setMinimumSize(320, 240)
        self.preview_scroll.setWidget(viewer_canvas)
        center_layout.addWidget(self.preview_scroll, 1)
        self.preview_label.pixmap_changed_callback = self.on_viewer_pixmap_changed
        self.on_viewer_pixmap_changed()
        self.update_diameter_preview()
        edit_mask_layout = QHBoxLayout()
        self.export_image_button = self.add_button(
            edit_mask_layout, tr("results.export_image"), self.export_context_result_images
        )
        self.edit_mask_button = self.add_button(
            edit_mask_layout, tr("results.edit_mask"), self.open_selected_result_mask_editor
        )
        edit_mask_layout.addStretch()
        center_layout.addLayout(edit_mask_layout)
        layout.addWidget(center, 0, 2, 2, 1)

    def retranslate_results_page(self):
        self._results_prediction_panel.setTitle(tr("results.prediction"))
        self.diameter_label.setText(tr("results.diameter_estimate"))
        self.results_parameters_label.setText(tr("results.parameters"))
        self.generate_results_button.setText(tr("results.generate"))
        self.view_results_button.setText(tr("results.view"))
        self.export_results_button.setText(tr("results.export"))
        self._results_images_panel.setTitle(tr("results.images"))
        self.result_images_table.setHorizontalHeaderLabels(
            ["", tr("results.header_image"), tr("results.header_overlay"), tr("results.header_metrics")]
        )
        self._results_viewer_panel.setTitle(tr("results.viewer"))
        for mode, button in self.view_buttons.items():
            button.setText(tr(self._view_mode_keys[mode]))
        self.vessel_colorful_checkbox.setText(tr("results.colorful"))
        self.export_image_button.setText(tr("results.export_image"))
        self.edit_mask_button.setText(tr("results.edit_mask"))
        self.refresh_calibration_labels()
