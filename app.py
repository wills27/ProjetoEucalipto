from pathlib import Path
import csv
import os
import re
import runpy
import shutil
import sys
import time

import numpy as np
import tifffile as tiff
from PIL import Image, ImageDraw
from PyQt6.QtCore import QProcess, QTimer, Qt
from PyQt6.QtGui import QAction, QColor, QImage, QKeySequence, QPixmap
from services.config import load_config, save_config
from services.cell_measurements import (
    build_mask_inteiros,
    compute_ellipse_minor_axis_by_label,
    filtrar_celulas_borda_proporcional,
)
from services.image_arrays import normalize_array
from services.paths import (
    PROJECT_DIR,
    SCRIPTS_DIR,
    active_model_path,
    active_project_dir,
    cell_counts_csv_path,
    cell_measurements_csv_path,
    conversion_input_dir,
    dataset_plan_path,
    ensure_project_structure,
    list_projects,
    metrics_csv_path,
    model_outputs_dir,
    overlays_dir,
    predictions_dir,
    projects_dir,
    project_models_dir,
    project_path,
    relative_to_project,
)
from services.dataset_plan import auto_split_indices, load_plan, save_plan, summarize_table_entries
from services.metrics import count_files, format_size, read_metrics, summarize_metrics
from services.training_log_parser import parse_training_log_line
from ui.annotation_page import AnnotationPage
from ui.loss_plot import LossPlotWidget
from ui.styles import APP_STYLE
from ui.widgets import AnnotationPreviewLabel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QInputDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


IMAGE_EXTENSIONS = [".tif", ".tiff", ".png", ".jpg", ".jpeg"]


class CellposeWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.config = load_config()
        self.process = None
        self.pending_actions = []
        self.pending_annotation_image_name = None
        self.current_process_title = ""
        self.current_process_error = ""
        self.result_process_titles = {"Gerar resultados"}
        self.training_start_time = None
        self.current_view_mode = "overlay"
        self.nav_buttons = []
        self.metric_labels = {}
        self.analysis_metric_labels = {}
        self.analysis_cache = {}

        self.setWindowTitle("Cellpose - Vasos de Eucalipto")
        self.resize(1320, 820)
        self.setMinimumSize(1100, 700)

        self.build_menu()
        self.build_ui()
        self.training_timer = QTimer(self)
        self.training_timer.timeout.connect(self.update_training_elapsed)
        self.refresh_all()

    def build_menu(self):
        menu_bar = self.menuBar()
        menu_bar.setNativeMenuBar(False)

        file_menu = menu_bar.addMenu("Arquivo")
        self.add_menu_action(file_menu, "Abrir projeto ativo", lambda: self.open_folder(active_project_dir(self.config)), "Ctrl+O")
        self.add_menu_action(file_menu, "Escolher pasta de projetos", self.choose_projects_folder)
        self.add_menu_action(file_menu, "Abrir pasta de modelos", lambda: self.open_folder(project_models_dir(self.config)))
        self.add_menu_action(file_menu, "Abrir pasta de outputs", lambda: self.open_folder(model_outputs_dir(self.config)))
        self.add_menu_action(file_menu, "Importar imagens e _seg.npy", self.import_dataset_folder)
        file_menu.addSeparator()
        self.add_menu_action(file_menu, "Sair", self.close, "Ctrl+Q")

        project_menu = menu_bar.addMenu("Projeto")
        self.add_menu_action(project_menu, "Criar projeto", self.create_project, "Ctrl+N")
        self.add_menu_action(project_menu, "Preparar dataset", self.run_prepare_dataset)
        self.add_menu_action(project_menu, "Ir para Inicio", lambda: self.set_page(0))
        self.add_menu_action(project_menu, "Ir para Dados", lambda: self.set_page(1))

        model_menu = menu_bar.addMenu("Modelo")
        self.add_menu_action(model_menu, "Ir para Treinar", lambda: self.set_page(2))
        self.add_menu_action(model_menu, "Treinar modelo", self.run_training)
        self.add_menu_action(model_menu, "Selecionar modelo da tabela", self.select_project_model)

        process_menu = menu_bar.addMenu("Processar")
        self.add_menu_action(process_menu, "Ir para Resultados", lambda: self.set_page(3))
        self.add_menu_action(process_menu, "Gerar resultados", self.run_results, "Ctrl+R")
        self.add_menu_action(process_menu, "Avaliar modelo", self.run_evaluation)
        self.add_menu_action(process_menu, "Gerar CSVs de medidas", self.run_cell_measurements)

        help_menu = menu_bar.addMenu("Ajuda")
        self.add_menu_action(help_menu, "Sobre", self.show_about)

    def add_menu_action(self, menu, text, callback, shortcut=None):
        action = QAction(text, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(callback)
        menu.addAction(action)
        return action

    def build_ui(self):
        root = QWidget()
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
            ("Dados", self.build_dataset_page),
            ("Treinar", self.build_train_page),
            ("Resultados", self.build_results_page),
        ]:
            button = QPushButton(label)
            button.setObjectName("nav")
            button.clicked.connect(lambda checked=False, index=len(self.nav_buttons): self.set_page(index))
            self.nav_buttons.append(button)
            sidebar_layout.addWidget(button)
            page = QWidget()
            builder(page)
            self.stack.addWidget(page)

        sidebar_layout.addStretch()
        self.add_button(sidebar_layout, "Atualizar", self.refresh_all)

        self.log_text = QTextEdit(self)
        self.log_text.setReadOnly(True)
        self.log_text.hide()

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
        project_layout.addWidget(QLabel("Projeto"), 0, 0)
        project_layout.addWidget(self.project_combo, 0, 1)
        project_actions = QHBoxLayout()
        self.add_button(project_actions, "Criar projeto", self.create_project)
        self.add_button(project_actions, "Abrir pasta", lambda: self.open_folder(active_project_dir(self.config)))
        self.add_button(project_actions, "Pasta de projetos", self.choose_projects_folder)
        project_actions.addStretch()
        project_layout.addLayout(project_actions, 0, 2)
        layout.addWidget(project_box)

        center_row = QHBoxLayout()
        center_row.setSpacing(12)

        model_box = self.panel("Modelo ativo")
        model_layout = QVBoxLayout(model_box)
        self.model_name_value = QLabel("-")
        self.model_name_value.setObjectName("largeText")
        self.model_name_value.setWordWrap(True)
        model_layout.addWidget(self.model_name_value)
        self.project_models_table = QTableWidget(0, 4)
        self.project_models_table.setHorizontalHeaderLabels(["Modelo", "Tamanho", "Modificado", "Metricas"])
        self.project_models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.project_models_table.verticalHeader().setVisible(False)
        self.project_models_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.project_models_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.project_models_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.project_models_table.cellDoubleClicked.connect(lambda _row, _col: self.select_project_model())
        self.project_models_table.setAlternatingRowColors(True)
        self.project_models_table.setMinimumHeight(220)
        model_layout.addWidget(self.project_models_table)
        model_actions = QHBoxLayout()
        self.add_button(model_actions, "Usar modelo selecionado", self.select_project_model, primary=True)
        self.add_button(model_actions, "Treinar novo modelo", lambda: self.set_page(2))
        self.add_button(model_actions, "Abrir pasta models", lambda: self.open_folder(project_models_dir(self.config)))
        model_actions.addStretch()
        model_layout.addLayout(model_actions)
        center_row.addWidget(model_box, 2)

        next_box = self.panel("Proximo passo")
        next_layout = QVBoxLayout(next_box)
        self.next_step_label = QLabel("Atualizando status do projeto.")
        self.next_step_label.setObjectName("largeText")
        self.next_step_label.setWordWrap(True)
        self.next_step_detail_label = QLabel()
        self.next_step_detail_label.setObjectName("hint")
        self.next_step_detail_label.setWordWrap(True)
        self.next_step_button = QPushButton("Atualizar")
        self.next_step_button.setObjectName("primary")
        self.next_step_button.clicked.connect(self.refresh_all)
        next_layout.addWidget(self.next_step_label)
        next_layout.addWidget(self.next_step_detail_label)
        next_layout.addStretch()
        next_layout.addWidget(self.next_step_button)
        center_row.addWidget(next_box, 1)
        layout.addLayout(center_row, 1)
        layout.addStretch()

    def build_dataset_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        validation_box = self.panel("Selecao e divisao do dataset")
        validation_layout = QHBoxLayout(validation_box)
        table_layout = QVBoxLayout()
        self.dataset_validation_summary = QLabel()
        self.dataset_validation_summary.setObjectName("mono")
        table_layout.addWidget(self.dataset_validation_summary)
        self.dataset_pairs_table = QTableWidget(0, 5)
        self.dataset_pairs_table.setHorizontalHeaderLabels(["Usar", "Grupo", "Imagem", "Segmentacao", "Status"])
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.verticalHeader().setVisible(False)
        self.dataset_pairs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.dataset_pairs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.dataset_pairs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.dataset_pairs_table.itemChanged.connect(self.save_dataset_plan_from_table)
        self.dataset_pairs_table.itemSelectionChanged.connect(self.show_selected_dataset_pair)
        table_layout.addWidget(self.dataset_pairs_table, 1)
        validation_actions = QHBoxLayout()
        self.add_button(validation_actions, "Importar pasta", self.import_dataset_folder)
        self.add_button(validation_actions, "Converter para TIFF", self.convert_dataset_images_to_tif)
        self.add_button(validation_actions, "Atualizar validacao", self.refresh_dataset_import)
        self.add_button(validation_actions, "Dividir automaticamente", self.auto_split_dataset_table)
        self.add_button(validation_actions, "Preparar train/val/test", self.run_prepare_dataset, primary=True)
        validation_actions.addStretch()
        table_layout.addLayout(validation_actions)
        validation_layout.addLayout(table_layout, 2)

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
        self.dataset_preview_label.setMinimumSize(360, 320)
        self.dataset_preview_label.setWordWrap(True)
        self.dataset_preview_info = QLabel("Imagem e mascara aparecem aqui. Duplo clique para editar a mascara.")
        self.dataset_preview_info.setObjectName("hint")
        self.dataset_preview_info.setWordWrap(True)
        preview_layout.addWidget(self.dataset_preview_label, 1)
        preview_layout.addWidget(self.dataset_preview_info)
        validation_layout.addLayout(preview_layout, 1)
        layout.addWidget(validation_box, 1)

        self.annotation_page = AnnotationPage(self, build_ui=False)

    def build_train_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        form_box = self.panel("Novo modelo")
        form_layout = QGridLayout(form_box)
        form_layout.setContentsMargins(10, 8, 10, 10)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(6)
        self.train_model_name = QLineEdit("cpsam_vasos_eucalipto_v2")
        self.train_base_model = QLineEdit("cpsam")
        self.train_epochs = QSpinBox()
        self.train_epochs.setRange(1, 10000)
        self.train_epochs.setValue(100)
        self.train_learning_rate = QLineEdit("1e-5")
        self.train_weight_decay = QLineEdit("0.1")
        self.train_batch_size = QSpinBox()
        self.train_batch_size.setRange(1, 512)
        self.train_batch_size.setValue(1)
        self.train_epochs.setFixedWidth(104)
        self.train_batch_size.setFixedWidth(92)
        for field in [self.train_learning_rate, self.train_weight_decay]:
            field.setFixedWidth(104)

        training_params = QWidget()
        training_params_layout = QGridLayout(training_params)
        training_params_layout.setContentsMargins(0, 0, 0, 0)
        training_params_layout.setHorizontalSpacing(8)
        training_params_layout.setVerticalSpacing(6)
        for index, (label, field) in enumerate([
            ("Epocas", self.train_epochs),
            ("Learning rate", self.train_learning_rate),
            ("Weight decay", self.train_weight_decay),
            ("Batch", self.train_batch_size),
        ]):
            row = index // 2
            column = (index % 2) * 2
            training_params_layout.addWidget(QLabel(label), row, column)
            training_params_layout.addWidget(field, row, column + 1)
        training_params_layout.setColumnStretch(4, 1)

        form_layout.addWidget(QLabel("Nome do modelo"), 0, 0)
        form_layout.addWidget(self.train_model_name, 0, 1)
        form_layout.addWidget(QLabel("Modelo base"), 1, 0)
        form_layout.addWidget(self.train_base_model, 1, 1)
        form_layout.addWidget(QLabel("Parametros"), 2, 0)
        form_layout.addWidget(training_params, 2, 1)
        train_button = QPushButton("Iniciar treinamento")
        train_button.setObjectName("primary")
        train_button.clicked.connect(self.run_training)
        form_layout.addWidget(train_button, 3, 1)
        top_layout.addWidget(form_box, 1)

        progress_box = self.panel("Status do treino")
        progress_layout = QVBoxLayout(progress_box)
        self.training_status_label = QLabel("Aguardando treino.")
        self.training_status_label.setObjectName("largeText")
        self.training_model_label = QLabel("Modelo: -")
        self.training_elapsed_label = QLabel("Tempo decorrido: 00:00:00")
        self.training_epoch_label = QLabel("Epocas: 0/0")
        self.training_epoch_label.setObjectName("largeText")
        self.training_epoch_progress = QProgressBar()
        self.training_epoch_progress.setRange(0, 100)
        self.training_epoch_progress.setValue(0)
        self.training_epoch_progress.setFormat("%p%")
        self.training_epoch_progress.setTextVisible(True)
        self.training_detail_label = QLabel("Detalhes: aguardando inicio")
        self.training_detail_label.setWordWrap(True)
        self.training_detail_label.setObjectName("hint")
        training_metrics = QFrame()
        training_metrics.setObjectName("trainingMetrics")
        training_metrics_layout = QGridLayout(training_metrics)
        training_metrics_layout.setContentsMargins(10, 8, 10, 8)
        training_metrics_layout.setSpacing(8)
        self.training_train_loss_label = QLabel("-")
        self.training_val_loss_label = QLabel("-")
        self.training_lr_label = QLabel("-")
        self.training_internal_time_label = QLabel("-")
        for column, (label, value) in enumerate(
            [
                ("Loss treino", self.training_train_loss_label),
                ("Loss validacao", self.training_val_loss_label),
                ("Learning rate", self.training_lr_label),
                ("Tempo Cellpose", self.training_internal_time_label),
            ]
        ):
            title = QLabel(label)
            title.setObjectName("metricTitle")
            value.setObjectName("metricValue")
            training_metrics_layout.addWidget(title, 0, column)
            training_metrics_layout.addWidget(value, 1, column)
        self.training_end_hint_label = QLabel("Fim real: quando a etapa 'Modelo salvo' for marcada e o processo encerrar.")
        self.training_end_hint_label.setObjectName("hint")
        self.training_saved_model_label = QLabel("Modelo salvo em: -")
        self.training_saved_model_label.setObjectName("hint")
        self.training_last_message_label = QLabel("Atualizacao: -")
        self.training_last_message_label.setWordWrap(True)
        self.training_steps_table = QTableWidget(0, 2)
        self.training_steps_table.setHorizontalHeaderLabels(["Etapa", "Status"])
        self.training_steps_table.verticalHeader().setVisible(False)
        self.training_steps_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.training_steps_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.training_steps_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.training_steps_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.training_steps = [
            ("dados_treino", "Carregar dados de treino"),
            ("dados_validacao", "Carregar dados de validacao"),
            ("inicializar_modelo", "Inicializar modelo"),
            ("treinar", "Treinar modelo"),
            ("modelo_salvo", "Modelo salvo"),
            ("concluido", "Concluido"),
        ]
        self.reset_training_steps()
        progress_layout.addWidget(self.training_status_label)
        progress_layout.addWidget(self.training_model_label)
        progress_layout.addWidget(self.training_elapsed_label)
        progress_layout.addWidget(self.training_epoch_label)
        progress_layout.addWidget(self.training_epoch_progress)
        progress_layout.addWidget(self.training_detail_label)
        progress_layout.addWidget(training_metrics)
        progress_layout.addWidget(self.training_end_hint_label)
        progress_layout.addWidget(self.training_steps_table)
        progress_layout.addWidget(self.training_saved_model_label)
        progress_layout.addWidget(self.training_last_message_label)
        progress_layout.addStretch()
        top_layout.addWidget(progress_box, 1)

        layout.addLayout(top_layout)

        loss_box = self.panel("Grafico de perda")
        loss_layout = QVBoxLayout(loss_box)
        self.loss_plot = LossPlotWidget(self.train_epochs.value())
        self.train_epochs.valueChanged.connect(lambda value: self.loss_plot.reset(value))
        loss_layout.addWidget(self.loss_plot, 1)
        layout.addWidget(loss_box, 1)

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
        self.pred_input = QLineEdit(self.config["test_images_dir"])
        self.pred_output = QLineEdit(self.config["predictions_dir"])
        self.pred_output.setReadOnly(True)
        self.pred_padding = QSpinBox()
        self.pred_padding.setRange(0, 2048)
        self.pred_padding.setValue(int(self.config["padding_pixels"]))
        self.pred_diameter = QLineEdit(str(self.config["diameter"]))
        self.pred_cellprob = QLineEdit(str(self.config["cellprob_threshold"]))
        self.pred_flow = QLineEdit(str(self.config["flow_threshold"]))
        self.pred_padding.setFixedWidth(82)
        for field in [self.pred_diameter, self.pred_cellprob, self.pred_flow]:
            field.setFixedWidth(86)

        params_row = QWidget()
        params_layout = QHBoxLayout(params_row)
        params_layout.setContentsMargins(0, 0, 0, 0)
        params_layout.setSpacing(8)
        for label, field in [
            ("Padding", self.pred_padding),
            ("Diametro", self.pred_diameter),
            ("Cell prob", self.pred_cellprob),
            ("Flow", self.pred_flow),
        ]:
            params_layout.addWidget(QLabel(label))
            params_layout.addWidget(field)
        params_layout.addStretch()

        model_header = QWidget()
        model_header_layout = QHBoxLayout(model_header)
        model_header_layout.setContentsMargins(0, 0, 0, 0)
        model_header_layout.setSpacing(8)
        model_header_layout.addWidget(QLabel("Modelo usado:"))
        model_header_layout.addWidget(self.predict_model_label, 1)
        self.add_button(model_header_layout, "Importar", self.import_prediction_model)

        self.prediction_model_combo = QComboBox()
        self.prediction_model_combo.currentIndexChanged.connect(self.on_prediction_model_changed)

        input_row = QWidget()
        input_row_layout = QHBoxLayout(input_row)
        input_row_layout.setContentsMargins(0, 0, 0, 0)
        input_row_layout.setSpacing(8)
        input_row_layout.addWidget(self.path_field(self.pred_input), 1)
        self.add_button(input_row_layout, "Importar imagens", self.import_prediction_images)

        model_layout.addWidget(model_header, 0, 0, 1, 2)
        model_layout.addWidget(QLabel("Modelos salvos"), 1, 0)
        model_layout.addWidget(self.prediction_model_combo, 1, 1)
        model_layout.addWidget(QLabel("Pasta de entrada"), 2, 0)
        model_layout.addWidget(input_row, 2, 1)
        model_layout.addWidget(QLabel("Pasta de saida"), 3, 0)
        model_layout.addWidget(self.pred_output, 3, 1)
        model_layout.addWidget(QLabel("Parametros"), 4, 0)
        model_layout.addWidget(params_row, 4, 1)
        predict_actions = QHBoxLayout()
        self.add_button(predict_actions, "Gerar resultados", self.run_results, primary=True)
        predict_actions.addStretch()
        model_layout.addLayout(predict_actions, 5, 1)
        self.result_progress_label = QLabel("Aguardando processo.")
        self.result_progress_label.setObjectName("hint")
        self.result_progress_label.setWordWrap(True)
        self.result_progress_bar = QProgressBar()
        self.result_progress_bar.setRange(0, 100)
        self.result_progress_bar.setValue(0)
        self.result_progress_bar.setFormat("%p%")
        self.result_progress_bar.setTextVisible(True)
        model_layout.addWidget(self.result_progress_label, 6, 1)
        model_layout.addWidget(self.result_progress_bar, 7, 1)
        left_column.addWidget(model_box)

        left = self.panel("Imagens")
        left_layout = QVBoxLayout(left)
        self.image_list = QListWidget()
        self.image_list.currentTextChanged.connect(self.show_analysis_image)
        left_layout.addWidget(self.image_list, 1)
        self.add_button(left_layout, "Atualizar lista", self.refresh_analysis_images)
        left_column.addWidget(left, 1)
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
        center_layout.addLayout(mode_layout)
        self.preview_label = QLabel("Selecione uma imagem.")
        self.preview_label.setObjectName("preview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setMinimumSize(640, 520)
        center_layout.addWidget(self.preview_label, 1)

        measurements_box = self.panel("Dados gerados")
        measurements_box.setMaximumHeight(260)
        measurements_layout = QVBoxLayout(measurements_box)
        self.measurements_status_label = QLabel("Gere os CSVs de medidas para visualizar os dados aqui.")
        self.measurements_status_label.setObjectName("hint")
        self.measurements_status_label.setWordWrap(True)
        self.measurements_tabs = QTabWidget()
        self.cell_counts_table = QTableWidget(0, 0)
        self.cell_measurements_table = QTableWidget(0, 0)
        for table in [self.cell_counts_table, self.cell_measurements_table]:
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setAlternatingRowColors(True)
            table.verticalHeader().setVisible(False)
            table.setSortingEnabled(True)
        self.measurements_tabs.addTab(self.cell_counts_table, "Contagens")
        self.measurements_tabs.addTab(self.cell_measurements_table, "Medidas")
        measurement_actions = QHBoxLayout()
        self.add_button(measurement_actions, "Atualizar dados", self.refresh_measurement_tables)
        measurement_actions.addStretch()
        measurements_layout.addWidget(self.measurements_status_label)
        measurements_layout.addWidget(self.measurements_tabs, 1)
        measurements_layout.addLayout(measurement_actions)
        center_layout.addWidget(measurements_box, 0)
        layout.addWidget(center, 1)

        right = self.panel("Metricas da imagem")
        right_layout = QVBoxLayout(right)
        for label in ["Dice", "IoU", "Precision", "Recall", "GT objects", "Pred objects"]:
            card, value = self.metric_card(label)
            self.analysis_metric_labels[label] = value
            right_layout.addWidget(card)
        self.add_button(right_layout, "Rodar avaliacao", self.run_evaluation, primary=True)
        self.add_button(right_layout, "Gerar CSVs de medidas", self.run_cell_measurements)
        self.add_button(right_layout, "Abrir medidas", lambda: self.open_file(cell_measurements_csv_path(self.config)))
        self.add_button(right_layout, "Abrir contagens", lambda: self.open_file(cell_counts_csv_path(self.config)))
        self.add_button(right_layout, "Abrir metricas", lambda: self.open_file(metrics_csv_path(self.config)))
        self.add_button(right_layout, "Abrir pasta de outputs", lambda: self.open_folder(model_outputs_dir(self.config)))
        right_layout.addStretch()
        layout.addWidget(right, 0)

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

    def set_page(self, index):
        self.stack.setCurrentIndex(index)
        for button_index, button in enumerate(self.nav_buttons):
            button.setProperty("active", button_index == index)
            button.style().unpolish(button)
            button.style().polish(button)

    def set_view_mode(self, mode):
        self.current_view_mode = mode
        for key, button in self.view_buttons.items():
            button.setProperty("active", key == mode)
            button.style().unpolish(button)
            button.style().polish(button)
        current = self.image_list.currentItem()
        if current:
            self.show_analysis_image(current.text())

    def select_project(self, project_name):
        if not project_name or project_name == self.config.get("active_project"):
            return
        self.reset_project_dependent_state()
        self.config["active_project"] = project_name
        models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
        if models:
            self.config["active_model"] = models[0]
        else:
            self.config["active_model"] = ""
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.analysis_cache.clear()
        save_config(self.config)
        self.refresh_all()

    def create_project(self):
        name, ok = QInputDialog.getText(self, "Criar projeto", "Nome do projeto:")
        if not ok:
            return
        name = name.strip().replace(" ", "_")
        if not name:
            return
        self.reset_project_dependent_state()
        self.config["active_project"] = name
        self.config["active_model"] = ""
        ensure_project_structure(active_project_dir(self.config))
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)
        self.refresh_all()

    def reset_project_dependent_state(self):
        self.pending_annotation_image_name = None
        self.analysis_cache.clear()
        if hasattr(self, "annotation_page"):
            self.annotation_page.current_image_entry = None
            self.annotation_page.base_image = None
            self.annotation_page.mask = None
            self.annotation_page.mask_history = []
            self.annotation_page.reset_transient_drawing()
        if hasattr(self, "dataset_preview_label"):
            self.dataset_preview_label.setText("Selecione uma imagem.")
            self.dataset_preview_label.setPixmap(QPixmap())
        if hasattr(self, "dataset_preview_info"):
            self.dataset_preview_info.setText("Imagem e mascara aparecem aqui. Duplo clique para editar a mascara.")
        if hasattr(self, "preview_label"):
            self.preview_label.setText("Selecione uma imagem.")
            self.preview_label.setPixmap(QPixmap())
        if hasattr(self, "image_list"):
            self.image_list.clear()
        if hasattr(self, "result_progress_bar"):
            self.result_progress_bar.setRange(0, 100)
            self.result_progress_bar.setValue(0)
            self.result_progress_bar.setFormat("%p%")
        if hasattr(self, "result_progress_label"):
            self.result_progress_label.setText("Aguardando processo.")
        if hasattr(self, "analysis_metric_labels"):
            for value in self.analysis_metric_labels.values():
                value.setText("-")
        if hasattr(self, "cell_counts_table"):
            self.cell_counts_table.clear()
            self.cell_counts_table.setRowCount(0)
            self.cell_counts_table.setColumnCount(0)
        if hasattr(self, "cell_measurements_table"):
            self.cell_measurements_table.clear()
            self.cell_measurements_table.setRowCount(0)
            self.cell_measurements_table.setColumnCount(0)
        if hasattr(self, "measurements_status_label"):
            self.measurements_status_label.setText("Gere os CSVs de medidas para visualizar os dados aqui.")

    def choose_projects_folder(self):
        current_dir = projects_dir(self.config)
        current_dir.mkdir(parents=True, exist_ok=True)
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta de projetos", str(current_dir))
        if not folder:
            return

        self.reset_project_dependent_state()
        self.config["projects_dir"] = folder
        available_projects = list_projects(self.config)
        if available_projects:
            self.config["active_project"] = available_projects[0]
            models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
            self.config["active_model"] = models[0] if models else ""
        else:
            self.config["active_project"] = "eucalipto"
            self.config["active_model"] = ""
            ensure_project_structure(active_project_dir(self.config))
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)
        self.refresh_all()

    def run_prepare_dataset(self):
        self.save_dataset_plan_from_table()
        self.run_script(
            "Preparar dataset",
            [
                str(SCRIPTS_DIR / "prepare_dataset.py"),
                "--project-dir",
                str(active_project_dir(self.config)),
                "--plan",
                str(dataset_plan_path(self.config)),
            ],
        )

    def run_training(self):
        model_name = self.train_model_name.text().strip()
        if not model_name:
            QMessageBox.information(self, "Modelo", "Informe um nome para o modelo.")
            return

        self.config["active_model"] = model_name
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)
        args = [
            str(SCRIPTS_DIR / "train_cellpose.py"),
            "--project-dir",
            str(active_project_dir(self.config)),
            "--model-name",
            model_name,
            "--base-model",
            self.train_base_model.text().strip(),
            "--epochs",
            str(self.train_epochs.value()),
            "--learning-rate",
            self.train_learning_rate.text().strip(),
            "--weight-decay",
            self.train_weight_decay.text().strip(),
            "--batch-size",
            str(self.train_batch_size.value()),
            "--require-gpu",
        ]
        self.run_script("Treinar modelo", args)

    def run_results(self):
        if not self.ensure_active_model():
            return
        self.analysis_cache.clear()
        self.save_prediction_config()
        args = [
            str(SCRIPTS_DIR / "generate_results.py"),
            "--model",
            str(active_model_path(self.config)),
            "--input",
            str(project_path(self.config["test_images_dir"], self.config)),
            "--predictions-output",
            str(predictions_dir(self.config)),
            "--overlays-output",
            str(overlays_dir(self.config)),
            "--padding",
            str(self.config["padding_pixels"]),
            "--diameter",
            str(self.config["diameter"]),
            "--cellprob-threshold",
            str(self.config["cellprob_threshold"]),
            "--flow-threshold",
            str(self.config["flow_threshold"]),
        ]
        self.run_script("Gerar resultados", args)

    def import_prediction_model(self):
        files, _filter = QFileDialog.getOpenFileNames(
            self,
            "Escolher modelos para importar",
            str(project_models_dir(self.config)),
            "Arquivos de modelo (*.*)",
        )
        if not files:
            return

        target_dir = project_models_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        skipped = 0
        last_model_name = None
        for file_name in files:
            source_path = Path(file_name)
            if not source_path.is_file():
                continue
            destination_path = target_dir / source_path.name
            if destination_path.exists():
                skipped += 1
                continue
            shutil.copy2(source_path, destination_path)
            copied += 1
            last_model_name = destination_path.name

        if last_model_name:
            self.config["active_model"] = last_model_name
            self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
            self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
            save_config(self.config)

        self.append_log(
            f"\n>>> Importar modelos\n"
            f"Destino: {target_dir}\n"
            f"Copiados: {copied}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        self.refresh_all()

    def import_prediction_images(self):
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = project_path(self.pred_input.text().strip() or self.config["test_images_dir"], self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        converted = 0
        skipped = 0

        for src in sorted(source_dir.iterdir()):
            if not src.is_file():
                continue
            if src.stem.endswith("_masks") or src.stem.endswith("_pred_mask") or src.name.endswith("_seg.npy"):
                continue

            suffix = src.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}:
                continue

            if suffix in {".tif", ".tiff"}:
                dst = target_dir / src.name
                if dst.exists():
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
                continue

            dst = target_dir / f"{src.stem}.tif"
            if dst.exists():
                skipped += 1
                continue

            try:
                with Image.open(src) as image:
                    if image.mode == "P":
                        image = image.convert("RGB")
                    tiff.imwrite(dst, np.asarray(image))
                converted += 1
            except Exception:
                skipped += 1

        self.config["test_images_dir"] = relative_to_project(target_dir, self.config)
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        save_config(self.config)

        self.append_log(
            f"\n>>> Importar imagens para predicao\n"
            f"Origem: {source_dir}\n"
            f"Destino: {target_dir}\n"
            f"Copiados: {copied}\n"
            f"Convertidos para TIFF: {converted}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        self.refresh_all()

    def run_annotation_mask_prediction(self):
        image_path = self.current_annotation_image_path()
        if image_path is None:
            QMessageBox.information(self, "Anotar", "Selecione uma imagem para gerar ou refazer a mascara.")
            return
        if not self.ensure_active_model():
            return
        self.save_annotation_prediction_config()
        params = self.annotation_page.model_parameters()
        output_path = image_path.with_name(f"{image_path.stem}_seg.npy")
        args = [
            str(SCRIPTS_DIR / "create_mask_with_model.py"),
            "--model",
            str(active_model_path(self.config)),
            "--image",
            str(image_path),
            "--output",
            str(output_path),
            "--padding",
            str(params["padding"]),
            "--diameter",
            params["diameter"],
            "--cellprob-threshold",
            params["cellprob_threshold"],
            "--flow-threshold",
            params["flow_threshold"],
        ]
        self.pending_annotation_image_name = image_path.name
        self.annotation_page.set_status(f"Gerando mascara para {image_path.name}...")
        self.run_script("Criar mascara", args)

    def run_evaluation(self):
        if not self.ensure_active_model():
            return
        args = [
            str(SCRIPTS_DIR / "evaluate_cellpose.py"),
            "--masks",
            str(project_path(self.config["test_masks_dir"], self.config)),
            "--predictions",
            str(predictions_dir(self.config)),
            "--output-csv",
            str(metrics_csv_path(self.config)),
        ]
        self.run_script("Avaliar modelo", args)

    def run_cell_measurements(self):
        if not self.ensure_active_model():
            return
        args = [
            str(SCRIPTS_DIR / "measure_cells.py"),
            "--masks-dir",
            str(predictions_dir(self.config)),
            "--output-dir",
            str(model_outputs_dir(self.config)),
            "--pattern",
            "*_pred_masks.tif",
        ]
        self.run_script("Gerar CSVs de medidas", args)

    def save_prediction_config(self):
        self.config["test_images_dir"] = self.pred_input.text().strip()
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.config["padding_pixels"] = self.pred_padding.value()
        self.config["diameter"] = self.parse_float(self.pred_diameter.text(), 0.0)
        self.config["cellprob_threshold"] = self.parse_float(self.pred_cellprob.text(), 0.0)
        self.config["flow_threshold"] = self.parse_float(self.pred_flow.text(), 0.4)
        save_config(self.config)

    def save_annotation_prediction_config(self):
        self.annotation_page.save_model_parameters_to_config(self.config, self.parse_float)
        save_config(self.config)

    def ensure_active_model(self):
        if self.config.get("active_model") and active_model_path(self.config).exists():
            return True
        QMessageBox.information(
            self,
            "Modelo nao selecionado",
            "Este projeto ainda nao tem um modelo ativo. Treine um modelo ou selecione um modelo existente antes de continuar.",
        )
        return False

    def run_script(self, title, args):
        if self.process is not None:
            QMessageBox.information(self, "Processo em andamento", "Aguarde o processo atual terminar.")
            return

        self.current_process_title = title
        self.current_process_error = ""
        if title == "Treinar modelo":
            self.start_training_progress()
        if title in self.result_process_titles:
            self.start_result_progress(title)
        self.append_log(f"\n>>> {title}\n")
        self.append_log(" ".join([sys.executable, "-u", *args]) + "\n")

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(PROJECT_DIR))
        self.process.setProgram(sys.executable)
        if getattr(sys, "frozen", False):
            self.process.setArguments(["--run-script", *args])
        else:
            self.process.setArguments(["-u", *args])
        self.process.readyReadStandardOutput.connect(self.read_process_output)
        self.process.readyReadStandardError.connect(self.read_process_output)
        self.process.finished.connect(self.process_finished)
        self.process.start()
        self.refresh_all()

    def read_process_output(self):
        if self.process is None:
            return
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if output:
            self.append_log(output)
            self.capture_process_error(output)
            self.update_training_last_message(output)
            self.update_result_progress(output)
        if error:
            self.append_log(error)
            self.capture_process_error(error)
            self.update_training_last_message(error)
            self.update_result_progress(error)

    def process_finished(self, exit_code):
        self.append_log(f">>> Finalizado com codigo {exit_code}\n")
        if self.current_process_title in self.result_process_titles:
            self.analysis_cache.clear()
            self.finish_result_progress(exit_code)
        if self.current_process_title == "Treinar modelo":
            self.finish_training_progress(exit_code)
        if self.current_process_title == "Criar mascara" and exit_code == 0:
            self.set_annotation_view_mode("overlay")
            if hasattr(self, "annotation_page") and self.pending_annotation_image_name:
                self.annotation_page.set_status(f"Mascara atualizada: {self.pending_annotation_image_name}")
        if exit_code != 0:
            self.show_process_error(exit_code)
        self.process = None
        self.current_process_title = ""
        self.config = load_config()
        self.refresh_all()
        if self.pending_actions:
            next_action = self.pending_actions.pop(0)
            next_action()

    def append_log(self, text):
        self.log_text.moveCursor(self.log_text.textCursor().MoveOperation.End)
        self.log_text.insertPlainText(text)
        self.log_text.moveCursor(self.log_text.textCursor().MoveOperation.End)

    def capture_process_error(self, text):
        error_markers = ["Traceback", "Error:", "Exception", "RuntimeError", "FileNotFoundError", "CUDA out of memory"]
        if any(marker in text for marker in error_markers):
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            if lines:
                self.current_process_error = "\n".join(lines[-8:])

    def show_process_error(self, exit_code):
        message = self.current_process_error or "O processo terminou com erro, mas nao retornou detalhes."
        if self.current_process_title == "Treinar modelo":
            self.training_status_label.setText("Treino finalizado com erro.")
            self.training_last_message_label.setText(f"Erro: {message.splitlines()[-1]}")
        QMessageBox.critical(
            self,
            "Erro no processo",
            f"{self.current_process_title or 'Processo'} terminou com codigo {exit_code}.\n\n{message}",
        )

    def start_result_progress(self, title):
        if not hasattr(self, "result_progress_bar"):
            return
        self.result_progress_bar.setRange(0, 100)
        self.result_progress_bar.setValue(0)
        self.result_progress_label.setText(f"{title}: iniciando.")

    def update_result_progress(self, text):
        if self.current_process_title not in self.result_process_titles:
            return
        if not hasattr(self, "result_progress_bar"):
            return
        for line in text.splitlines():
            match = re.match(r"^PROGRESS\s+(\d+)\s+(\d+)\s*(.*)$", line.strip())
            if not match:
                continue
            current = int(match.group(1))
            total = max(1, int(match.group(2)))
            detail = match.group(3).strip()
            self.result_progress_bar.setRange(0, total)
            self.result_progress_bar.setValue(min(current, total))
            self.result_progress_bar.setFormat(f"{current}/{total}")
            if detail:
                self.result_progress_label.setText(detail)

    def finish_result_progress(self, exit_code):
        if not hasattr(self, "result_progress_bar"):
            return
        if exit_code == 0:
            maximum = self.result_progress_bar.maximum()
            self.result_progress_bar.setValue(maximum)
            self.result_progress_bar.setFormat("100%")
            self.result_progress_label.setText(f"{self.current_process_title}: concluido.")
        else:
            self.result_progress_label.setText(f"{self.current_process_title}: erro.")

    def reset_training_steps(self):
        self.training_step_states = {key: "Pendente" for key, _label in self.training_steps}
        self.training_steps_table.setRowCount(len(self.training_steps))
        for row, (key, label) in enumerate(self.training_steps):
            self.training_steps_table.setItem(row, 0, QTableWidgetItem(label))
            self.training_steps_table.setItem(row, 1, QTableWidgetItem(self.training_step_states[key]))
        self.training_steps_table.resizeColumnsToContents()

    def set_training_step(self, key, state):
        if key not in getattr(self, "training_step_states", {}):
            return
        self.training_step_states[key] = state
        for row, (step_key, _label) in enumerate(self.training_steps):
            if step_key == key:
                self.training_steps_table.setItem(row, 1, QTableWidgetItem(state))
                break

    def complete_previous_training_steps(self, current_key):
        order = [key for key, _label in self.training_steps]
        if current_key not in order:
            return
        for key in order[: order.index(current_key)]:
            if self.training_step_states.get(key) in ["Pendente", "Em andamento"]:
                self.set_training_step(key, "Concluido")

    def start_training_progress(self):
        self.training_start_time = time.time()
        self.reset_training_steps()
        self.loss_plot.reset(self.train_epochs.value())
        self.training_status_label.setText("Treinando...")
        self.training_model_label.setText(f"Modelo: {self.train_model_name.text().strip()}")
        self.training_epoch_progress.setRange(0, self.train_epochs.value())
        self.training_epoch_progress.setValue(0)
        self.training_epoch_label.setText(f"Epocas: 0/{self.train_epochs.value()}")
        self.training_detail_label.setText("Detalhes: preparando dados e inicializando o treino")
        self.training_train_loss_label.setText("-")
        self.training_val_loss_label.setText("-")
        self.training_lr_label.setText("-")
        self.training_internal_time_label.setText("-")
        self.training_saved_model_label.setText("Modelo salvo em: -")
        self.training_last_message_label.setText("Atualizacao: iniciando treino")
        self.training_timer.start(1000)
        self.update_training_elapsed()

    def finish_training_progress(self, exit_code):
        self.training_timer.stop()
        if exit_code == 0:
            self.training_epoch_progress.setValue(self.train_epochs.value())
            self.training_epoch_label.setText(f"Epocas: {self.train_epochs.value()}/{self.train_epochs.value()}")
            self.training_detail_label.setText("Detalhes: treino concluido e modelo salvo")
            self.training_last_message_label.setText("Atualizacao: treinamento concluido com sucesso")
            self.complete_previous_training_steps("concluido")
            self.set_training_step("concluido", "Concluido")
            self.training_status_label.setText("Treino concluido.")
        else:
            for key, state in self.training_step_states.items():
                if state == "Em andamento":
                    self.set_training_step(key, "Erro")
                    break
            self.training_detail_label.setText(self.friendly_error_message())
            self.training_last_message_label.setText("Atualizacao: consulte o log para os detalhes tecnicos")
            self.training_status_label.setText("Treino finalizado com erro.")
        self.update_training_elapsed()

    def update_training_elapsed(self):
        if self.training_start_time is None:
            return
        elapsed = int(time.time() - self.training_start_time)
        hours = elapsed // 3600
        minutes = (elapsed % 3600) // 60
        seconds = elapsed % 60
        self.training_elapsed_label.setText(f"Tempo decorrido: {hours:02d}:{minutes:02d}:{seconds:02d}")

    def update_training_last_message(self, text):
        if self.current_process_title != "Treinar modelo":
            return
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return
        for line in lines:
            event = parse_training_log_line(line, self.friendly_error_message)
            if event:
                self.apply_training_event(event)

    def apply_training_event(self, event):
        event_type = event["type"]
        if event_type == "epoch":
            self.update_training_epoch(event)
        elif event_type == "stage":
            self.update_training_stage(event)
        elif event_type == "model_saved":
            self.complete_previous_training_steps("modelo_salvo")
            self.set_training_step("treinar", "Concluido")
            self.set_training_step("modelo_salvo", "Concluido")
            self.training_saved_model_label.setText(f"Modelo salvo em: {event['path']}")
            self.training_status_label.setText("Modelo salvo")
            self.training_detail_label.setText("Detalhes: modelo salvo; aguardando encerramento do processo")
            self.training_last_message_label.setText("Atualizacao: modelo salvo com sucesso")
        elif event_type == "detail":
            self.training_detail_label.setText(f"Detalhes: {event['text']}")
            self.training_last_message_label.setText("Atualizacao: informacao do treino recebida")
        elif event_type == "internal_progress":
            self.training_detail_label.setText("Detalhes: etapa interna do Cellpose concluida")
            self.training_last_message_label.setText("Atualizacao: Cellpose concluiu uma subetapa interna")
        elif event_type == "error":
            self.training_detail_label.setText(event["text"])
            self.training_last_message_label.setText("Atualizacao: erro detectado durante o treino")

    def update_training_epoch(self, event):
        epoch = event["epoch"]
        total_epochs = self.train_epochs.value()
        visible_epoch = min(epoch, total_epochs)
        train_loss = self.parse_optional_float(event["train_loss"])
        val_loss = self.parse_optional_float(event["val_loss"])
        self.training_epoch_progress.setValue(visible_epoch)
        self.training_epoch_label.setText(f"Epocas: {visible_epoch}/{total_epochs}")
        self.training_train_loss_label.setText(event["train_loss"])
        self.training_val_loss_label.setText(event["val_loss"])
        self.training_lr_label.setText(event["lr"])
        self.training_internal_time_label.setText(f"{event['cellpose_time']}s")
        self.complete_previous_training_steps("treinar")
        self.set_training_step("treinar", "Em andamento")
        self.training_status_label.setText(f"Treinando rede: epoca {visible_epoch}/{total_epochs}")
        self.training_detail_label.setText(
            f"Detalhes: epoca {visible_epoch} concluida; loss treino {event['train_loss']} e validacao {event['val_loss']}"
        )
        self.training_last_message_label.setText("Atualizacao: metricas da epoca atualizadas")
        self.loss_plot.add_point(event["plot_epoch"], train_loss, val_loss)

    def parse_optional_float(self, value):
        try:
            return float(value)
        except ValueError:
            return None

    def update_training_stage(self, event):
        key = event["key"]
        self.complete_previous_training_steps(key)
        if key == "concluido":
            self.set_training_step("modelo_salvo", "Concluido")
            self.set_training_step("concluido", "Concluido")
            self.training_status_label.setText("Treinamento finalizado")
            self.training_detail_label.setText("Detalhes: finalizando arquivos do treino")
        else:
            self.set_training_step(key, "Em andamento")
            self.training_status_label.setText(event["title"])
            self.training_detail_label.setText(f"Detalhes: {event['title'].lower()}")
        self.training_last_message_label.setText(f"Atualizacao: {event['title'].lower()}")

    def friendly_error_message(self, message=None):
        text = message or self.current_process_error
        lowered = text.lower()
        if "gpu obrigatoria" in lowered or "cuda" in lowered and "not detect" in lowered:
            return "Detalhes: GPU nao detectada ou indisponivel para o treino"
        if "nenhuma imagem de treino valida" in lowered:
            return "Detalhes: nenhuma imagem valida de treino foi encontrada"
        if "out of memory" in lowered:
            return "Detalhes: memoria da GPU insuficiente para este treino"
        return "Detalhes: falha durante o treinamento; veja o log bruto para detalhes"

    def refresh_all(self):
        self.config = load_config()
        ensure_project_structure(active_project_dir(self.config))
        self.refresh_project_selector()
        self.refresh_project()
        self.refresh_dataset_import()
        self.refresh_project_models_table()
        self.refresh_prediction()
        self.refresh_analysis_images()
        self.refresh_analysis_metrics()
        self.refresh_measurement_tables()

    def refresh_project_selector(self):
        if not hasattr(self, "project_combo"):
            return
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = list_projects(self.config)
        self.project_combo.addItems(projects)
        index = self.project_combo.findText(self.config["active_project"])
        if index >= 0:
            self.project_combo.setCurrentIndex(index)
        self.project_combo.blockSignals(False)

    def refresh_project(self):
        project_dir = active_project_dir(self.config)
        input_dir = conversion_input_dir(self.config)
        conversion_images = sum(
            1
            for ext in IMAGE_EXTENSIONS
            for path in input_dir.glob(f"*{ext}")
            if not path.stem.endswith("_masks") and not path.stem.endswith("_pred_mask")
        )
        conversion_masks = count_files(input_dir, "*_seg.npy") + count_files(input_dir, "*_masks.tif")
        train_images = count_files(project_dir / "data" / "train" / "images", "*.tif")
        train_masks = count_files(project_dir / "data" / "train" / "masks", "*_masks.tif")
        val_images = count_files(project_dir / "data" / "val" / "images", "*.tif")
        test_images = count_files(project_path(self.config["test_images_dir"], self.config), "*.tif")
        predictions = count_files(predictions_dir(self.config), "*_pred_masks.tif")

        self.model_name_value.setText(self.config["active_model"] or "Nenhum modelo selecionado")

        next_label, next_detail, next_button, next_callback = self.project_next_step(
            conversion_images,
            conversion_masks,
            train_images,
            train_masks,
            val_images,
            test_images,
            predictions,
        )
        self.next_step_label.setText(next_label)
        self.next_step_detail_label.setText(next_detail)
        self.next_step_button.setText(next_button)
        try:
            self.next_step_button.clicked.disconnect()
        except TypeError:
            pass
        self.next_step_button.clicked.connect(next_callback)

        self.refresh_project_models_table()

    def project_next_step(
        self,
        conversion_images,
        conversion_masks,
        train_images,
        train_masks,
        val_images,
        test_images,
        predictions,
    ):
        if conversion_images == 0 and train_images == 0 and val_images == 0 and test_images == 0:
            return (
                "Importe imagens para comecar.",
                "A pasta de entrada ainda nao tem imagens para preparar.",
                "Ir para Dados",
                lambda: self.set_page(1),
            )
        if conversion_images > conversion_masks:
            missing = conversion_images - conversion_masks
            return (
                "Revise as mascaras pendentes.",
                f"{missing} imagem(ns) na entrada ainda nao tem mascara.",
                "Ir para Dados",
                lambda: self.set_page(1),
            )
        if train_images == 0 or train_masks == 0 or val_images == 0 or test_images == 0:
            return (
                "Prepare o dataset de treino.",
                f"Treino: {train_images} imagens / {train_masks} mascaras. Validacao: {val_images}. Teste: {test_images}.",
                "Preparar dataset",
                self.run_prepare_dataset,
            )
        if not self.config.get("active_model"):
            return (
                "Treine ou selecione um modelo.",
                "O dataset ja tem dados, mas nenhum modelo ativo foi selecionado.",
                "Ir para Treino",
                lambda: self.set_page(2),
            )
        if predictions == 0:
            return (
                "Gere predicoes com o modelo ativo.",
                f"Modelo ativo: {self.config['active_model']}. Imagens de teste: {test_images}.",
                "Ir para Resultados",
                lambda: self.set_page(3),
            )
        return (
            "Veja os resultados.",
            f"Ha {predictions} predicao(oes) disponiveis para analisar.",
            "Ir para Resultados",
            lambda: self.set_page(3),
        )

    def refresh_dataset_import(self):
        if not hasattr(self, "dataset_pairs_table"):
            return

        input_dir = conversion_input_dir(self.config)
        input_dir.mkdir(parents=True, exist_ok=True)
        if hasattr(self, "conversion_input_label"):
            self.conversion_input_label.setText(str(input_dir))

        plan = self.load_dataset_plan()
        all_rows = self.scan_conversion_input()
        rows = all_rows
        image_count = len(all_rows)
        valid_count = sum(1 for row in all_rows if row["status"] == "OK")
        missing_count = image_count - valid_count
        seg_count = len(list(input_dir.glob("*_seg.npy")))
        tif_mask_count = len(list(input_dir.glob("*_masks.tif"))) + len(list(input_dir.glob("*_masks.tiff")))
        selected_count = sum(
            1
            for row in rows
            if row["status"] == "OK" and plan.get(row["image"], {}).get("include", True)
        )

        self.dataset_validation_summary.setText(
            f"Imagens: {image_count}\n"
            f"Mascaras: {seg_count + tif_mask_count}\n"
            f"Pares validos: {valid_count}\n"
            f"Selecionadas: {selected_count}\n"
            f"Sem mascara: {missing_count}"
        )

        self.dataset_pairs_table.blockSignals(True)
        self.dataset_pairs_table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            saved = plan.get(row["image"], {})
            include = row["status"] == "OK" and saved.get("include", True)
            group = saved.get("group", "auto")

            include_item = QTableWidgetItem()
            include_item.setFlags(include_item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            if row["status"] != "OK":
                include_item.setFlags(include_item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            include_item.setCheckState(Qt.CheckState.Checked if include else Qt.CheckState.Unchecked)
            include_item.setData(Qt.ItemDataRole.UserRole, row)
            self.dataset_pairs_table.setItem(row_index, 0, include_item)

            group_combo = QComboBox()
            group_options = [
                ("auto", "Auto"),
                ("train", "Treino"),
                ("val", "Validacao"),
                ("test", "Teste"),
            ]
            for key, label in group_options:
                group_combo.addItem(label, key)
            group_index = group_combo.findData(group)
            group_combo.setCurrentIndex(group_index if group_index >= 0 else 0)
            group_combo.setEnabled(row["status"] == "OK")
            group_combo.currentIndexChanged.connect(lambda _index: self.save_dataset_plan_from_table())
            self.dataset_pairs_table.setCellWidget(row_index, 1, group_combo)

            values = [row["image"], row["segmentation"], row["status"]]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.dataset_pairs_table.setItem(row_index, col + 2, item)
            self.dataset_pairs_table.setRowHeight(row_index, 30)
        self.dataset_pairs_table.blockSignals(False)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.dataset_pairs_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        if rows:
            self.dataset_pairs_table.selectRow(0)
        else:
            self.dataset_preview_label.setText("Nenhuma imagem encontrada.")
            self.dataset_preview_label.setPixmap(QPixmap())

    def scan_conversion_input(self):
        input_dir = conversion_input_dir(self.config)
        image_files = []
        for ext in IMAGE_EXTENSIONS:
            image_files.extend(input_dir.glob(f"*{ext}"))

        image_files = sorted(
            path
            for path in image_files
            if not path.stem.endswith("_masks") and not path.stem.endswith("_pred_mask")
        )

        rows = []
        for image_path in image_files:
            seg_path = image_path.with_name(f"{image_path.stem}_seg.npy")
            tif_mask_path = image_path.with_name(f"{image_path.stem}_masks.tif")
            tiff_mask_path = image_path.with_name(f"{image_path.stem}_masks.tiff")
            mask_path = tif_mask_path if tif_mask_path.exists() else tiff_mask_path
            has_mask = seg_path.exists() or mask_path.exists()
            rows.append(
                {
                    "image": image_path.name,
                    "segmentation": seg_path.name if seg_path.exists() else (mask_path.name if mask_path.exists() else "ausente"),
                    "status": "OK" if has_mask else "Sem mascara",
                    "image_path": str(image_path),
                    "seg_path": str(seg_path),
                    "tif_mask_path": str(mask_path),
                }
            )
        return rows

    def load_dataset_plan(self):
        return load_plan(dataset_plan_path(self.config))

    def save_dataset_plan_from_table(self):
        if not hasattr(self, "dataset_pairs_table") or self.dataset_pairs_table.signalsBlocked():
            return
        entries = self.dataset_plan_entries_from_table()
        save_plan(dataset_plan_path(self.config), entries)
        self.update_dataset_selection_summary()

    def update_dataset_selection_summary(self):
        if not hasattr(self, "dataset_validation_summary"):
            return
        summary = summarize_table_entries(self.dataset_plan_entries_from_table())
        groups = summary["groups"]
        self.dataset_validation_summary.setText(
            f"Imagens: {summary['total']}\n"
            f"Pares validos: {summary['valid']}\n"
            f"Selecionadas: {summary['selected']}\n"
            f"Treino/Val/Teste/Auto: {groups['train']}/{groups['val']}/{groups['test']}/{groups['auto']}\n"
            f"Sem mascara: {summary['problems']}"
        )

    def dataset_plan_entries_from_table(self):
        entries = []
        for row in range(self.dataset_pairs_table.rowCount()):
            include_item = self.dataset_pairs_table.item(row, 0)
            status_item = self.dataset_pairs_table.item(row, 4)
            group_combo = self.dataset_pairs_table.cellWidget(row, 1)
            image_item = self.dataset_pairs_table.item(row, 2)
            if include_item is None or status_item is None or image_item is None:
                continue
            entries.append(
                {
                    "image": image_item.text(),
                    "include": include_item.checkState() == Qt.CheckState.Checked,
                    "group": group_combo.currentData() if group_combo else "auto",
                    "status": status_item.text(),
                }
            )
        return entries

    def auto_split_dataset_table(self):
        assignments = auto_split_indices(self.dataset_plan_entries_from_table())

        self.dataset_pairs_table.blockSignals(True)
        for row, group in assignments.items():
            combo = self.dataset_pairs_table.cellWidget(row, 1)
            if combo:
                index = combo.findData(group)
                if index >= 0:
                    combo.setCurrentIndex(index)
        self.dataset_pairs_table.blockSignals(False)
        self.save_dataset_plan_from_table()

    def show_selected_dataset_pair(self):
        row = self.dataset_pairs_table.currentRow()
        if row < 0:
            return
        item = self.dataset_pairs_table.item(row, 2)
        if item is None:
            return
        row_data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.show_dataset_preview(row_data)
        self.select_dataset_annotation_row(row_data)

    def show_dataset_preview(self, row_data):
        image_path = Path(row_data.get("image_path", ""))
        seg_path = Path(row_data.get("seg_path", ""))
        tif_mask_path = Path(row_data.get("tif_mask_path", ""))
        if not image_path.exists():
            self.dataset_preview_label.setText("Imagem nao encontrada.")
            self.dataset_preview_label.setPixmap(QPixmap())
            return
        try:
            image = Image.open(image_path).convert("RGB")
            mask = None
            if seg_path.exists():
                mask = np.load(seg_path, allow_pickle=True).item().get("masks")
            elif tif_mask_path.exists():
                mask = np.array(Image.open(tif_mask_path))
            if mask is not None and np.max(mask) > 0:
                mask = np.asarray(mask)
                mask_image = Image.fromarray((mask > 0).astype(np.uint8) * 120).resize(image.size)
                color = Image.new("RGBA", image.size, (22, 107, 92, 0))
                color.putalpha(mask_image)
                image = Image.alpha_composite(image.convert("RGBA"), color).convert("RGB")
            self.set_label_pixmap(self.dataset_preview_label, image)
            self.dataset_preview_info.setText(
                f"{image_path.name}\n{row_data.get('status', '')}\nDuplo clique para editar a mascara."
            )
        except Exception as exc:
            self.dataset_preview_label.setText(f"Nao foi possivel carregar preview:\n{exc}")
            self.dataset_preview_label.setPixmap(QPixmap())

    def select_dataset_annotation_row(self, row_data):
        if not hasattr(self, "annotation_page"):
            return
        image_path = Path(row_data.get("image_path", ""))
        if not image_path.exists():
            return
        seg_path = Path(row_data.get("seg_path", ""))
        tif_mask_path = Path(row_data.get("tif_mask_path", ""))
        entry = {
            "path": image_path,
            "seg_path": seg_path,
            "tif_mask_path": tif_mask_path,
            "has_mask": seg_path.exists() or tif_mask_path.exists(),
            "label": "[Com mascara]" if seg_path.exists() or tif_mask_path.exists() else "[Sem mascara]",
        }
        self.annotation_page.show_image(entry)

    def open_selected_dataset_editor(self):
        row = self.dataset_pairs_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Editar mascara", "Selecione uma imagem na tabela.")
            return
        item = self.dataset_pairs_table.item(row, 2)
        if item is None:
            return
        row_data = item.data(Qt.ItemDataRole.UserRole) or {}
        self.select_dataset_annotation_row(row_data)
        self.annotation_page.open_editor()

    def import_dataset_folder(self):
        source = QFileDialog.getExistingDirectory(self, "Escolher pasta com imagens e _seg.npy", str(PROJECT_DIR))
        if not source:
            return

        source_dir = Path(source)
        target_dir = conversion_input_dir(self.config)
        target_dir.mkdir(parents=True, exist_ok=True)

        copied = 0
        converted = 0
        skipped = 0
        image_candidates = {}

        for src in sorted(source_dir.iterdir()):
            if not src.is_file():
                continue

            if src.name.endswith("_seg.npy"):
                dst = target_dir / src.name
                if dst.exists():
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
                continue

            if src.stem.endswith("_masks") or src.stem.endswith("_pred_mask"):
                continue

            if src.suffix.lower() not in IMAGE_EXTENSIONS:
                continue

            current = image_candidates.get(src.stem)
            if current is None:
                image_candidates[src.stem] = src
                continue

            current_is_tif = current.suffix.lower() in {".tif", ".tiff"}
            src_is_tif = src.suffix.lower() in {".tif", ".tiff"}
            if src_is_tif and not current_is_tif:
                image_candidates[src.stem] = src

        for src in sorted(image_candidates.values()):
            if src.suffix.lower() in {".tif", ".tiff"}:
                dst = target_dir / src.name
                if dst.exists():
                    skipped += 1
                    continue
                shutil.copy2(src, dst)
                copied += 1
                continue

            dst = target_dir / f"{src.stem}.tif"
            if dst.exists():
                skipped += 1
                continue

            try:
                with Image.open(src) as image:
                    if image.mode == "P":
                        image = image.convert("RGB")
                    tiff.imwrite(dst, np.asarray(image))
                converted += 1
            except Exception:
                skipped += 1

        self.append_log(
            f"\n>>> Importar imagens e _seg.npy\n"
            f"Origem: {source_dir}\n"
            f"Destino: {target_dir}\n"
            f"Copiados: {copied}\n"
            f"Convertidos para TIFF: {converted}\n"
            f"Pulados por ja existirem: {skipped}\n"
        )
        self.convert_dataset_images_to_tif(target_dir)
        self.refresh_dataset_import()
        self.refresh_project()

    def convert_dataset_images_to_tif(self, folder=None):
        input_dir = Path(folder) if folder else conversion_input_dir(self.config)
        input_dir.mkdir(parents=True, exist_ok=True)

        converted = 0
        skipped = 0
        failed = 0

        for image_path in sorted(input_dir.iterdir()):
            if not image_path.is_file():
                continue
            if image_path.name.endswith("_seg.npy") or image_path.stem.endswith("_masks") or image_path.stem.endswith("_pred_mask"):
                continue

            suffix = image_path.suffix.lower()
            if suffix not in {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif", ".tif", ".tiff"}:
                continue

            if suffix in {".tif", ".tiff"}:
                skipped += 1
                continue

            tif_path = image_path.with_suffix(".tif")
            if tif_path.exists():
                if image_path.exists():
                    image_path.unlink()
                skipped += 1
                continue

            try:
                with Image.open(image_path) as image:
                    if image.mode == "P":
                        image = image.convert("RGB")
                    tiff.imwrite(tif_path, np.asarray(image))
                image_path.unlink()
                converted += 1
            except Exception:
                failed += 1

        self.append_log(
            f"\n>>> Converter para TIFF\n"
            f"Pasta: {input_dir}\n"
            f"Convertidos: {converted}\n"
            f"Ja eram TIFF: {skipped}\n"
            f"Falhas: {failed}\n"
        )

    def refresh_annotation_images(self):
        if hasattr(self, "annotation_page"):
            self.annotation_page.refresh_images()

    def current_annotation_image_path(self):
        return self.annotation_page.current_image_path()

    def set_annotation_view_mode(self, mode):
        self.annotation_page.set_view_mode(mode)

    def refresh_project_models_table(self):
        if not hasattr(self, "project_models_table"):
            return

        models_dir = project_models_dir(self.config)
        models_dir.mkdir(parents=True, exist_ok=True)
        models = sorted(path for path in models_dir.iterdir() if path.is_file())
        self.project_models_table.setRowCount(len(models))
        active_row = None
        for row, model_path in enumerate(models):
            values = [
                model_path.name,
                format_size(model_path.stat().st_size),
                time.strftime("%d/%m/%Y %H:%M", time.localtime(model_path.stat().st_mtime)),
                "sim" if metrics_csv_path(self.config, model_path.name).exists() else "nao",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if model_path.name == self.config["active_model"]:
                    item.setBackground(QColor("#dcece6"))
                    item.setForeground(QColor("#1f2933"))
                self.project_models_table.setItem(row, col, item)
            if model_path.name == self.config["active_model"]:
                active_row = row
            self.project_models_table.setRowHeight(row, 30)

        self.project_models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column in range(1, 4):
            self.project_models_table.horizontalHeader().setSectionResizeMode(column, QHeaderView.ResizeMode.ResizeToContents)
        if active_row is not None:
            self.project_models_table.selectRow(active_row)
        else:
            self.project_models_table.clearSelection()

    def refresh_prediction(self):
        self.predict_model_label.setText(self.config["active_model"] or "Nenhum modelo selecionado")
        self.pred_input.setText(self.config["test_images_dir"])
        self.pred_output.setText(self.config["predictions_dir"])
        self.pred_padding.setValue(int(self.config["padding_pixels"]))
        self.pred_diameter.setText(str(self.config["diameter"]))
        self.pred_cellprob.setText(str(self.config["cellprob_threshold"]))
        self.pred_flow.setText(str(self.config["flow_threshold"]))
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.pred_output.setText(self.config["predictions_dir"])
        if not self.config.get("active_model"):
            self.train_model_name.setText(f"cpsam_{self.config['active_project']}_v1")
        self.refresh_prediction_model_selector()
        if hasattr(self, "annotation_page"):
            self.annotation_page.sync_from_config(self.config)

    def refresh_prediction_model_selector(self):
        if not hasattr(self, "prediction_model_combo"):
            return

        models = sorted(path.name for path in project_models_dir(self.config).glob("*") if path.is_file())
        self.prediction_model_combo.blockSignals(True)
        self.prediction_model_combo.clear()
        self.prediction_model_combo.addItem("Selecione um modelo", "")
        for model_name in models:
            self.prediction_model_combo.addItem(model_name, model_name)

        active_model = self.config.get("active_model") or ""
        index = self.prediction_model_combo.findData(active_model)
        self.prediction_model_combo.setCurrentIndex(index if index >= 0 else 0)
        self.prediction_model_combo.blockSignals(False)

    def on_prediction_model_changed(self, _index=None):
        if not hasattr(self, "prediction_model_combo"):
            return
        model_name = self.prediction_model_combo.currentData() or ""
        if not model_name or model_name == self.config.get("active_model"):
            return
        self.set_active_model(model_name)

    def set_active_model(self, model_name):
        if not model_name or model_name == self.config.get("active_model"):
            return
        self.config["active_model"] = model_name
        self.config["predictions_dir"] = relative_to_project(predictions_dir(self.config), self.config)
        self.config["overlays_dir"] = relative_to_project(overlays_dir(self.config), self.config)
        self.analysis_cache.clear()
        save_config(self.config)
        self.refresh_all()

    def refresh_analysis_images(self):
        if not hasattr(self, "image_list"):
            return
        selected = self.image_list.currentItem().text() if self.image_list.currentItem() else None
        self.image_list.clear()
        images_dir = project_path(self.config["test_images_dir"], self.config)
        if images_dir.exists():
            for path in sorted(images_dir.glob("*.tif")):
                self.image_list.addItem(path.stem)
        if selected:
            items = self.image_list.findItems(selected, Qt.MatchFlag.MatchExactly)
            if items:
                self.image_list.setCurrentItem(items[0])
            elif self.image_list.count() > 0:
                self.image_list.setCurrentRow(0)
            else:
                self.preview_label.setText("Nenhuma imagem encontrada.")
                self.preview_label.setPixmap(QPixmap())
        elif self.image_list.count() > 0:
            self.image_list.setCurrentRow(0)
        else:
            self.preview_label.setText("Nenhuma imagem encontrada.")
            self.preview_label.setPixmap(QPixmap())

    def refresh_analysis_metrics(self):
        self.metrics_by_image = {
            row["image"]: row for row in read_metrics(metrics_csv_path(self.config))
        }
        current = self.image_list.currentItem() if hasattr(self, "image_list") else None
        if current:
            self.update_metric_panel(current.text())
        else:
            self.update_metric_panel(None)

    def refresh_measurement_tables(self):
        if not hasattr(self, "cell_counts_table"):
            return
        counts_path = cell_counts_csv_path(self.config)
        measurements_path = cell_measurements_csv_path(self.config)
        counts_rows = self.load_semicolon_csv(counts_path)
        measurement_rows = self.load_semicolon_csv(measurements_path)
        self.populate_csv_table(self.cell_counts_table, counts_rows)
        self.populate_csv_table(self.cell_measurements_table, measurement_rows)

        if counts_path.exists() and measurements_path.exists():
            self.measurements_status_label.setText(
                f"Contagens: {max(len(counts_rows) - 1, 0)} imagens | "
                f"Medidas: {max(len(measurement_rows) - 1, 0)} objetos"
            )
        else:
            missing = []
            if not counts_path.exists():
                missing.append("cell_counts.csv")
            if not measurements_path.exists():
                missing.append("cell_measurements.csv")
            self.measurements_status_label.setText(
                "Arquivos ainda nao encontrados: " + ", ".join(missing)
            )

    def load_semicolon_csv(self, path):
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            return list(csv.reader(file, delimiter=";"))

    def populate_csv_table(self, table, rows):
        table.setSortingEnabled(False)
        table.clear()
        if not rows:
            table.setRowCount(0)
            table.setColumnCount(0)
            table.setSortingEnabled(True)
            return
        headers = rows[0]
        body = rows[1:]
        table.setColumnCount(len(headers))
        table.setHorizontalHeaderLabels(headers)
        table.setRowCount(len(body))
        for row_index, row in enumerate(body):
            for column_index, value in enumerate(row):
                table.setItem(row_index, column_index, QTableWidgetItem(value))
        table.resizeColumnsToContents()
        table.horizontalHeader().setStretchLastSection(True)
        table.setSortingEnabled(True)

    def select_project_model(self):
        row = self.project_models_table.currentRow()
        if row < 0:
            QMessageBox.information(self, "Modelo", "Selecione um modelo na tabela.")
            return
        self.set_active_model(self.project_models_table.item(row, 0).text())

    def show_analysis_image(self, image_stem):
        if not image_stem:
            return
        self.update_metric_panel(image_stem)
        if self.current_view_mode in {"overlay_50pct", "overlay_inteiros", "overlay_diametro"}:
            image = self.render_measurement_overlay(image_stem, self.current_view_mode)
            if image is None:
                self.preview_label.setText("Imagem ou predicao nao encontrada para este modo.")
                self.preview_label.setPixmap(QPixmap())
                return
            self.set_label_pixmap(self.preview_label, image)
            return
        image_path = self.analysis_image_path(image_stem, self.current_view_mode)
        if image_path is None or not image_path.exists():
            self.preview_label.setText("Arquivo nao encontrado para este modo.")
            self.preview_label.setPixmap(QPixmap())
            return
        self.show_image_file(image_path)

    def analysis_image_path(self, stem, mode):
        if mode == "original":
            return project_path(self.config["test_images_dir"], self.config) / f"{stem}.tif"
        if mode == "overlay":
            return overlays_dir(self.config) / f"{stem}_overlay_pred.tif"
        return None

    def render_measurement_overlay(self, stem, mode):
        image_path = project_path(self.config["test_images_dir"], self.config) / f"{stem}.tif"
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if not image_path.exists() or not pred_path.exists():
            return None

        base_image = self.load_image_as_rgb(image_path)
        mask = self.load_mask_array(pred_path)
        if mask is None:
            return None

        if mode == "overlay_50pct":
            filtered = filtrar_celulas_borda_proporcional(
                mask,
                area_minima=0,
                max_borda_diametro_ratio=1.5,
                borda_expandida=8,
            )
            return self.overlay_mask_on_image(base_image, filtered, color=(230, 92, 58), alpha=105)

        filtered = build_mask_inteiros(mask)
        image = self.overlay_mask_on_image(base_image, filtered, color=(22, 107, 92), alpha=105)

        if mode == "overlay_diametro":
            image = self.draw_minor_axes(image, filtered)

        return image

    def load_image_as_rgb(self, path):
        cache_key = self.cache_key("image", path)
        if cache_key not in self.analysis_cache:
            image = Image.open(path)
            array = np.array(image)
            if array.ndim == 2:
                array = normalize_array(array)
                image = Image.fromarray(array).convert("RGB")
            else:
                image = image.convert("RGB")
            self.analysis_cache[cache_key] = image
        return self.analysis_cache[cache_key].copy()

    def load_mask_array(self, path):
        cache_key = self.cache_key("mask", path)
        if cache_key not in self.analysis_cache:
            mask = np.asarray(tiff.imread(path)).astype(np.uint16)
            if mask.ndim > 2:
                mask = np.squeeze(mask)
            if mask.ndim != 2:
                return None
            self.analysis_cache[cache_key] = mask
        return self.analysis_cache[cache_key]

    def cache_key(self, kind, path):
        path = Path(path)
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0
        return kind, str(path), mtime

    def overlay_mask_on_image(self, image, mask, color, alpha):
        overlay_alpha = Image.fromarray((np.asarray(mask) > 0).astype(np.uint8) * alpha).resize(image.size)
        color_image = Image.new("RGBA", image.size, (*color, 0))
        color_image.putalpha(overlay_alpha)
        return Image.alpha_composite(image.convert("RGBA"), color_image).convert("RGB")

    def draw_minor_axes(self, image, mask):
        draw = ImageDraw.Draw(image)
        axes = compute_ellipse_minor_axis_by_label(mask)
        for ellipse in axes.values():
            y1, x1 = ellipse.axis_start_rc
            y2, x2 = ellipse.axis_end_rc
            cy, cx = ellipse.centroid_rc
            draw.line((x1, y1, x2, y2), fill=(255, 235, 59), width=3)
            draw.ellipse((cx - 3, cy - 3, cx + 3, cy + 3), fill=(255, 235, 59))
        return image

    def show_image_file(self, path):
        image = self.load_image_as_rgb(path)
        self.set_label_pixmap(self.preview_label, image)

    def set_label_pixmap(self, label, image):
        image = image.convert("RGB")
        width, height = image.size
        qimage = QImage(image.tobytes(), width, height, width * 3, QImage.Format.Format_RGB888).copy()
        source_pixmap = QPixmap.fromImage(qimage)
        pixmap = source_pixmap.scaled(
            label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        label._display_scale = pixmap.width() / width
        label._display_offset_x = (label.width() - pixmap.width()) / 2
        label._display_offset_y = (label.height() - pixmap.height()) / 2
        label.setPixmap(pixmap)

    def update_metric_panel(self, image_stem):
        row = getattr(self, "metrics_by_image", {}).get(image_stem) if image_stem else None
        values = {
            "Dice": "-",
            "IoU": "-",
            "Precision": "-",
            "Recall": "-",
            "GT objects": "-",
            "Pred objects": "-",
        }
        if row:
            values.update(
                {
                    "Dice": f"{float(row['dice']):.4f}",
                    "IoU": f"{float(row['iou']):.4f}",
                    "Precision": f"{float(row['precision']):.4f}",
                    "Recall": f"{float(row['recall']):.4f}",
                    "GT objects": row["gt_objects"],
                    "Pred objects": row["pred_objects"],
                }
            )
        for key, value in values.items():
            self.analysis_metric_labels[key].setText(value)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        current = self.image_list.currentItem() if hasattr(self, "image_list") else None
        if current:
            self.show_analysis_image(current.text())

    def choose_folder(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "Escolher pasta", str(PROJECT_DIR))
        if folder:
            try:
                line_edit.setText(str(Path(folder).relative_to(PROJECT_DIR)))
            except ValueError:
                line_edit.setText(folder)

    def parse_float(self, value, default):
        try:
            return float(value.strip().replace(",", "."))
        except ValueError:
            return default

    def open_folder(self, folder):
        Path(folder).mkdir(parents=True, exist_ok=True)
        os.startfile(folder)

    def open_file(self, file_path):
        if not file_path.exists():
            QMessageBox.information(self, "Arquivo nao encontrado", str(file_path))
            return
        os.startfile(file_path)

    def show_about(self):
        QMessageBox.information(
            self,
            "Sobre",
            "Cellpose - Vasos de Eucalipto\n\n"
            "Interface local para preparar datasets, treinar modelos, gerar predicoes, "
            "criar overlays e avaliar metricas por projeto.",
        )

    def apply_style(self):
        self.setStyleSheet(APP_STYLE)


def main():
    if len(sys.argv) > 2 and sys.argv[1] == "--run-script":
        script_path = sys.argv[2]
        sys.argv = [script_path, *sys.argv[3:]]
        runpy.run_path(script_path, run_name="__main__")
        return

    app = QApplication(sys.argv)
    window = CellposeWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
