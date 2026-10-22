"""Sistema central de traducao do app (primeira rodada - ver plano). Ingles
e o idioma padrao; portugues fica disponivel como alternativa. Cobre por
enquanto a barra lateral, o menu superior, o dialog de calibracao e o painel
de resultados/predicao - as demais telas (treino, importacao de dataset,
dialogs avancados) continuam em portugues ate entrarem numa rodada seguinte.

Uso: `from services.i18n import tr` e troca o literal por `tr("chave")`. Pra
telas que ficam abertas durante toda a sessao (janela principal, sidebar),
quem monta esses widgets tambem precisa reaplicar `tr()` num
`retranslate_ui()` quando o idioma muda - dialogs que sao recriados do zero a
cada abertura (ex. CalibrationDialog) nao precisam disso, ja nascem no
idioma atual.
"""

DEFAULT_LANGUAGE = "en"

AVAILABLE_LANGUAGES = {
    "en": "English",
    "pt": "Português",
}

_current_language = DEFAULT_LANGUAGE

STRINGS = {
    "en": {
        # Sidebar
        "sidebar.calibration": "Calibration",
        "sidebar.import_images": "Import images",
        "sidebar.model": "Model",
        # Top menu
        "menu.file": "File",
        "menu.file.exit": "Exit",
        "menu.model": "Model",
        "menu.model.import": "Import model",
        "menu.model.remove": "Remove model",
        "menu.model.promote": "Promote model to shared",
        "menu.model.train": "Train model",
        "menu.model.compact_masks": "Compact masks",
        "menu.results": "Results",
        "menu.results.generate": "Generate results",
        "menu.results.view": "View results",
        "menu.help": "Help",
        "menu.help.about": "About",
        "menu.language": "Language",
        "about.title": "About",
        "about.text": (
            "Cellpose - Eucalyptus Vessels\n\n"
            "Local interface to prepare datasets, train models, generate predictions, "
            "create overlays and evaluate metrics per project."
        ),
        "file_not_found.title": "File not found",
        # Calibration dialog
        "calibration.title": "Calibration",
        "calibration.reference_image": "Reference image",
        "calibration.import_image": "Import image",
        "calibration.scale": "Scale",
        "calibration.unit": "Unit",
        "calibration.pixel_distance": "Pixel distance",
        "calibration.real_distance": "Real distance",
        "calibration.px_per_unit": "Px/unit",
        "calibration.hint": (
            "Click to mark the first point and click again to mark the second "
            "(Shift locks to horizontal/vertical); drag an existing point to reposition it, "
            "or enter the values manually."
        ),
        "calibration.save": "Save calibration",
        "calibration.clear": "Clear calibration",
        "calibration.close": "Close",
        "calibration.open_image_to_mark_points": "Open an image to mark the points.",
        "calibration.open_image_or_enter_manually": "Open an image or enter the scale manually.",
        "calibration.choose_image": "Choose image for calibration",
        "calibration.enter_valid_numbers": "Enter valid numeric values.",
        "calibration.enter_scale_above_zero": "Enter a unit/px scale greater than zero.",
        "calibration.saved": "Calibration saved.",
        "calibration.not_set": "Calibration: not set",
        "calibration.label_prefix": "Calibration",
        "calibration.required_title": "Calibration required",
        "calibration.required_text": (
            'Set the project calibration before generating results ("Calibrate" button). '
            "Without calibration, the measurements CSV would have no area/diameter values."
        ),
        # Results / prediction panel
        "results.prediction": "Prediction",
        "results.parameters": "Parameters",
        "results.diameter_estimate": "Estimated diameter",
        "results.padding": "Padding",
        "results.cellprob": "Cell prob",
        "results.flow": "Flow",
        "results.generate": "Generate results",
        "results.view": "View results",
        "results.export": "Export results",
        "results.waiting": "Waiting for process.",
        "results.images": "Images",
        "results.header_image": "Image",
        "results.header_overlay": "Overlay",
        "results.header_metrics": "Metrics",
        "results.viewer": "Viewer",
        "results.mode_original": "Original",
        "results.mode_mask": "Mask",
        "results.mode_freq_50": "Freq. 50%",
        "results.mode_freq_100": "Freq. 100%",
        "results.mode_diameter": "Diameter",
        "results.mode_diameter_cross": "Cross diameter",
        "results.colorful": "Colorful",
        "results.export_image": "Export image",
        "results.edit_mask": "Edit mask",
        "results.mode_not_found": "Image or prediction not found for this mode.",
        "results.file_not_found": "File not found for this mode.",
        "model.none_selected": "No model selected",
    },
    "pt": {
        # Sidebar
        "sidebar.calibration": "Calibração",
        "sidebar.import_images": "Importar imagens",
        "sidebar.model": "Modelo",
        # Top menu
        "menu.file": "Arquivo",
        "menu.file.exit": "Sair",
        "menu.model": "Modelo",
        "menu.model.import": "Importar modelo",
        "menu.model.remove": "Remover modelo",
        "menu.model.promote": "Promover modelo para compartilhados",
        "menu.model.train": "Treinar modelo",
        "menu.model.compact_masks": "Compactar máscaras",
        "menu.results": "Resultados",
        "menu.results.generate": "Gerar resultados",
        "menu.results.view": "Visualizar resultados",
        "menu.help": "Ajuda",
        "menu.help.about": "Sobre",
        "menu.language": "Idioma",
        "about.title": "Sobre",
        "about.text": (
            "Cellpose - Vasos de Eucalipto\n\n"
            "Interface local para preparar datasets, treinar modelos, gerar predições, "
            "criar overlays e avaliar métricas por projeto."
        ),
        "file_not_found.title": "Arquivo não encontrado",
        # Calibration dialog
        "calibration.title": "Calibração",
        "calibration.reference_image": "Imagem de referência",
        "calibration.import_image": "Importar Imagem",
        "calibration.scale": "Escala",
        "calibration.unit": "Unidade",
        "calibration.pixel_distance": "Distância px",
        "calibration.real_distance": "Distância real",
        "calibration.px_per_unit": "Px/unidade",
        "calibration.hint": (
            "Clique para marcar o primeiro ponto e clique novamente para marcar o segundo "
            "(Shift trava na horizontal/vertical); arraste um ponto existente para reposicioná-lo, "
            "ou informe os valores manualmente."
        ),
        "calibration.save": "Salvar calibração",
        "calibration.clear": "Limpar calibração",
        "calibration.close": "Fechar",
        "calibration.open_image_to_mark_points": "Abra uma imagem para marcar os pontos.",
        "calibration.open_image_or_enter_manually": "Abra uma imagem ou informe a escala manualmente.",
        "calibration.choose_image": "Escolher imagem para calibração",
        "calibration.enter_valid_numbers": "Informe valores numéricos válidos.",
        "calibration.enter_scale_above_zero": "Informe uma escala unidade/px maior que zero.",
        "calibration.saved": "Calibração salva.",
        "calibration.not_set": "Calibração: não definida",
        "calibration.label_prefix": "Calibração",
        "calibration.required_title": "Calibração necessária",
        "calibration.required_text": (
            'Defina a calibração do projeto antes de gerar resultados (botão "Calibrar"). '
            "Sem calibração, o CSV de medidas sairia sem nenhum valor de área/diâmetro."
        ),
        # Results / prediction panel
        "results.prediction": "Predição",
        "results.parameters": "Parâmetros",
        "results.diameter_estimate": "Diâmetro estimado",
        "results.padding": "Padding",
        "results.cellprob": "Cell prob",
        "results.flow": "Flow",
        "results.generate": "Gerar resultados",
        "results.view": "Visualizar resultados",
        "results.export": "Exportar resultados",
        "results.waiting": "Aguardando processo.",
        "results.images": "Imagens",
        "results.header_image": "Imagem",
        "results.header_overlay": "Overlay",
        "results.header_metrics": "Métricas",
        "results.viewer": "Visualizador",
        "results.mode_original": "Original",
        "results.mode_mask": "Máscara",
        "results.mode_freq_50": "Freq. 50%",
        "results.mode_freq_100": "Freq. 100%",
        "results.mode_diameter": "Diâmetro",
        "results.mode_diameter_cross": "Diâmetro cruzado",
        "results.colorful": "Colorido",
        "results.export_image": "Exportar imagem",
        "results.edit_mask": "Editar máscara",
        "results.mode_not_found": "Imagem ou predição não encontrada para este modo.",
        "results.file_not_found": "Arquivo não encontrado para este modo.",
        "model.none_selected": "Nenhum modelo selecionado",
    },
}


def get_language():
    return _current_language


def set_language(language):
    global _current_language
    _current_language = language if language in STRINGS else DEFAULT_LANGUAGE


def tr(key):
    strings = STRINGS.get(_current_language, STRINGS[DEFAULT_LANGUAGE])
    return strings.get(key, STRINGS[DEFAULT_LANGUAGE].get(key, key))
