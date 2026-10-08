from services.cell_measurements import (
    MEASUREMENT_COLUMNS,
    SUMMARY_COLUMNS,
    build_measurement_rows,
    build_summary_row,
)
from ui.analysis_presenter import AnalysisPresenterMixin


class _FakeRegion:
    def __init__(self, label, area):
        self.label = label
        self.area = area


class _FakeEllipse:
    def __init__(self, minor_axis_length, diametro_cruzado=0.0):
        self.minor_axis_length = minor_axis_length
        self.diametro_cruzado = diametro_cruzado


def _labeled_dict(label):
    return AnalysisPresenterMixin._csv_column_label(AnalysisPresenterMixin(), label, "")


def test_build_measurement_rows_matches_declared_columns():
    props = [_FakeRegion(1, 100.0)]
    ellipses = {1: _FakeEllipse(10.0, 12.0)}
    rows = build_measurement_rows("img1", props, ellipses, unit="um", unit_per_pixel=0.5)
    assert set(rows[0].keys()) == set(MEASUREMENT_COLUMNS)


def test_build_summary_row_matches_declared_columns():
    props = [_FakeRegion(1, 100.0)]
    ellipses = {1: _FakeEllipse(10.0, 12.0)}
    row = build_summary_row(
        "img1", props, ellipses,
        area_total_vasos=100, area_total_img=1000,
        freq_vaso_50pct_count=1, total_vasos_count=1,
        unit="um", unit_per_pixel=0.5,
    )
    assert set(row.keys()) == set(SUMMARY_COLUMNS)


def test_every_csv_column_has_a_friendly_label():
    """Toda coluna gravada no CSV deve ter um rotulo amigavel equivalente
    mostrado na tela (mesmo padrao de nomes cobrado pelo usuario). Uma
    coluna sem entrada em _CSV_FIXED_LABELS cai no rotulo generico
    (underscore -> espaco), que ainda e aceitavel para colunas puramente
    tecnicas (ex: 'unidade', '*_px' escondidas), mas nunca deve devolver
    a chave crua sem nenhum tratamento."""
    presenter = AnalysisPresenterMixin()
    for column in set(MEASUREMENT_COLUMNS) | set(SUMMARY_COLUMNS):
        label = presenter._csv_column_label(column, "")
        assert label, f"coluna sem rotulo: {column}"
        assert "_" not in label, f"coluna {column} caiu no rotulo cru: {label!r}"


def test_no_stray_celula_wording_in_csv_columns():
    """'celula' nao deve mais aparecer nos nomes de coluna gravados no
    CSV - o app usa 'vaso' em todo lugar (inclusive no CSV agora)."""
    for column in MEASUREMENT_COLUMNS + SUMMARY_COLUMNS:
        assert "celula" not in column
