"""Shared constants for image import/scan support."""

COMMON_IMAGE_EXTENSIONS = [
    ".tif",
    ".tiff",
    ".png",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".webp",
    ".gif",
]

IMAGE_EXTENSIONS = COMMON_IMAGE_EXTENSIONS
COMMON_IMAGE_EXTENSIONS_SET = set(COMMON_IMAGE_EXTENSIONS)

# Used by dataset import conversion routines
SUPPORTED_CONVERSION_EXTENSIONS = COMMON_IMAGE_EXTENSIONS_SET

# Used by prediction import discovery
SUPPORTED_EXTENSIONS = COMMON_IMAGE_EXTENSIONS_SET
