from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
    QHeaderView,
)

from ui.loss_plot import LossPlotWidget


class TrainingPageBuilderMixin:
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

    def open_training_dialog(self):
        if self.training_dialog is None:
            self.training_dialog = QDialog(self)
            self.training_dialog.setWindowTitle("Treinar modelo")
            self.training_dialog.resize(1100, 760)
            self.build_train_page(self.training_dialog)
            if not self.config.get("active_model"):
                self.train_model_name.setText(f"cpsam_{self.config['active_project']}_v1")
        self.training_dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.training_dialog.show()
        self.training_dialog.raise_()
        self.training_dialog.activateWindow()
