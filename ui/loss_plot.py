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
        self.axes.set_title("Perda por epoca")
        self.axes.set_xlabel("Epoca")
        self.axes.set_ylabel("Loss")
        self.axes.set_xlim(0, max(1, self.total_epochs))
        self.axes.grid(True, color="#d9dfd8", linewidth=0.8)

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
        val_points = [
            (epoch, loss)
            for epoch, loss in zip(self.epochs, self.val_losses)
            if loss is not None
        ]
        if train_points:
            epochs, losses = zip(*train_points)
            self.axes.plot(epochs, losses, color="#166b5c", marker="o", linewidth=2, label="Treino")
        if val_points:
            epochs, losses = zip(*val_points)
            self.axes.plot(epochs, losses, color="#315f9f", marker="o", linewidth=2, label="Validacao")
        if train_points or val_points:
            all_losses = [loss for _epoch, loss in train_points + val_points]
            upper = max(1.0, max(all_losses) * 1.15)
            self.axes.set_ylim(0, upper)
            self.axes.legend(loc="best")
        self.canvas.draw_idle()
