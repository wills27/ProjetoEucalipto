# Rotulos amigaveis para as colunas gravadas em cell_counts.csv/
# cell_measurements.csv. Usado tanto pelas tabelas dentro do app quanto pela
# exportacao em Excel (services/result_export.py), pra nunca divergir entre
# o que o usuario ve na tela e o que sai no arquivo exportado.

# Rotulos fixos: primeira letra da primeira palavra maiuscula, resto em
# minuscula, palavras separadas por espaco (nunca "_"). "celula" vira
# "vaso" em todo lugar pra bater com o resto do app.
CSV_FIXED_LABELS = {
    "imagem": "Imagem",
    "id_vaso": "Id vaso",
    "quantidade_vasos": "Quantidade vasos",
    "percentual_area_ocupada": "Area ocupada por vaso (%)",
    # Densidade (vasos/mm2 de area total da imagem - padrao "vessel
    # frequency" da anatomia da madeira), nao contagem bruta; por isso
    # some sem calibracao (cal_only, abaixo) em vez de mostrar vazio.
    "freq_vaso_50pct": "Frequencia vasos 50% (n°/mm²)",
    "freq_vaso_inteiros": "Frequencia vasos inteiros (n°/mm²)",
}


def csv_has_calibration(headers, body):
    if "unidade" not in headers:
        return False
    unit_col = headers.index("unidade")
    return any(unit_col < len(row) and row[unit_col].strip() for row in body)


def csv_unit_symbol(headers, body):
    unit_col = headers.index("unidade")
    raw_unit = next(
        (row[unit_col].strip() for row in body if unit_col < len(row) and row[unit_col].strip()),
        "",
    )
    # "um" e um placeholder ascii pra microns (sem o simbolo grego) usado
    # na calibracao — troca so esse caso pelo mu de verdade ao exibir.
    return "µm" if raw_unit.lower() == "um" else raw_unit


def default_column_label(key):
    """Padrao para qualquer coluna sem rotulo customizado: troca '_' por
    espaco e deixa maiuscula so a primeira letra da primeira palavra (o
    resto minusculo, sem virar Title Case)."""
    text = key.replace("_", " ").strip()
    return text[:1].upper() + text[1:] if text else text


def csv_column_label(key, unit_symbol):
    if unit_symbol:
        unit_labels = {
            "area": f"Area ({unit_symbol}²)",
            "diametro_menor": f"Diametro menor ({unit_symbol})",
            "diametro_cruzado": f"Diametro cruzado ({unit_symbol})",
            "media_area": f"Area media dos vasos ({unit_symbol}²)",
            # "media_diametro_menor" e a media do eixo MENOR (mesmo
            # criterio da coluna por vaso "Diametro menor" acima) - o
            # rotulo deixa isso explicito agora que existe tambem a
            # media do diametro cruzado, logo abaixo.
            "media_diametro_menor": f"Diametro menor ({unit_symbol})",
            "media_diametro_cruzado": f"Diametro cruzado medio ({unit_symbol})",
        }
        if key in unit_labels:
            return unit_labels[key]
    if key in CSV_FIXED_LABELS:
        return CSV_FIXED_LABELS[key]
    return default_column_label(key)


def csv_visible_columns(headers, has_calibration):
    always_hidden = {
        # Nomes antigos (px/"_calibrado"): o CSV atual nao os grava mais,
        # mas um arquivo gerado antes dessa mudanca ainda pode te-los até
        # ser regerado - continuam escondidos aqui so por seguranca.
        "area_px", "diametro_menor_px", "diametro_cruzado_px",
        "media_area_px", "media_diametro_menor_px", "media_diametro_cruzado_px", "pixels_area_ocupada",
        # A unidade agora aparece embutida no nome de cada coluna
        # calibrada (ex: "Area (µm²)"), entao a coluna solta some.
        "unidade",
    }
    cal_only = {
        "area", "diametro_menor", "diametro_cruzado",
        "media_area", "media_diametro_menor", "media_diametro_cruzado",
        # Densidade por mm2 - sem calibracao nao da pra converter pixel
        # em area real, entao o valor vem None do backend e a coluna
        # inteira some (em vez de mostrar uma coluna vazia).
        "freq_vaso_50pct", "freq_vaso_inteiros",
    }
    return [
        i for i, h in enumerate(headers)
        if h not in always_hidden
        and not (not has_calibration and h in cal_only)
    ]


def prettify_table(rows):
    """Recebe linhas cruas (header + corpo, como lidas do CSV) e devolve
    (headers_bonitos, corpo) ja filtrados pelas mesmas regras de
    visibilidade/calibracao usadas na tabela do app - usado pela
    exportacao em Excel pra nunca divergir do que aparece na tela."""
    if not rows:
        return [], []
    headers, body = rows[0], rows[1:]
    has_cal = csv_has_calibration(headers, body)
    unit_symbol = csv_unit_symbol(headers, body) if has_cal else ""
    visible = csv_visible_columns(headers, has_cal)
    pretty_headers = [csv_column_label(headers[i], unit_symbol) for i in visible]
    pretty_body = [[row[i] if i < len(row) else "" for i in visible] for row in body]
    return pretty_headers, pretty_body
