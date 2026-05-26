from pathlib import Path
import shutil

from PyQt6.QtCore import QObject, pyqtSignal


class FileCopyWorker(QObject):
    finished = pyqtSignal(int, int, str, list)
    progress = pyqtSignal(int, int, str)

    def __init__(self, files, target_dir):
        super().__init__()
        self.files = files
        self.target_dir = Path(target_dir)

    def run(self):
        copied = 0
        skipped = 0
        last_model_name = ""
        errors = []
        file_sizes = {}
        total_bytes = 0

        for file_name in self.files:
            source_path = Path(file_name)
            try:
                if source_path.is_file():
                    size = source_path.stat().st_size
                    file_sizes[str(source_path)] = size
                    total_bytes += size
            except OSError:
                continue

        total_bytes = max(1, total_bytes)
        copied_bytes = 0

        try:
            self.target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            errors.append(f"{self.target_dir}: {exc}")
            self.finished.emit(copied, skipped, last_model_name, errors)
            return

        for file_name in self.files:
            source_path = Path(file_name)
            if not source_path.is_file():
                skipped += 1
                continue

            source_size = file_sizes.get(str(source_path), 0)
            destination_path = self.target_dir / source_path.name
            if destination_path.exists():
                skipped += 1
                copied_bytes += source_size
                self.progress.emit(min(copied_bytes, total_bytes), total_bytes, source_path.name)
                continue

            try:
                with source_path.open("rb") as source_file, destination_path.open("wb") as destination_file:
                    while True:
                        chunk = source_file.read(4 * 1024 * 1024)
                        if not chunk:
                            break
                        destination_file.write(chunk)
                        copied_bytes += len(chunk)
                        self.progress.emit(min(copied_bytes, total_bytes), total_bytes, source_path.name)
                shutil.copystat(source_path, destination_path)
            except OSError as exc:
                errors.append(f"{source_path.name}: {exc}")
                if destination_path.exists():
                    try:
                        destination_path.unlink()
                    except OSError:
                        pass
                continue

            copied += 1
            last_model_name = destination_path.name

        self.finished.emit(copied, skipped, last_model_name, errors)
