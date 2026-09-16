"""Paleta Eucalipto: tokens de cor compartilhados pelo QSS (styles.py) e por
qualquer codigo Python que precise pintar algo fora do stylesheet (QColor em
tabelas, graficos, etc). Manter as cores centralizadas aqui evita hexadecimais
soltos pelo app e mantém a identidade visual (verde-claro + branco) consistente.
"""

# Escala verde-eucalipto (salvia), do quase-branco ao verde-mata.
GREEN_50 = "#EDF5EF"
GREEN_100 = "#DCEBE0"
GREEN_200 = "#B9D7C2"
GREEN_300 = "#92C0A0"
GREEN_400 = "#6FA980"
GREEN_500 = "#4F8C64"
GREEN_600 = "#3D7350"
GREEN_700 = "#2E5A3F"
GREEN_800 = "#21422E"
GREEN_900 = "#162E20"

# Base neutra.
BACKGROUND = "#F6F9F6"
SURFACE = "#FFFFFF"
SURFACE_ALT = GREEN_50
SURFACE_MUTED = "#FBFDFB"
NEUTRAL_TINT = "#EEF2EE"
BORDER = "#DCE6DE"
BORDER_STRONG = "#C3D3C7"
DIVIDER = "#E3ECE5"
CONTROL_BORDER = "#94A69B"

# Fonte serifada usada como contraponto editorial em titulos de paineis e
# valores de destaque — Georgia vem instalada por padrao no Windows, entao
# nao depende de nenhuma fonte custom embutida no app.
FONT_DISPLAY = "Georgia"
TEXT = "#1B2A21"
TEXT_SECONDARY = "#5B6B60"

# Marca / interacao.
PRIMARY = GREEN_500
PRIMARY_HOVER = GREEN_600
PRIMARY_ACTIVE = GREEN_700
ON_PRIMARY = "#FFFFFF"

HOVER_BG = GREEN_50
HOVER_BORDER = GREEN_300
PRESSED_BG = GREEN_100
PRESSED_BORDER = GREEN_400

SELECTED_BG = GREEN_600
SELECTED_TEXT = "#FFFFFF"

NAV_ACTIVE_BG = GREEN_50
NAV_ACTIVE_BORDER = GREEN_200
NAV_ACTIVE_TEXT = GREEN_700

# Acento — tom de casca de eucalipto, para CTAs secundarios pontuais.
ACCENT = "#C68A52"
ACCENT_HOVER = "#D8A46B"
ACCENT_ACTIVE = "#A96F3C"
ON_ACCENT = "#2A1B0E"

# Semanticas.
SUCCESS = "#3D7350"
WARNING = "#B4841F"
ERROR = "#A8402F"
INFO = "#3E7690"
ERROR_SURFACE = "#FBF4F2"
ERROR_BORDER = "#E7C4BC"
ERROR_TEXT = "#7A2E22"

# Estados desabilitados.
DISABLED_BG = "#EEF2EE"
DISABLED_BORDER = "#C7D2C8"

# Log / console.
LOG_BACKGROUND = "#13241B"
LOG_TEXT = "#DCEBE0"
