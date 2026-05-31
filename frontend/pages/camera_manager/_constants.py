from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QWidget,
)
from frontend.app_theme import page_base_styles


from frontend.styles._colors import (
    _BG_BASE as _BG_BASE,
    _BG_SURFACE,
    _BG_RAISED,
    _BG_OVERLAY,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED,
    _ACCENT,
    _ACCENT_HI,
    _ACCENT_HI_BG_03,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    RADIUS_XS,
    SIZE_BTN_W_XS,
    SIZE_ICON_TINY,
    SIZE_ITEM_SM,
    SIZE_LABEL_W_LG,
    SIZE_PILL_H,
    SIZE_ROW_52,
    SPACE_10,
    SPACE_20,
    SPACE_28,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXL,
    SPACE_XXS,
    SPACE_XXXS,
)
from frontend.styles._input_styles import _FORM_INPUTS, _FORM_COMBO
from frontend.styles._btn_styles import (
    _PRIMARY_BTN as _PRIMARY_BTN,
    _TEXT_BTN_BLUE as _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST as _TEXT_BTN_GHOST,
    _TEXT_BTN_RED as _TEXT_BTN_RED,
    _TEXT_BTN_RED_CONFIRM as _TEXT_BTN_RED_CONFIRM,
)
from frontend.styles._form_rows import make_labeled_row, make_pill, make_section_divider, make_separator
from frontend.styles.page_styles import section_kicker_style

_ACTION_BTN_W = SIZE_BTN_W_XS
_ACTION_BTN_H = SIZE_ITEM_SM


_STYLESHEET = (
    page_base_styles(FONT_SIZE_BODY)
    + f"""
QPushButton {{
    background-color: {_BG_OVERLAY};
    border: {SPACE_XXXS}px solid {_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 0 {SPACE_LG}px;
    color: {_TEXT_PRI};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    min-height: {SPACE_XXL}px;
}}
QPushButton:hover {{ background-color: {_BORDER}; border-color: {_TEXT_SEC}; }}
QPushButton:disabled {{ color: {_TEXT_MUTED}; border-color: {_TEXT_MUTED}; background-color: {_BG_RAISED}; }}
QPushButton[class="secondary"] {{
    background-color: transparent; border: {SPACE_XXXS}px solid {_BORDER}; color: {_TEXT_SEC};
}}
QPushButton[class="secondary"]:hover {{ background-color: {_BG_OVERLAY}; color: {_TEXT_PRI}; }}
{_FORM_INPUTS}
{_FORM_COMBO}
QScrollArea {{ border: none; background-color: transparent; }}
QScrollBar:vertical {{
    border: none;
    background: {_BORDER_DIM};
    width: {SPACE_6}px;
    margin: {SPACE_XXS}px {SPACE_XS}px;
    border-radius: {RADIUS_XS}px;
}}
QScrollBar::handle:vertical {{
    background: {_ACCENT_HI}; min-height: {SPACE_28}px; border-radius: {RADIUS_XS}px;
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


def _make_separator() -> QFrame:
    return make_separator(f"background-color: {_BORDER}; border: none; max-height: {SPACE_XXXS}px; margin: {SPACE_XXS}px 0;")


def _pill(text: str, fg: str, bg: str) -> QLabel:
    return make_pill(text, SIZE_PILL_H, f"""
        color: {fg};
        background-color: {bg};
        border: none;
        border-radius: {RADIUS_LG}px;
        padding: 0 {SPACE_10}px;
        font-size: {FONT_SIZE_MICRO}px;
        font-weight: {FONT_WEIGHT_BOLD};
        letter-spacing: 0.{SPACE_5}px;
    """)


def _make_sdiv(title: str) -> QFrame:
    return make_section_divider(
        title,
        (
            f"QFrame {{ background: {_BG_RAISED}; border-top: {SPACE_XXXS}px solid {_BORDER};"
            f" border-bottom: {SPACE_XXXS}px solid {_BORDER}; border-left: none; border-right: none; }}"
        ),
        (
            f"{section_kicker_style(_TEXT_SEC)} background: transparent; border: none;"
        ),
        margins=(SPACE_LG, SPACE_6, SPACE_MD, SPACE_6),
        expanding=True,
    )


def _srow(label_text: str, widget: QWidget, height: int = SIZE_ROW_52) -> QFrame:
    return make_labeled_row(
        label_text,
        widget,
        height=height,
        frame_style=f"""
        QFrame {{
            background: transparent;
            border: none;
            border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
        }}
        QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}
    """,
        label_style=(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL};"
            "background: transparent; border: none;"
        ),
        label_width=SIZE_LABEL_W_LG,
        margins=(SPACE_XL, 0, SPACE_XL, 0),
        spacing=SPACE_20,
    )


def _combo_ss() -> str:
    return _FORM_COMBO


def _spin_ss() -> str:
    return _FORM_INPUTS


def _input_ss(radius: int = RADIUS_MD) -> str:
    return _FORM_INPUTS
