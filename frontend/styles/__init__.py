from PySide6.QtGui import QColor
from PySide6.QtWidgets import QGraphicsDropShadowEffect


def _build_shadow(color_hex: str, alpha: int, blur: int, offset_x: int, offset_y: int, parent):
    shadow = QGraphicsDropShadowEffect(parent)
    shadow_color = QColor(color_hex)
    shadow_color.setAlpha(alpha)
    shadow.setColor(shadow_color)
    shadow.setBlurRadius(blur)
    shadow.setOffset(offset_x, offset_y)
    return shadow


def apply_shadow_float(widget, color_hex: str):
    shadow = _build_shadow(color_hex, alpha=50, blur=26, offset_x=0, offset_y=6, parent=widget)
    widget.setGraphicsEffect(shadow)
    return shadow


def apply_shadow_glow(widget, color_hex: str):
    shadow = _build_shadow(color_hex, alpha=180, blur=42, offset_x=0, offset_y=0, parent=widget)
    widget.setGraphicsEffect(shadow)
    return shadow

