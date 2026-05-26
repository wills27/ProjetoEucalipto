from PyQt6.QtWidgets import QMessageBox

from services.config import save_config, with_derived_paths
from services.paths import SCRIPTS_DIR, active_project_dir, dataset_plan_path

class ScriptWorkflowMixin:
    def run_prepare_dataset(self):
        self.save_dataset_plan_from_table()
        self.run_script(
            "Exportar dataset",
            [
                str(SCRIPTS_DIR / "prepare_dataset.py"),
                "--project-dir",
                str(active_project_dir(self.config)),
                "--plan",
                str(dataset_plan_path(self.config)),
            ],
        )

    def run_mask_compaction(self):
        if self.process_runner.is_running():
            self.show_process_in_progress()
            return
        reply = QMessageBox.question(
            self,
            "Compactar mascaras",
            (
                "Converter _seg.npy para _masks.tif comprimido e remover os .npy duplicados?\n\n"
                "O processo valida cada TIFF antes de apagar o arquivo .npy correspondente."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.run_script(
            "Compactar mascaras",
            [
                str(SCRIPTS_DIR / "compact_masks.py"),
                "--project-dir",
                str(active_project_dir(self.config)),
            ],
        )

    def run_training(self):
        model_name = self.train_model_name.text().strip()
        if not model_name:
            QMessageBox.information(self, "Modelo", "Informe um nome para o modelo.")
            return

        self.config["active_model"] = model_name
        self.config = with_derived_paths(self.config)
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
            "--plan",
            str(dataset_plan_path(self.config)),
            "--require-gpu",
        ]
        self.run_script("Treinar modelo", args)
