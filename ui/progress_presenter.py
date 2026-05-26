from PyQt6.QtCore import QTimer, Qt

from services.process_output import parse_progress_line, result_status_stem_from_line as parse_result_status_stem


class ProgressPresenterMixin:
    def start_task_progress(self, title, total=0, detail=""):
        if not hasattr(self, "task_progress_bar"):
            return
        self.task_progress_label.setText(detail or title)
        self.task_progress_label.show()
        self.task_progress_bar.show()
        if total > 0:
            self.task_progress_bar.setRange(0, total)
            self.task_progress_bar.setValue(0)
            self.task_progress_bar.setFormat("%p%")
        else:
            self.task_progress_bar.setRange(0, 0)
            self.task_progress_bar.setFormat("")
        self.statusBar().showMessage(detail or title)

    def update_task_progress(self, current, total, detail=""):
        if not hasattr(self, "task_progress_bar"):
            return
        total = max(1, int(total))
        current = min(max(0, int(current)), total)
        self.task_progress_label.setText(detail or self.current_process_title or "Processando")
        self.task_progress_label.show()
        self.task_progress_bar.show()
        self.task_progress_bar.setRange(0, total)
        self.task_progress_bar.setValue(current)
        self.task_progress_bar.setFormat(f"{int((current / total) * 100)}%")
        if detail:
            self.statusBar().showMessage(detail)

    def finish_task_progress(self, message, success=True):
        if not hasattr(self, "task_progress_bar"):
            return
        self.task_progress_bar.setRange(0, 100)
        self.task_progress_bar.setValue(100 if success else 0)
        self.task_progress_bar.setFormat("100%" if success else "Erro")
        self.task_progress_label.setText(message)
        self.statusBar().showMessage(message, 5000)
        QTimer.singleShot(5000, self.hide_task_progress)

    def hide_task_progress(self):
        if not hasattr(self, "task_progress_bar"):
            return
        self.task_progress_label.hide()
        self.task_progress_bar.hide()

    def update_task_progress_from_output(self, text):
        if self.current_process_title not in {"Exportar dataset", "Compactar mascaras"}:
            return
        for line in text.splitlines():
            progress = parse_progress_line(line)
            if not progress:
                continue
            current = progress["current"]
            total = progress["total"]
            detail = progress["detail"] or "Preparando dataset"
            self.update_task_progress(current, total, detail)

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
            progress = parse_progress_line(line)
            if not progress:
                continue
            current = progress["current"]
            total = max(1, progress["total"])
            detail = progress["detail"]
            self.result_progress_bar.setRange(0, total)
            self.result_progress_bar.setValue(min(current, total))
            self.result_progress_bar.setFormat(f"{current}/{total}")
            if detail:
                self.result_progress_label.setText(detail)

    def update_result_status_from_output(self, text):
        if self.current_process_title not in self.result_process_titles:
            return
        if not hasattr(self, "result_images_table"):
            return
        if getattr(self, "current_process_model", "") != (self.config.get("active_model") or ""):
            return
        for line in text.splitlines():
            stem = parse_result_status_stem(line)
            if not stem:
                continue
            if "Overlay salvo:" in line or "Resultados:" in line:
                self.runtime_overlay_ready_stems.add(stem)
            if self.current_process_title in {"Avaliar modelo", "Gerar CSVs de medidas"}:
                self.runtime_metrics_ready_stems.add(stem)
            self.update_result_status_row(stem)

    def update_result_status_row(self, stem):
        row = self.result_table_row_for_stem(stem)
        if row < 0:
            return
        self.result_images_table.blockSignals(True)
        overlay_item = self.result_status_item(self.result_overlay_exists(stem))
        overlay_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_images_table.setItem(row, 2, overlay_item)
        metrics_item = self.result_status_item(self.result_metrics_exists(stem))
        metrics_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.result_images_table.setItem(row, 3, metrics_item)
        self.result_images_table.blockSignals(False)

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

