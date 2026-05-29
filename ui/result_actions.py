from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QMessageBox

from services.csv_files import remove_rows_from_csv as remove_csv_rows
from services.dataset_manifest import update_plan_entry_group
from services.overlay_rendering import transparent_overlay_from_mask as render_transparent_overlay
from services.paths import (
    cell_counts_csv_path,
    cell_measurements_csv_path,
    metrics_csv_path,
    overlays_dir,
    predictions_dir,
)
from services.result_service import (
    build_result_status_index as collect_result_status_index,
    conversion_input_image_for_stem as find_conversion_input_image,
    image_mask_exists,
    legacy_result_overlay_paths as result_legacy_overlay_paths,
    move_to_removed_folder as move_file_to_removed_folder,
    result_conversion_input_images as collect_result_conversion_input_images,
    result_image_entries as collect_result_image_entries,
    result_metrics_exists as check_result_metrics_exists,
    result_output_removal_targets as collect_result_output_removal_targets,
    result_overlay_exists as check_result_overlay_exists,
    result_overlay_path as build_result_overlay_path,
    result_prediction_exists as check_result_prediction_exists,
)
from ui.mask_edit_target import ResultMaskTarget


class ResultActionsMixin:
    def open_selected_result_mask_editor(self):
        stem = self.current_result_image_stem()
        if not stem:
            QMessageBox.information(self, "Editar mascara", "Selecione uma imagem na lista de resultados.")
            return
        image_path = self.result_image_path(stem)
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if image_path is None or not image_path.exists():
            QMessageBox.information(self, "Editar mascara", "Imagem original nao encontrada.")
            return
        if not pred_path.exists():
            QMessageBox.information(
                self,
                "Editar mascara",
                "Mascara de predicao nao encontrada. Gere resultados para esta imagem antes de editar.",
            )
            return

        target = ResultMaskTarget(
            path=image_path,
            tif_mask_path=pred_path,
            stem=stem,
            window=self,
            prediction_callback=lambda image_stem=stem: self.run_results_for_stem(image_stem),
        )
        self.annotation_page.show_image(target)
        self.annotation_page.open_editor()

    def on_result_mask_saved(self, stem, mask, recalculate=False):
        self.clear_analysis_caches()
        self.create_result_overlay(stem, mask)
        removed_rows = self.invalidate_result_metrics(stem)
        self.runtime_metrics_ready_stems.discard(stem)
        self.update_result_status_row(stem)
        if not recalculate:
            self.refresh_analysis_metrics()
            self.refresh_measurement_tables()
            self.show_analysis_image(stem)
        if hasattr(self, "result_progress_label"):
            self.result_progress_label.setText(
                f"Mascara editada para {stem}. Recalculando metricas..."
                if recalculate
                else f"Mascara editada para {stem}. Metrica invalidada; use Recalcular metrica."
            )
        self.append_log(
            f"\n>>> Mascara de resultado editada\n"
            f"Imagem: {stem}\n"
            f"Overlay atualizado: sim\n"
            f"CSVs invalidados: {removed_rows}\n"
        )
        if recalculate:
            QTimer.singleShot(0, lambda image_stem=stem: self.run_metrics_for_result_image(image_stem))

    def create_result_overlay(self, stem, mask=None):
        pred_path = predictions_dir(self.config) / f"{stem}_pred_masks.tif"
        if mask is None:
            if not pred_path.exists():
                return False
            mask = self.load_mask_array(pred_path)
        if mask is None:
            return False
        self.save_result_overlay(stem, mask)
        self.runtime_overlay_ready_stems.add(stem)
        return True

    def result_overlay_path(self, stem):
        return build_result_overlay_path(self.config, stem)

    def legacy_result_overlay_paths(self, stem):
        return result_legacy_overlay_paths(self.config, stem)

    def save_result_overlay(self, stem, mask, alpha=118):
        overlays_dir(self.config).mkdir(parents=True, exist_ok=True)
        overlay = self.transparent_overlay_from_mask(mask, alpha=alpha)
        overlay_path = self.result_overlay_path(stem)
        overlay.save(overlay_path, format="PNG", optimize=True)
        for legacy_path in self.legacy_result_overlay_paths(stem):
            if legacy_path.exists():
                try:
                    legacy_path.unlink()
                except OSError:
                    pass
        self.runtime_overlay_ready_stems.add(stem)
        return overlay_path

    def transparent_overlay_from_mask(self, mask, alpha=118):
        return render_transparent_overlay(mask, alpha=alpha)

    def invalidate_result_metrics(self, stem):
        removed = 0
        removed += self.remove_rows_from_csv(metrics_csv_path(self.config), "image", stem)
        removed += self.remove_rows_from_csv(cell_counts_csv_path(self.config), "filename", stem)
        removed += self.remove_rows_from_csv(cell_measurements_csv_path(self.config), "filename", stem)
        return removed

    def result_overlay_exists(self, stem, preferred_only=False):
        self.ensure_result_status_index_current()
        return check_result_overlay_exists(
            self.config,
            stem,
            status_index=getattr(self, "result_status_index", {}),
            runtime_overlay_ready_stems=getattr(self, "runtime_overlay_ready_stems", set()),
            preferred_only=preferred_only,
        )

    def result_prediction_exists(self, stem):
        self.ensure_result_status_index_current()
        return check_result_prediction_exists(
            self.config,
            stem,
            status_index=getattr(self, "result_status_index", {}),
        )

    def result_metrics_exists(self, stem):
        self.ensure_result_status_index_current()
        return check_result_metrics_exists(
            self.config,
            stem,
            status_index=getattr(self, "result_status_index", {}),
            runtime_metrics_ready_stems=getattr(self, "runtime_metrics_ready_stems", set()),
        )

    def build_result_status_index(self, entries=None):
        self.result_status_index_model = self.config.get("active_model") or ""
        self.result_status_index = collect_result_status_index(
            self.config,
            entries=entries,
            runtime_overlay_ready_stems=getattr(self, "runtime_overlay_ready_stems", set()),
            runtime_metrics_ready_stems=getattr(self, "runtime_metrics_ready_stems", set()),
        )

    def ensure_result_status_index_current(self):
        active_model = self.config.get("active_model") or ""
        if getattr(self, "result_status_index_model", None) == active_model and self.result_status_index:
            return
        entries = self.result_entries_cache if self.result_entries_cache is not None else None
        self.build_result_status_index(entries)

    def result_image_entries(self):
        if self.result_entries_cache is not None:
            return self.result_entries_cache
        self.result_entries_cache = collect_result_image_entries(self.config, self.load_dataset_plan())
        return self.result_entries_cache

    def result_conversion_input_images(self):
        return collect_result_conversion_input_images(self.config)

    def result_input_mask_exists(self, image_path):
        return image_mask_exists(image_path)

    def result_image_path(self, stem):
        if not stem:
            return None
        return self.result_image_entries().get(stem)

    def current_result_image_stem(self):
        if not hasattr(self, "result_images_table"):
            return None
        return self.result_table_stem(self.result_images_table.currentRow())

    def selected_result_image_stems(self):
        if not hasattr(self, "result_images_table"):
            return []
        return self.checked_result_image_stems()

    def context_result_image_stems(self):
        if not hasattr(self, "result_images_table"):
            return []

        checked_stems = self.checked_result_image_stems()
        if checked_stems:
            return checked_stems

        stems = []
        selected_rows = sorted({index.row() for index in self.result_images_table.selectedIndexes()})
        for row in selected_rows:
            stem = self.result_table_stem(row)
            if stem and stem not in stems:
                stems.append(stem)
        if stems:
            return stems

        stem = self.current_result_image_stem()
        return [stem] if stem else []

    def run_results_for_context_images(self):
        stems = self.context_result_image_stems()
        if not stems:
            QMessageBox.information(self, "Gerar resultados", "Selecione uma ou mais imagens na tabela.")
            return
        self.run_results(stems)

    def remove_context_result_images(self):
        self.remove_result_images(self.context_result_image_stems())

    def remove_selected_result_image(self):
        self.remove_result_images(self.selected_result_image_stems())

    def remove_result_images(self, image_stems):
        if not hasattr(self, "result_images_table"):
            return

        if not image_stems:
            QMessageBox.information(self, "Remover imagem", "Selecione ou marque uma ou mais imagens na tabela.")
            return

        image_label = image_stems[0] if len(image_stems) == 1 else f"{len(image_stems)} imagens"
        reply = QMessageBox.question(
            self,
            "Remover imagem",
            (
                f"Remover {image_label} da aba de resultados e do conjunto test?\n\n"
                "As imagens e mascaras ficarao nos arquivos atuais e voltarao para a aba Dados como Sem categoria. "
                "Predicoes, overlays e linhas dos CSVs serao removidos dos resultados."
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        recategorized_images = []
        moved_paths = []
        missing_paths = []
        csv_updates = 0
        for image_stem in image_stems:
            returned = self.return_result_image_to_uncategorized(image_stem)
            if returned:
                recategorized_images.append(returned)

            for source_path, removed_dir in self.result_output_removal_targets(image_stem):
                if not source_path.exists():
                    missing_paths.append(source_path)
                    continue
                moved_paths.append(self.move_to_removed_folder(source_path, removed_dir))

            csv_updates += self.remove_rows_from_csv(metrics_csv_path(self.config), "image", image_stem)
            csv_updates += self.remove_rows_from_csv(cell_counts_csv_path(self.config), "filename", image_stem)
            csv_updates += self.remove_rows_from_csv(cell_measurements_csv_path(self.config), "filename", image_stem)

        self.clear_analysis_caches()
        self.preview_label.setText("Selecione uma imagem.")
        self.preview_label.setPixmap(QPixmap())
        self.update_metric_panel(None)
        self.refresh_analysis_images()
        self.refresh_analysis_metrics()
        self.refresh_measurement_tables()
        self.refresh_dataset_import()
        self.refresh_project()

        self.append_log(
            f"\n>>> Remover imagem dos resultados\n"
            f"Imagens: {', '.join(image_stems)}\n"
            f"Marcadas como Sem categoria: {', '.join(recategorized_images) if recategorized_images else 'nenhuma'}\n"
            f"Arquivos de resultado movidos: {len(moved_paths)}\n"
            f"Arquivos nao encontrados: {len(missing_paths)}\n"
            f"CSVs atualizados: {csv_updates}\n"
        )

    def return_result_image_to_uncategorized(self, image_stem):
        entry = update_plan_entry_group(self.config, image_stem, "uncategorized")
        if entry is None:
            return None
        self.result_entries_cache = None
        return entry["image"]

    def conversion_input_image_for_stem(self, image_stem):
        return find_conversion_input_image(self.config, image_stem)

    def input_mask_exists(self, image_path):
        return image_mask_exists(image_path)

    def result_output_removal_targets(self, image_stem):
        return collect_result_output_removal_targets(self.config, image_stem)

    def move_to_removed_folder(self, source_path, removed_dir):
        return move_file_to_removed_folder(source_path, removed_dir)

    def remove_rows_from_csv(self, path, column_name, image_stem):
        return remove_csv_rows(path, column_name, image_stem)
