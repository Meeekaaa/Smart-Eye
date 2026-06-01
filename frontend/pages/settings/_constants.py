from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)
from frontend.app_theme import page_base_styles

from frontend.styles.page_styles import section_kicker_style
from frontend.styles._colors import (
    _ACCENT as _ACCENT,
    _BG_SURFACE as _BG_SURFACE,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI as _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED,
    _ACCENT_HI_BG_28,
    _ACCENT_HI_BG_55,
)
from frontend.styles._btn_styles import (
    _DANGER_BTN as _DANGER_BTN,
    _PRIMARY_BTN as _PRIMARY_BTN,
    _SECONDARY_BTN as _SECONDARY_BTN,
    _TAB_BTN as _TAB_BTN,
    _TAB_BTN_ACTIVE as _TAB_BTN_ACTIVE,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_LABEL,
    FONT_SIZE_CAPTION,
    FONT_WEIGHT_NORMAL,
    RADIUS_3,
    RADIUS_NONE,
    SIZE_CONTROL_LG,
    SIZE_CONTROL_MD,
    SIZE_CONTROL_SM,
    SIZE_LABEL_W_180,
    SIZE_ROW_54,
    SIZE_ROW_LG,
    SPACE_3,
    SPACE_6,
    SPACE_20,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XXS,
    SPACE_XXXS,
)
from frontend.styles._input_styles import _FORM_INPUTS, _FORM_COMBO


_BTN_H = SIZE_CONTROL_MD
_BTN_H_SM = SIZE_CONTROL_SM
_FIELD_H = SIZE_CONTROL_MD
_ROW_H = SIZE_ROW_54
_ROW_H_TALL = SIZE_ROW_LG
_LABEL_W = SIZE_LABEL_W_180
_TAB_BAR_H = SIZE_CONTROL_LG


_STYLESHEET = (
    page_base_styles(FONT_SIZE_BODY)
    + f"""
{_FORM_INPUTS}
{_FORM_COMBO}
QScrollArea {{ border: none; background-color: transparent; }}
QScrollBar:vertical {{
    border: none; background: transparent; width: {SPACE_SM}px; margin: {SPACE_XXS}px {SPACE_XXXS}px;
}}
QScrollBar::handle:vertical {{
    background: {_ACCENT_HI_BG_28}; min-height: {SIZE_CONTROL_SM}px; border-radius: {RADIUS_3}px;
}}
QScrollBar::handle:vertical:hover {{ background: {_ACCENT_HI_BG_55}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLabel {{ background: transparent; }}
"""
)


def _combo_ss() -> str:
    return _FORM_COMBO


def _make_separator() -> QFrame:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"background-color: {_BORDER}; border: none; max-height: {SPACE_XXXS}px; margin: 0;")
    return sep


def _make_sdiv(title: str, action_widget: QWidget | None = None) -> QFrame:
    fr = QFrame()
    fr.setStyleSheet(f"QFrame {{ background: {_BG_RAISED}; border: {SPACE_XXXS}px solid {_BORDER}; border-radius: {RADIUS_NONE}px; }}")
    row = QHBoxLayout(fr)
    row.setContentsMargins(SPACE_LG, SPACE_6, SPACE_MD, SPACE_6)
    lbl = QLabel(title.upper())
    lbl.setStyleSheet(f"{section_kicker_style(_TEXT_SEC)} background: transparent; border: none;")
    row.addWidget(lbl)
    row.addStretch()
    if action_widget is not None:
        row.addWidget(action_widget)
    return fr


def _srow(
    label_text: str,
    widget: QWidget,
    hint: str = "",
    height: int = 0,
) -> QFrame:
    h = height or (_ROW_H_TALL if hint else _ROW_H)
    fr = QFrame()
    fr.setMinimumHeight(h)
    fr.setStyleSheet(f"background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};")

    outer = QHBoxLayout(fr)
    outer.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
    outer.setSpacing(SPACE_LG)

    lb = QLabel(label_text)
    lb.setFixedWidth(_LABEL_W)
    lb.setAlignment(Qt.AlignmentFlag.AlignVCenter)
    lb.setStyleSheet(
        f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL}; background: transparent; border: none;"
    )
    outer.addWidget(lb)

    fr.setStyleSheet(f"QFrame {{ background: transparent; border: none; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM}; }}")

    if hint:
        from PySide6.QtWidgets import QVBoxLayout

        col = QWidget()
        col.setStyleSheet("background:transparent; border:none;")
        vl = QVBoxLayout(col)
        vl.setContentsMargins(0, SPACE_SM, 0, SPACE_SM)
        vl.setSpacing(SPACE_3)
        vl.addWidget(widget)
        hl = QLabel(hint)
        hl.setWordWrap(True)
        hl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; background: transparent; border: none;")
        vl.addWidget(hl)
        outer.addWidget(col, stretch=1)
    else:
        outer.addWidget(widget, stretch=1)

    return fr
