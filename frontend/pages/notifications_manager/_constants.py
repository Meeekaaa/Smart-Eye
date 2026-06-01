from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QWidget,
)
from frontend.app_theme import page_base_styles


from frontend.styles._colors import (
    _BG_BASE as _BG_BASE,
    _BG_SURFACE,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED as _TEXT_MUTED,
    _ACCENT,
    _ACCENT_HI,
    _ACCENT_HI_BG_03,
)
from frontend.styles._btn_styles import (
    _PRIMARY_BTN as _PRIMARY_BTN,
    _TEXT_BTN_BLUE as _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST as _TEXT_BTN_GHOST,
    _TEXT_BTN_RED as _TEXT_BTN_RED,
    _TEXT_BTN_RED_CONFIRM as _TEXT_BTN_RED_CONFIRM,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_SIZE_TINY,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    RADIUS_5,
    RADIUS_SM,
    RADIUS_XS,
    SIZE_CONTROL_SM,
    SIZE_LABEL_W,
    SIZE_PILL_H,
    SIZE_ROW_52,
    SIZE_SECTION_H,
    SPACE_10,
    SPACE_20,
    SPACE_28,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
)
from frontend.styles._input_styles import _FORM_INPUTS, _FORM_COMBO
from frontend.styles._form_rows import make_labeled_row, make_pill, make_section_divider
from frontend.styles.page_styles import section_kicker_style


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
    margin: {SPACE_XXS}px {SPACE_XS}px;
    border-radius: {RADIUS_XS}px;
}}
QScrollBar::handle:vertical {{
    background: {_ACCENT_HI};
    min-height: {SIZE_CONTROL_SM}px; border-radius: {RADIUS_XS}px;
}}
QScrollBar::handle:vertical:hover {{ background: {_TEXT_PRI}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    border: none;
    background: {_BORDER_DIM};
    height: {SPACE_6}px;
    margin: {SPACE_XXS}px {SPACE_XXS}px;
    border-radius: {RADIUS_XS}px;
}}
QScrollBar::handle:horizontal {{
    background: {_ACCENT_HI}; min-width: {SPACE_28}px; border-radius: {RADIUS_XS}px;
}}
QScrollBar::handle:horizontal:hover {{ background: {_TEXT_PRI}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
QCheckBox {{ color: {_TEXT_PRI}; spacing: {SPACE_SM}px; }}
QCheckBox::indicator {{
    width: {SPACE_LG}px; height: {SPACE_LG}px;
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


def _pill(text: str, fg: str, bg: str) -> QLabel:
    return make_pill(text, SIZE_PILL_H, f"""
        color: {fg};
        background-color: {bg};
        border: none;
        border-radius: {RADIUS_5}px;
        padding: 0 {SPACE_10}px;
        font-size: {FONT_SIZE_MICRO}px;
        font-weight: {FONT_WEIGHT_BOLD};
        letter-spacing: 0.{SPACE_5}px;
    """)


def _combo_ss() -> str:
    return _FORM_COMBO


def _make_sdiv(title: str) -> QFrame:
    return make_section_divider(
        title,
        f"""
        QFrame {{
            background:{_BG_RAISED};
            border-top:{SPACE_XXXS}px solid {_BORDER};
            border-bottom:{SPACE_XXXS}px solid {_BORDER};
        }}
    """,
        (
            f"{section_kicker_style(_TEXT_SEC)} background:transparent;"
        ),
        margins=(SPACE_XL, 0, SPACE_LG, 0),
        fixed_height=SIZE_SECTION_H,
    )


def _srow(label_text: str, widget: QWidget, height: int = SIZE_ROW_52) -> QFrame:
    return make_labeled_row(
        label_text,
        widget,
        height=height,
        frame_style=f"""
        QFrame {{
            background:transparent;
            border:none;
            border-bottom:{SPACE_XXXS}px solid {_BORDER_DIM};
        }}
        QFrame:hover {{ background:{_ACCENT_HI_BG_03}; }}
    """,
        label_style=(
            f"color:{_TEXT_SEC}; font-size:{FONT_SIZE_LABEL}px; font-weight:{FONT_WEIGHT_NORMAL};"
            "background:transparent; border:none;"
        ),
        label_width=SIZE_LABEL_W,
        margins=(SPACE_XL, 0, SPACE_XL, 0),
        spacing=SPACE_20,
    )


def _make_banner(text: str, dot_color: str, bg: str, border: str) -> QFrame:
    fr = QFrame()
    fr.setStyleSheet(f"""
        QFrame {{
            background: {bg};
            border-bottom: {SPACE_XXXS}px solid {border};
            border-top: none; border-left: none; border-right: none;
        }}
    """)
    bi = QHBoxLayout(fr)
    bi.setContentsMargins(SPACE_XL, SPACE_SM, SPACE_XL, SPACE_SM)
    bi.setSpacing(SPACE_SM)
    dot = QLabel("\u25cf")
    dot.setStyleSheet(f"color: {dot_color}; font-size: {FONT_SIZE_TINY}px; background: transparent; border: none;")
    bi.addWidget(dot)
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {dot_color}; font-size: {FONT_SIZE_CAPTION}px; background: transparent; border: none;")
    bi.addWidget(lbl)
    bi.addStretch()
    return fr
