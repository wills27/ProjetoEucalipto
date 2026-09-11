from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class LossPlotWidget(QWidget):
    def __init__(self, total_epochs=100, parent=None):
        super().__init__(parent)
        self.figure = Figure(figsize=(6, 3), tight_layout=True)
        self.canvas = FigureCanvas(self.figure)
        self.canvas.setMinimumHeight(240)
        self.axes = self.figure.add_subplot(111)
        self.epochs = []
        self.train_losses = []
        self.val_losses = []
        self.total_epochs = total_epochs

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 1)

        self.reset(total_epochs)

    def reset(self, total_epochs=None):
        if total_epochs is not None:
            self.total_epochs = total_epochs
        self.epochs = []
        self.train_losses = []
        self.val_losses = []
        self._draw_empty()

    def add_point(self, epoch, train_loss, val_loss):
        if train_loss is None and val_loss is None:
            return
        if epoch in self.epochs:
            index = self.epochs.index(epoch)
            self.train_losses[index] = train_loss
            self.val_losses[index] = val_loss
        else:
            self.epochs.append(epoch)
            self.train_losses.append(train_loss)
            self.val_losses.append(val_loss)
        self._draw_points()

    def _configure_axes(self):
        self.axes.set_title("Curva de Perda")
        self.axes.set_xlabel("Epoch")
        self.axes.set_ylabel("Loss")
        self.axes.set_xlim(0, max(1, self.total_epochs))
        self.axes.grid(False)

    def _draw_empty(self):
        self.axes.clear()
        self._configure_axes()
        self.axes.set_ylim(0, 1)
        self.axes.text(
            0.5,
            0.5,
            "Aguardando metricas do treino",
            transform=self.axes.transAxes,
            ha="center",
            va="center",
            color="#69736d",
        )
        self.canvas.draw_idle()

    def _draw_points(self):
        self.axes.clear()
        self._configure_axes()
        train_points = [
            (epoch, loss)
            for epoch, loss in zip(self.epochs, self.train_losses)
            if loss is not None
        ]
        if train_points:
            epochs, losses = zip(*train_points)
            self.axes.plot(epochs, losses, color="#1f77b4", marker="o", markersize=5, linewidth=1)
            upper = max(1.0, max(losses) * 1.15)
            self.axes.set_ylim(0, upper)
        self.canvas.draw_idle()

    def has_data(self):
        return bool(self.train_losses) or bool(self.val_losses)

    def export_to_file(self, file_path):
        train_points = [
            (epoch, loss)
            for epoch, loss in zip(self.epochs, self.train_losses)
            if loss is not None
        ]
        figure = Figure(figsize=(8, 5))
        axes = figure.add_subplot(111)
        axes.set_title("Curva de Perda")
        axes.set_xlabel("Epoch")
        axes.set_ylabel("Loss (1.a)")
        if train_points:
            epochs, losses = zip(*train_points)
            axes.plot(epochs, losses, color="#1f77b4", marker="o", markersize=5, linewidth=1, label="Loss (1.a)")
            axes.set_xlim(0, max(1, self.total_epochs))
            axes.set_ylim(0, max(1.0, max(losses) * 1.15))
            axes.legend(loc="best")
        figure.tight_layout()
        figure.savefig(str(file_path), dpi=150, bbox_inches="tight")

    def load_history(self, epochs, train_losses, val_losses):
        self.epochs = list(epochs)
        self.train_losses = list(train_losses)
        self.val_losses = list(val_losses)
        if self.epochs:
            self.total_epochs = max(self.total_epochs, max(self.epochs) + 1)
        self._draw_points()
