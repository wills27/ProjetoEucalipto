import pandas as pd

from services.csv_files import load_semicolon_csv
from services.csv_labels import prettify_table

# Nomes pedidos pelo usuario para as duas planilhas do arquivo exportado -
# "Media por imagens" (resumo por imagem, cell_counts.csv) e "Valores por
# celulas" (um vaso por linha, cell_measurements.csv). Fica tudo em 1
# arquivo .xlsx com 2 abas em vez de 2 .csv separados.
SHEET_SUMMARY = "Média por imagens"
SHEET_MEASUREMENTS = "Valores por células"


def export_results_xlsx(counts_path, measurements_path, output_path):
    counts_rows = load_semicolon_csv(counts_path)
    measurement_rows = load_semicolon_csv(measurements_path)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        _write_sheet(writer, SHEET_SUMMARY, counts_rows)
        _write_sheet(writer, SHEET_MEASUREMENTS, measurement_rows)

    return output_path


def _write_sheet(writer, sheet_name, rows):
    headers, body = prettify_table(rows)
    pd.DataFrame(body, columns=headers).to_excel(writer, sheet_name=sheet_name, index=False)
