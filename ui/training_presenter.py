import shutil
import time

import numpy as np
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
    QTableWidgetItem,
    QVBoxLayout,
)

from services.dataset_plan import load_plan
from services.image_set_service import write_image_set_metadata
from services.paths import (
    dataset_images_dir,
    dataset_plan_path,
    ensure_image_set_structure,
    image_sets_dir,
    list_image_sets,
    project_models_dir,
    DEFAULT_IMAGE_SET,
)
from services.training_log_parser import parse_training_log_line


class TrainingPresenterMixin:
    def load_loss_history(self):
        start_dir = str(project_models_dir(self.config))
        file_name, _filter = QFileDialog.getOpenFileName(
            self,
            "Carregar historico de perda",
            start_dir,
            "Historico de perda (*.csv *.npy);;CSV (*.csv);;Numpy (*.npy);;Todos os arquivos (*)",
        )
        if not file_name:
            return
        if file_name.lower().endswith(".npy"):
            epochs, train_losses, val_losses = self._read_loss_history_npy(file_name)
        else:
            epochs, train_losses, val_losses = self._read_loss_history_csv(file_name)
        if epochs is None:
            QMessageBox.warning(
                self,
                "Carregar historico de perda",
                "Nao foi possivel ler o arquivo de historico selecionado.",
            )
            return
        self.loss_plot.load_history(epochs, train_losses, val_losses)

    def _read_loss_history_csv(self, file_name):
        epochs, train_losses, val_losses = [], [], []
        try:
            with open(file_name, "r", encoding="utf-8") as history_file:
                for line in history_file:
                    line = line.strip()
                    if not line or not line[0].isdigit():
                        continue
                    epoch_text, train_text, val_text = (line.split(",") + ["", ""])[:3]
                    epochs.append(int(epoch_text))
                    train_losses.append(self.parse_optional_float(train_text))
                    val_losses.append(self.parse_optional_float(val_text))
        except (OSError, ValueError):
            return None, None, None
        return epochs, train_losses, val_losses

    def _read_loss_history_npy(self, file_name):
        try:
            losses = np.load(file_name, allow_pickle=True)
            losses = np.asarray(losses, dtype=float).reshape(-1)
        except (OSError, ValueError):
            return None, None, None
        epochs = list(range(len(losses)))
        train_losses = [float(loss) for loss in losses]
        val_losses = [None] * len(losses)
        return epochs, train_losses, val_losses

    def export_loss_plot(self):
        if not self.loss_plot.has_data():
            QMessageBox.information(
                self,
                "Exportar grafico",
                "Nenhum dado de treino disponivel para exportar ainda.",
            )
            return
        model_name = self.train_model_name.text().strip() or "modelo"
        file_name, _filter = QFileDialog.getSaveFileName(
            self,
            "Exportar grafico",
            f"{model_name}_loss.png",
            "Imagem PNG (*.png)",
        )
        if not file_name:
            return
        self.loss_plot.export_to_file(file_name)

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
        self.training_dataset_train_count = None
        self.training_dataset_val_count = None
        self.training_dataset_counts_label.setText("Imagens: - treino / - validacao")
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
        elif event_type == "dataset_count":
            self.update_training_dataset_counts(event)
        elif event_type == "internal_progress":
            self.training_detail_label.setText("Detalhes: etapa interna do Cellpose concluida")
            self.training_last_message_label.setText("Atualizacao: Cellpose concluiu uma subetapa interna")
        elif event_type == "error":
            self.training_detail_label.setText(event["text"])
            self.training_last_message_label.setText("Atualizacao: erro detectado durante o treino")

    def update_training_dataset_counts(self, event):
        if event["kind"] == "train":
            self.training_dataset_train_count = event["count"]
        else:
            self.training_dataset_val_count = event["count"]
        train_text = self.training_dataset_train_count if self.training_dataset_train_count is not None else "-"
        val_text = self.training_dataset_val_count if self.training_dataset_val_count is not None else "-"
        self.training_dataset_counts_label.setText(f"Imagens: {train_text} treino / {val_text} validacao")
        self.training_last_message_label.setText("Atualizacao: contagem de imagens de treino/validacao recebida")

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

    def export_test_images_to_image_set(self):
        plan = load_plan(dataset_plan_path(self.config))
        test_images = [
            name for name, entry in plan.items()
            if entry.get("group") == "test"
        ]
        if not test_images:
            QMessageBox.information(
                self,
                "Exportar teste",
                "Nenhuma imagem marcada como 'teste' no dataset atual.\n"
                "Use 'Separar treino/teste' antes de exportar.",
            )
            return

        custom_sets = [n for n in list_image_sets(self.config) if n != DEFAULT_IMAGE_SET]

        dialog = QDialog(self)
        dialog.setWindowTitle("Exportar imagens de teste")
        dialog.setModal(True)
        dialog.setMinimumWidth(340)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel(f"{len(test_images)} imagem(ns) de teste encontrada(s)."))
        layout.addWidget(QLabel("Destino:"))

        CREATE_NEW = "__criar_novo__"
        combo = QComboBox()
        for name in custom_sets:
            combo.addItem(name, name)
        combo.addItem("Criar novo conjunto...", CREATE_NEW)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        target_name = combo.currentData()

        if target_name == CREATE_NEW:
            name, ok = QInputDialog.getText(self, "Novo conjunto de teste", "Nome do conjunto:")
            if not ok:
                return
            target_name = name.strip().replace(" ", "_")
            if not target_name or target_name == DEFAULT_IMAGE_SET:
                QMessageBox.information(self, "Exportar teste", "Nome invalido.")
                return
            if target_name in list_image_sets(self.config):
                QMessageBox.information(self, "Exportar teste", "Ja existe um conjunto com esse nome.")
                return

        ensure_image_set_structure(self.config, target_name)
        write_image_set_metadata(
            self.config,
            target_name,
            {"type": "test", "source_project": self.config.get("active_project", "")},
        )

        src_dir = dataset_images_dir(self.config)
        dst_dir = image_sets_dir(self.config) / target_name / "images"
        dst_dir.mkdir(parents=True, exist_ok=True)

        copied, skipped, errors = 0, 0, []
        for image_name in test_images:
            src = src_dir / image_name
            if not src.exists():
                errors.append(f"Nao encontrado: {image_name}")
                continue
            dst = dst_dir / image_name
            if dst.exists():
                skipped += 1
                continue
            try:
                shutil.copy2(src, dst)
                copied += 1
            except OSError as err:
                errors.append(f"{image_name}: {err}")

        self.append_log(
            f"\n>>> Exportar imagens de teste → conjunto '{target_name}'\n"
            f"Copiadas: {copied}\n"
            f"Ja existiam: {skipped}\n"
            f"Erros: {len(errors)}\n"
        )

        if errors:
            self.show_error(
                "Exportar teste",
                f"{len(errors)} arquivo(s) nao puderam ser copiados.",
                "\n".join(errors),
            )
        else:
            QMessageBox.information(
                self,
                "Exportar teste",
                f"{copied} imagem(ns) copiada(s) para '{target_name}'.\n"
                f"{skipped} ja existiam e foram mantidas.",
            )

