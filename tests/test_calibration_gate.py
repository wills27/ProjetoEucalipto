from ui.project_presenter import ProjectPresenterMixin


class _FakeWindow(ProjectPresenterMixin):
    def __init__(self, unit_per_pixel):
        self.config = {"calibration": {"unit": "um", "unit_per_pixel": unit_per_pixel}}


def test_ensure_calibration_fails_silently_without_calibration():
    window = _FakeWindow(unit_per_pixel=0.0)
    assert window.ensure_calibration(silent=True) is False


def test_ensure_calibration_passes_with_calibration():
    window = _FakeWindow(unit_per_pixel=1.5)
    assert window.ensure_calibration(silent=True) is True
