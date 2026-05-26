import sys

from PyQt6.QtCore import QObject, QProcess, pyqtSignal


class ScriptProcessRunner(QObject):
    output_received = pyqtSignal(str)
    finished = pyqtSignal(int)
    error_occurred = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.process = None

    def is_running(self):
        return self.process is not None

    def start(self, args, working_directory):
        if self.process is not None:
            return False

        self.process = QProcess(self)
        self.process.setWorkingDirectory(str(working_directory))
        self.process.setProgram(sys.executable)
        if getattr(sys, "frozen", False):
            self.process.setArguments(["--run-script", *args])
        else:
            self.process.setArguments(["-u", *args])
        self.process.readyReadStandardOutput.connect(self.read_output)
        self.process.readyReadStandardError.connect(self.read_output)
        self.process.errorOccurred.connect(self.handle_error)
        self.process.finished.connect(self.handle_finished)
        self.process.start()
        return True

    def read_output(self):
        if self.process is None:
            return
        output = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        error = bytes(self.process.readAllStandardError()).decode("utf-8", errors="replace")
        if output:
            self.output_received.emit(output)
        if error:
            self.output_received.emit(error)

    def handle_finished(self, exit_code, _exit_status):
        self.process = None
        self.finished.emit(exit_code)

    def handle_error(self, error):
        if self.process is None:
            return
        failed_to_start = error == QProcess.ProcessError.FailedToStart
        error_message = self.process.errorString()
        if failed_to_start:
            self.process = None
        self.error_occurred.emit(error_message, failed_to_start)
