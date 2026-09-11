from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from ui.loss_plot import LossPlotWidget


class TrainingPageBuilderMixin:
    def open_training_page(self):
        self.set_page(self.training_page_index)
        self._go_to_training_wizard_page(0)

    def build_training_page(self, page):
        self.training_page_index = self.stack.indexOf(page)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(0)

        self._training_wizard_stack = QStackedWidget()
        page_layout.addWidget(self._training_wizard_stack, 1)

        # Passo 1: Modelos treinados e mascaras
        masks_page = QWidget()
        masks_layout = QVBoxLayout(masks_page)
        masks_layout.setContentsMargins(14, 14, 14, 14)
        masks_layout.addWidget(self._build_training_models_panel())
        self._training_masks_body = QHBoxLayout()
        masks_layout.addLayout(self._training_masks_body, 1)
        self._training_wizard_stack.addWidget(masks_page)

        # Passo 2: Separacao dos dados (treino/validacao/teste)
        split_page = QWidget()
        split_layout = QVBoxLayout(split_page)
        split_layout.setContentsMargins(14, 14, 14, 14)
        self._training_split_body = QHBoxLayout()
        split_layout.addLayout(self._training_split_body, 1)
        self._training_wizard_stack.addWidget(split_page)

        # Passo 3: Parametros de treino
        params_page = QWidget()
        self._build_train_params_page(params_page)
        self._training_wizard_stack.addWidget(params_page)

        # Passo 4: Progresso
        progress_page = QWidget()
        self._build_train_progress_page(progress_page)
        self._training_wizard_stack.addWidget(progress_page)

        # Barra de navegacao
        nav_bar = QWidget()
        nav_bar.setObjectName("wizardNav")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(16, 10, 16, 10)
        nav_layout.setSpacing(8)

        self._wizard_exit_button = QPushButton("← Resultados")
        self._wizard_exit_button.clicked.connect(lambda: self.set_page(0))

        self._wizard_back_button = QPushButton("← Voltar")
        self._wizard_back_button.clicked.connect(self._wizard_go_back)
        self._wizard_next_button = QPushButton("Próximo →")
        self._wizard_next_button.clicked.connect(self._wizard_go_next)
        self._wizard_train_button = QPushButton("Treinar ▶")
        self._wizard_train_button.setObjectName("primary")
        self._wizard_train_button.clicked.connect(self.run_training)

        self._wizard_loss_history_button = QPushButton("Grafico de perda")
        self._wizard_loss_history_button.clicked.connect(lambda: self._go_to_training_wizard_page(3))

        nav_layout.addWidget(self._wizard_exit_button)
        nav_layout.addWidget(self._wizard_back_button)
        nav_layout.addWidget(self._wizard_loss_history_button)
        nav_layout.addStretch()
        nav_layout.addWidget(self._wizard_next_button)
        nav_layout.addWidget(self._wizard_train_button)
        page_layout.addWidget(nav_bar)
        self._go_to_training_wizard_page(0)

    def _go_to_training_wizard_page(self, index):
        self._place_dataset_table_panel(index == 1)
        self._training_wizard_stack.setCurrentIndex(index)
        self._wizard_back_button.setVisible(index in (1, 2, 3))
        self._wizard_next_button.setVisible(index in (0, 1))
        self._wizard_train_button.setVisible(index == 2)

    def _place_dataset_table_panel(self, in_split_page):
        for body in (self._training_masks_body, self._training_split_body):
            body.removeWidget(self._dataset_table_panel)
            body.removeWidget(self._dataset_preview_panel)
        target_body = self._training_split_body if in_split_page else self._training_masks_body
        target_body.addWidget(self._dataset_table_panel, 1)
        target_body.addWidget(self._dataset_preview_panel, 2)
        self.set_dataset_table_mode(split=in_split_page)

    def _wizard_go_back(self):
        current = self._training_wizard_stack.currentIndex()
        if current > 0:
            self._go_to_training_wizard_page(current - 1)

    def _wizard_go_next(self):
        current = self._training_wizard_stack.currentIndex()
        if current < self._training_wizard_stack.count() - 1:
            self._go_to_training_wizard_page(current + 1)

    def _build_train_params_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        form_box = self.panel("Novo modelo")
        form_layout = QGridLayout(form_box)
        form_layout.setContentsMargins(10, 8, 10, 10)
        form_layout.setHorizontalSpacing(10)
        form_layout.setVerticalSpacing(6)
        default_model_name = (
            self.config["active_model"] if self.config.get("active_model")
            else f"cpsam_{self.config['active_project']}_v1"
        )
        self.train_model_name = QLineEdit(default_model_name)
        self.train_base_model = QLineEdit("cpsam")
        self.train_epochs = QSpinBox()
        self.train_epochs.setRange(1, 10000)
        self.train_epochs.setValue(100)
        self.train_learning_rate = QLineEdit("1e-5")
        self.train_weight_decay = QLineEdit("0.1")
        self.train_batch_size = QSpinBox()
        self.train_batch_size.setRange(1, 512)
        self.train_batch_size.setValue(1)
        self.train_epochs.setMinimumWidth(80)
        self.train_batch_size.setMinimumWidth(72)
        for field in [self.train_learning_rate, self.train_weight_decay]:
            field.setMinimumWidth(90)

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
        layout.addWidget(form_box)
        layout.addStretch()

    def _build_train_progress_page(self, page):
        layout = QVBoxLayout(page)
        layout.setSpacing(12)
        layout.setContentsMargins(14, 14, 14, 14)

        top_layout = QHBoxLayout()
        top_layout.setSpacing(12)

        progress_box = self.panel("Status do treino")
        progress_layout = QVBoxLayout(progress_box)
        self.training_status_label = QLabel("Aguardando treino.")
        self.training_status_label.setObjectName("largeText")
        self.training_model_label = QLabel("Modelo: -")
        self.training_dataset_counts_label = QLabel("Imagens: - treino / - validacao")
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
        progress_layout.addWidget(self.training_dataset_counts_label)
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
        loss_toolbar = QHBoxLayout()
        loss_toolbar.addStretch()
        self.loss_plot_load_button = QPushButton("Carregar historico")
        self.loss_plot_load_button.clicked.connect(self.load_loss_history)
        loss_toolbar.addWidget(self.loss_plot_load_button)
        self.loss_plot_export_button = QPushButton("Exportar grafico")
        self.loss_plot_export_button.clicked.connect(self.export_loss_plot)
        loss_toolbar.addWidget(self.loss_plot_export_button)
        loss_layout.addLayout(loss_toolbar)
        self.loss_plot = LossPlotWidget(self.train_epochs.value())
        self.train_epochs.valueChanged.connect(lambda value: self.loss_plot.reset(value))
        loss_layout.addWidget(self.loss_plot, 1)
        layout.addWidget(loss_box, 1)

    def _build_training_models_panel(self):
        box = self.panel("Modelos treinados")
        layout = QVBoxLayout(box)
        layout.setSpacing(6)

        project_row = QHBoxLayout()
        project_row.addWidget(QLabel("Projeto:"))
        self.project_combo = QComboBox()
        self.project_combo.currentTextChanged.connect(self.select_project)
        project_row.addWidget(self.project_combo, 1)
        new_proj_btn = QPushButton("Novo")
        new_proj_btn.clicked.connect(self.create_project)
        del_proj_btn = QPushButton("Deletar")
        del_proj_btn.clicked.connect(self.delete_project)
        project_row.addWidget(new_proj_btn)
        project_row.addWidget(del_proj_btn)
        layout.addLayout(project_row)

        self.project_models_table = QTableWidget(0, 5)
        self.project_models_table.setHorizontalHeaderLabels(["Nome", "Tamanho", "Data", "Avaliado", "Compartilhado"])
        self.project_models_table.verticalHeader().setVisible(False)
        self.project_models_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.project_models_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.project_models_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.project_models_table.setAlternatingRowColors(True)
        self.project_models_table.setShowGrid(False)
        for col in range(5):
            self.project_models_table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        self.project_models_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Interactive)
        self.project_models_table.setColumnWidth(0, 200)
        self.project_models_table.cellDoubleClicked.connect(lambda row, _col: self._use_model_at_row(row))
        layout.addWidget(self.project_models_table)

        actions = QHBoxLayout()
        use_btn = QPushButton("Usar modelo")
        use_btn.clicked.connect(self.select_project_model)
        promote_btn = QPushButton("Promover para compartilhados")
        promote_btn.clicked.connect(self._promote_selected_project_model)
        remove_btn = QPushButton("Remover modelo")
        remove_btn.clicked.connect(self._remove_selected_project_model)
        actions.addWidget(use_btn)
        actions.addWidget(promote_btn)
        actions.addWidget(remove_btn)
        actions.addStretch()
        layout.addLayout(actions)
        return box

    def _use_model_at_row(self, row):
        if not hasattr(self, "project_models_table") or row < 0:
            return
        item = self.project_models_table.item(row, 0)
        if item:
            self.set_active_model(item.text())

    def _promote_selected_project_model(self):
        if not hasattr(self, "project_models_table"):
            return
        row = self.project_models_table.currentRow()
        if row < 0:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Promover modelo", "Selecione um modelo na tabela.")
            return
        model_name = self.project_models_table.item(row, 0).text()
        original = self.config.get("active_model")
        self.config["active_model"] = model_name
        self.promote_active_model()
        self.config["active_model"] = original

    def _remove_selected_project_model(self):
        if not hasattr(self, "project_models_table"):
            return
        row = self.project_models_table.currentRow()
        if row < 0:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(self, "Remover modelo", "Selecione um modelo na tabela.")
            return
        model_name = self.project_models_table.item(row, 0).text()
        original = self.config.get("active_model")
        self.config["active_model"] = model_name
        self.remove_active_model()
        if self.config.get("active_model") != model_name:
            pass  # remove_active_model ja atualizou
        else:
            self.config["active_model"] = original
