import gc
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile as tiff

from services.annotation import load_mask, save_mask, validate_mask_file


def replace_tiff_with_retries(temp_path, target_path, window=None, attempts=8):
    last_error = None
    for attempt in range(attempts):
        try:
            temp_path.replace(target_path)
            return
        except PermissionError as exc:
            last_error = exc
        except OSError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 5:
                raise

        if attempt == 0 and window is not None and hasattr(window, "analysis_cache"):
            window.analysis_cache.clear()
        gc.collect()

        try:
            if target_path.exists():
                target_path.chmod(0o666)
                target_path.unlink()
            temp_path.replace(target_path)
            return
        except PermissionError as exc:
            last_error = exc
        except OSError as exc:
            last_error = exc
            if getattr(exc, "winerror", None) != 5:
                raise

        time.sleep(0.25)

    raise last_error


@dataclass
class DatasetMaskTarget:
    path: Path
    seg_path: Path
    tif_mask_path: Path
    has_mask: bool
    label: str
    window: object
    commit_on_close: bool = False
    recalculate_on_close: bool = False

    @property
    def display_name(self):
        return self.path.name

    def refresh_state(self):
        validation = validate_mask_file(self.seg_path, self.tif_mask_path)
        self.has_mask = validation["valid"]
        self.label = "[Com mascara]" if self.has_mask else "[Sem mascara]"

    def load_mask(self, image_size):
        return load_mask(self.seg_path, self.tif_mask_path, image_size)

    def status_text(self):
        status = "com mascara" if self.has_mask else "sem mascara"
        return f"Selecionada: {self.path.name} ({status})"

    def save(self, mask, page, silent=False, recalculate=False):
        save_mask(self.seg_path, self.tif_mask_path, mask)
        page.set_status(f"Mascara salva: {self.seg_path.name} e {self.tif_mask_path.name}")
        self.window.pending_annotation_image_name = self.path.name
        self.refresh_state()
        if not self.has_mask:
            page.set_status(
                f"Mascara salva, mas ainda invalida: minimo de pixels/objetos nao atingido ({self.path.name})."
            )
        page.refresh_images()
        self.window.refresh_dataset_import()
        return True


@dataclass
class ResultMaskTarget:
    path: Path
    tif_mask_path: Path
    stem: str
    window: object
    label: str = "[Resultado]"
    has_mask: bool = True
    commit_on_close: bool = True
    recalculate_on_close: bool = True
    prediction_callback: object = None

    @property
    def display_name(self):
        return self.path.name

    @property
    def seg_path(self):
        return self.tif_mask_path.with_name(f"{self.stem}_pred_seg.npy")

    def refresh_state(self):
        validation = validate_mask_file(self.seg_path, self.tif_mask_path)
        self.has_mask = validation["valid"]

    def load_mask(self, image_size):
        return load_mask(self.seg_path, self.tif_mask_path, image_size)

    def status_text(self):
        return f"Selecionada: {self.path.name} (resultado)"

    def save(self, mask, page, silent=False, recalculate=False):
        self.tif_mask_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.tif_mask_path.with_name(f"{self.tif_mask_path.stem}.tmp{self.tif_mask_path.suffix}")
        mask = np.asarray(mask).astype(np.uint16)
        try:
            if hasattr(self.window, "analysis_cache"):
                self.window.analysis_cache.clear()
            tiff.imwrite(temp_path, mask)
            replace_tiff_with_retries(temp_path, self.tif_mask_path, self.window)
            np.save(self.seg_path, {"masks": mask})
        except OSError as exc:
            if not silent:
                from PyQt6.QtWidgets import QMessageBox

                QMessageBox.warning(
                    self.window,
                    "Salvar mascara",
                    "Nao foi possivel substituir a mascara editada.\n"
                    f"A copia temporaria ficou em:\n{temp_path}\n\n"
                    f"Detalhe:\n{exc}",
                )
            return False
        page.set_status(f"Mascara salva: {self.tif_mask_path.name}")
        if hasattr(self.window, "on_result_mask_saved"):
            self.window.on_result_mask_saved(self.stem, mask, recalculate=recalculate)
        self.refresh_state()
        return True
