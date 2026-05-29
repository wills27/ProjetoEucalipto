from PyQt6.QtWidgets import QMessageBox

from pathlib import Path

from services.config import save_config, with_derived_paths
from services.dataset_manifest import manifest_mask_path
from services.paths import (
    SCRIPTS_DIR,
    active_model_path,
    dataset_images_dir,
    dataset_masks_dir,
    metrics_csv_path,
    model_outputs_dir,
    overlays_dir,
    predictions_dir,
)
from ui.dialogs.results_viewer_dialog import ResultsViewerDialog

class ResultWorkflowMixin:
    def result_ground_truth_masks(self, image_stems=None):
        selected_stems = set(image_stems or [])
        masks = []
        for entry in self.load_dataset_plan().values():
            image_name = entry.get("image", "")
            stem = Path(image_name).stem
            if selected_stems and stem not in selected_stems:
                continue
            if entry.get("group") != "test" or not entry.get("include", True):
                continue
            mask_path = manifest_mask_path(self.config, entry)
            if mask_path is not None:
                masks.append(mask_path)
        if not masks:
            return []
        return masks

    def run_results(self, image_stems=None):
        if isinstance(image_stems, bool):
            image_stems = None
        if self.process_runner.is_running():
            self.show_process_in_progress()
            return
        if not self.ensure_active_model():
            return
        self.clear_analysis_caches()
        self.save_prediction_config()
        input_dir = dataset_images_dir(self.config)
        result_entries = self.result_image_entries()
        selected_stems = list(image_stems) if image_stems else None
        args = [
            str(SCRIPTS_DIR / "generate_results.py"),
            "--model",
            str(active_model_path(self.config)),
            "--input",
            str(input_dir),
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
        if selected_stems:
            image_paths = [result_entries.get(stem, input_dir / f"{stem}.tif") for stem in selected_stems]
            missing = [path.name for path in image_paths if not path.exists()]
            if missing:
                QMessageBox.warning(
                    self,
                    "Gerar resultados",
                    "Algumas imagens selecionadas nao foram encontradas:\n" + "\n".join(missing),
                )
                return
            args.extend(["--images", *[str(path) for path in image_paths]])
        elif result_entries:
            args.extend(["--images", *[str(path) for path in result_entries.values()]])
        self.append_log(
            "\n>>> Imagens enviadas para resultados\n"
            + (
                "\n".join(selected_stems)
                if selected_stems
                else f"Todas as imagens listadas ({len(result_entries)})"
            )
            + "\n"
        )
        self.pending_result_stems = selected_stems
        if self.result_ground_truth_masks(selected_stems):
            self.pending_actions.extend([self.run_evaluation_then_measurements, self.run_cell_measurements])
        else:
            self.pending_actions.append(self.run_cell_measurements)
        self.run_script("Gerar resultados", args)

    def run_results_for_current_image(self):
        stem = self.current_result_image_stem()
        if not stem:
            QMessageBox.information(self, "Gerar resultados", "Selecione uma imagem na lista.")
            return
        self.run_results_for_stem(stem)

    def run_results_for_stem(self, stem):
        if not stem:
            QMessageBox.information(self, "Gerar resultados", "Selecione uma imagem na lista.")
            return
        self.run_results([stem])

    def run_results_for_selected_images(self):
        stems = self.selected_result_image_stems()
        if not stems:
            QMessageBox.information(self, "Gerar resultados", "Marque uma ou mais imagens na tabela.")
            return
        self.run_results(stems)

    def run_missing_result_outputs(self):
        if self.process_runner.is_running():
            self.show_process_in_progress()
            return
        if not self.ensure_active_model():
            return
        self.clear_analysis_caches()
        self.save_prediction_config()
        entries = self.result_image_entries()
        if not entries:
            QMessageBox.information(self, "Gerar resultados", "Nenhuma imagem encontrada para gerar resultados.")
            return

        missing_predictions = [stem for stem in entries if not self.result_prediction_exists(stem)]
        if missing_predictions:
            self.append_log(
                f"\n>>> Gerar resultados faltantes\n"
                f"Imagens sem predicao: {len(missing_predictions)}\n"
            )
            self.run_results(missing_predictions)
            return

        missing_overlay = [stem for stem in entries if not self.result_overlay_exists(stem, preferred_only=True)]
        missing_metrics = [stem for stem in entries if not self.result_metrics_exists(stem)]

        created_overlays, skipped_overlays = self.create_missing_result_overlays(missing_overlay)
        if missing_metrics:
            self.append_log(
                f"\n>>> Gerar resultados faltantes\n"
                f"Overlays criados: {created_overlays}\n"
                f"Overlays pulados sem predicao: {skipped_overlays}\n"
                f"Imagens sem metricas/medidas: {len(missing_metrics)}\n"
            )
            if self.result_ground_truth_masks(missing_metrics):
                self.pending_result_stems = missing_metrics
                self.pending_actions.extend([self.run_evaluation_then_measurements, self.run_cell_measurements])
            else:
                self.pending_result_stems = missing_metrics
                self.pending_actions.append(self.run_cell_measurements)
            next_action = self.pending_actions.pop(0)
            next_action()
            return

        self.append_log(
            f"\n>>> Gerar resultados faltantes\n"
            f"Overlays criados: {created_overlays}\n"
            f"Overlays pulados sem predicao: {skipped_overlays}\n"
            f"Nenhuma metrica/medida faltante.\n"
        )
        if hasattr(self, "result_progress_label"):
            self.result_progress_label.setText("Resultados faltantes: nada pendente.")
        if hasattr(self, "result_progress_bar"):
            self.result_progress_bar.setRange(0, 100)
            self.result_progress_bar.setValue(100)
            self.result_progress_bar.setFormat("100%")
        self.refresh_all()

    def create_missing_result_overlays(self, image_stems):
        overlays_dir(self.config).mkdir(parents=True, exist_ok=True)
        created = 0
        skipped = 0
        for stem in image_stems:
            pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
            if not pred_path.exists():
                skipped += 1
                continue
            mask = self.load_mask_array(pred_path)
            if mask is None:
                skipped += 1
                continue
            self.save_result_overlay(stem, mask)
            created += 1
        return created, skipped

    def open_results_viewer(self):
        dialog = ResultsViewerDialog(self)
        dialog.exec()

    def run_evaluation(self, image_stems=None):
        if not self.ensure_active_model():
            return
        selected_stems = image_stems if image_stems is not None else self.pending_result_stems
        args = [
            str(SCRIPTS_DIR / "evaluate_cellpose.py"),
            "--masks",
            str(dataset_masks_dir(self.config)),
            "--predictions",
            str(predictions_dir(self.config)),
            "--output-csv",
            str(metrics_csv_path(self.config)),
        ]
        mask_files = self.result_ground_truth_masks(selected_stems)
        if mask_files:
            args.extend(["--mask-files", *[str(path) for path in mask_files]])
        if selected_stems:
            args.extend(["--images", *selected_stems])
        self.run_script("Avaliar modelo", args)

    def run_evaluation_then_measurements(self):
        self.auto_measure_after_evaluation = True
        self.run_evaluation(self.pending_result_stems)

    def run_cell_measurements(self, image_stems=None):
        self.auto_measure_after_evaluation = False
        if not self.ensure_active_model():
            return
        selected_stems = image_stems if image_stems is not None else self.pending_result_stems
        args = [
            str(SCRIPTS_DIR / "measure_cells.py"),
            "--masks-dir",
            str(predictions_dir(self.config)),
            "--output-dir",
            str(model_outputs_dir(self.config)),
            "--pattern",
            "*_pred_masks.tif",
        ]
        if selected_stems:
            args.extend(["--images", *selected_stems])
        unit, unit_per_pixel = self.calibration()
        if unit_per_pixel > 0:
            args.extend(["--unit", unit, "--unit-per-pixel", str(unit_per_pixel)])
        self.run_script("Gerar CSVs de medidas", args)

    def run_metrics_for_current_result_image(self):
        stem = self.current_result_image_stem()
        if not stem:
            QMessageBox.information(self, "Recalcular metrica", "Selecione uma imagem na lista.")
            return
        self.run_metrics_for_result_image(stem, interactive=True)

    def run_metrics_for_result_image(self, stem, interactive=False):
        if self.process_runner.is_running():
            if interactive:
                self.show_process_in_progress()
            elif hasattr(self, "result_progress_label"):
                self.result_progress_label.setText(
                    f"Mascara salva para {stem}, mas ha um processo em andamento. Recalcule depois."
                )
            return False
        if not self.result_prediction_exists(stem):
            if interactive:
                QMessageBox.information(
                    self,
                    "Recalcular metrica",
                    "Esta imagem ainda nao tem mascara de predicao para recalcular.",
                )
            return False

        self.pending_actions.clear()
        self.pending_result_stems = [stem]
        if self.result_ground_truth_masks([stem]):
            self.pending_actions.extend([self.run_evaluation_then_measurements, self.run_cell_measurements])
        else:
            self.pending_actions.append(self.run_cell_measurements)
        next_action = self.pending_actions.pop(0)
        next_action()
        return True

    def save_prediction_config(self):
        self.config = with_derived_paths(self.config)
        self.config["padding_pixels"] = max(0, int(self.parse_float(self.pred_padding.text(), 0)))
        self.config["diameter"] = self.parse_float(self.pred_diameter.text(), 0.0)
        self.config["cellprob_threshold"] = self.parse_float(self.pred_cellprob.text(), 0.0)
        self.config["flow_threshold"] = self.parse_float(self.pred_flow.text(), 0.4)
        save_config(self.config)
