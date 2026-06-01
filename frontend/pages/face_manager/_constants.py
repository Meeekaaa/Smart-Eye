from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from frontend.app_theme import page_base_styles


from frontend.styles._colors import (
    _BG_BASE as _BG_BASE,
    _BG_OVERLAY as _BG_OVERLAY,
    _BG_SURFACE,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED as _TEXT_MUTED,
    _ACCENT,
    _ACCENT_HI,
    _DANGER as _DANGER,
    _SUCCESS as _SUCCESS,
    _SUCCESS_DIM as _SUCCESS_DIM,
    _AVATAR_BG_1,
    _AVATAR_BG_2,
    _AVATAR_BG_3,
    _AVATAR_BG_4,
    _AVATAR_BG_5,
    _AVATAR_BG_6,
    _AVATAR_BG_7,
    _AVATAR_BG_8,
    _AVATAR_BG_9,
    _AVATAR_BG_10,
    _AVATAR_BG_11,
    _AVATAR_BG_12,
    _AVATAR_FG_1,
    _AVATAR_FG_2,
    _AVATAR_FG_3,
    _AVATAR_FG_4,
    _AVATAR_FG_5,
    _AVATAR_FG_6,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_LABEL,
    FONT_WEIGHT_NORMAL,
    RADIUS_SM,
    SIZE_CONTROL_SM,
    SIZE_ICON_TINY,
    SPACE_SM,
    SPACE_XXXS,
)
from frontend.styles._input_styles import _FORM_INPUTS, _FORM_COMBO
from frontend.styles._btn_styles import (
    _DANGER_BTN as _DANGER_BTN,
    _PRIMARY_BTN as _PRIMARY_BTN,
    _TEXT_BTN_BLUE as _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST as _TEXT_BTN_GHOST,
    _TEXT_BTN_RED as _TEXT_BTN_RED,
    _TEXT_BTN_RED_CONFIRM as _TEXT_BTN_RED_CONFIRM,
    _TEXT_BTN_RED_DEFAULT as _TEXT_BTN_RED_DEFAULT,
)

_AVATAR_BG_COLORS = [
    (_AVATAR_BG_1, _AVATAR_BG_2),
    (_AVATAR_BG_3, _AVATAR_BG_4),
    (_AVATAR_BG_5, _AVATAR_BG_6),
    (_AVATAR_BG_7, _AVATAR_BG_8),
    (_AVATAR_BG_9, _AVATAR_BG_10),
    (_AVATAR_BG_11, _AVATAR_BG_12),
]

_AVATAR_FG_COLORS = [
    _AVATAR_FG_1,
    _AVATAR_FG_2,
    _AVATAR_FG_3,
    _AVATAR_FG_4,
    _AVATAR_FG_5,
    _AVATAR_FG_6,
]


_STYLESHEET = (
    page_base_styles(FONT_SIZE_BODY)
    + f"""
{_FORM_INPUTS}
{_FORM_COMBO}
QScrollArea {{ border: none; background-color: transparent; }}
QScrollBar:vertical {{
    border: none;
    background: {_BORDER_DIM};
    width: {SPACE_SM}px;
    margin: 0;
    border-radius: {RADIUS_SM}px;
}}
QScrollBar::handle:vertical {{
    background: {_ACCENT_HI}; min-height: {SIZE_CONTROL_SM}px; border-radius: {RADIUS_SM}px;
}}
QScrollBar::handle:vertical:hover {{ background: {_TEXT_PRI}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QCheckBox {{ color: {_TEXT_PRI}; spacing: {SPACE_SM}px; }}
QCheckBox::indicator {{
    width: {SIZE_ICON_TINY}px; height: {SIZE_ICON_TINY}px;
    border: {SPACE_XXXS}px solid {_BORDER};
    border-radius: {RADIUS_SM}px;
    background-color: {_BG_RAISED};
    image: none;
}}
QCheckBox::indicator:checked {{
    background-color: {_ACCENT}; border-color: {_ACCENT};
    image: url(frontend/assets/icons/checkmark.png);
}}
QCheckBox::indicator:hover {{ border-color: {_ACCENT_HI}; }}
QLabel {{ background: transparent; }}
QFormLayout QLabel {{ color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL}; }}
QDialog {{ background-color: {_BG_SURFACE}; }}
"""
)


def _split_name_parts(full_name: str) -> tuple[str, str, str, str]:
    parts = [p for p in (full_name or "").strip().split() if p]
    first = parts[0] if len(parts) > 0 else ""
    second = parts[1] if len(parts) > 1 else ""
    third = parts[2] if len(parts) > 2 else ""
    last = " ".join(parts[3:]) if len(parts) > 3 else ""
    return first, second, third, last


def _compose_name(first: str, second: str, third: str = "", last: str = "") -> str:
    return " ".join([p.strip() for p in [first, second, third, last] if p and p.strip()])


def _short_display_name(full_name: str) -> str:
    first, second, _t, _l = _split_name_parts(full_name)
    short = " ".join([p for p in [first, second] if p])
    return short if short else (full_name or "Unknown")


def _make_rounded_pixmap(photo_path: str, size: int, radius: int):
    if not photo_path:
        return None

    resolved = photo_path if os.path.isabs(photo_path) else os.path.abspath(photo_path)
    if not os.path.isfile(resolved):
        return None
    pix = QPixmap(resolved)
    if pix.isNull():
        return None
    pix = pix.scaled(
        size,
        size,
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    pix = pix.copy((pix.width() - size) // 2, (pix.height() - size) // 2, size, size)
    rounded = QPixmap(size, size)
    rounded.fill(Qt.GlobalColor.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, radius, radius)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, pix)
    painter.end()
    return rounded
