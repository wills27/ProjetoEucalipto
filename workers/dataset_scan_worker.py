from PyQt6.QtCore import QObject, pyqtSignal

from services.conversion_scan import scan_conversion_input_rows


class DatasetScanWorker(QObject):
    finished = pyqtSignal(list, str)

    def __init__(self, config):
        super().__init__()
        self.config = dict(config)

    def run(self):
        try:
            self.finished.emit(scan_conversion_input_rows(self.config), "")
        except Exception as exc:
            self.finished.emit([], str(exc))
