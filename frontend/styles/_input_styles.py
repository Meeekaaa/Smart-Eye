from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_HI_BG_12,
    _ACCENT_HI_BG_22,
    _BG_BASE,
    _BG_OVERLAY,
    _BG_SURFACE,
    _BORDER,
    _BORDER_DARK,
    _TEXT_MUTED,
    _TEXT_PRI,
)
from frontend.icon_theme import themed_icon_path
from frontend.ui_tokens import (
    FONT_SIZE_15,
    FONT_SIZE_BODY,
    FONT_SIZE_LABEL,
    FONT_SIZE_SUBHEAD,
    FONT_WEIGHT_BOLD,
    RADIUS_9,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_NONE,
    SIZE_CONTROL_22,
    SIZE_CONTROL_XS,
    SIZE_ICON_10,
    SIZE_ICON_12,
    SIZE_ITEM_SM,
    SPACE_10,
    SPACE_6,
    SPACE_LG,
    SPACE_SM,
    SPACE_XXXS,
)


_SEARCH_INPUT = (
    "QLineEdit {"
    f"    background-color: {_BG_BASE};"
    "    border: none;"
    f"    border-radius: {RADIUS_9}px;"
    f"    padding: 0 {SPACE_10}px;"
    f"    color: {_TEXT_PRI};"
    f"    font-size: {FONT_SIZE_LABEL}px;"
    "}"
    f"QLineEdit:focus {{ background: {_BG_OVERLAY}; }}"
)

_FORM_INPUTS = (
    "QLineEdit, QTextEdit, QPlainTextEdit, QDateEdit {"
    f"    background-color: {_BG_BASE};"
    f"    border: {SPACE_XXXS}px solid {_BORDER_DARK};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    padding: {SPACE_6}px {SPACE_10}px;"
    f"    color: {_TEXT_PRI};"
    f"    min-height: {SIZE_CONTROL_22}px;"
    "}"
    "QLineEdit:hover, QTextEdit:hover, QPlainTextEdit:hover, QDateEdit:hover {"
    f"    border-color: {_ACCENT_HI_BG_22};"
    "}"
    "QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QDateEdit:focus {"
    f"    background-color: {_BG_SURFACE};"
    f"    border-color: {_ACCENT};"
    "}"
    "QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled, QDateEdit:disabled {"
    f"    color: {_TEXT_MUTED};"
    "}"
    "QLineEdit:read-only, QTextEdit:read-only, QPlainTextEdit:read-only {"
    f"    background-color: {_BG_BASE};"
    f"    border-color: {_BORDER};"
    "}"
    "QSpinBox, QDoubleSpinBox {"
    f"    background-color: {_BG_BASE};"
    f"    border: {SPACE_XXXS}px solid {_BORDER_DARK};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    padding: 0 {SPACE_10}px;"
    f"    color: {_TEXT_PRI};"
    f"    min-height: {SIZE_CONTROL_22}px;"
    "}"
    "QSpinBox:focus, QDoubleSpinBox:focus {"
    f"    border-color: {_ACCENT};"
    "}"
    "QSpinBox::up-button, QSpinBox::down-button, "
    "QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {"
    f"    background: transparent; border: none; width: {SIZE_CONTROL_XS}px;"
    "}"
    "QSpinBox::up-button:hover, QSpinBox::down-button:hover, "
    "QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {"
    f"    background: {_ACCENT_HI_BG_12};"
    "}"
    f"QSpinBox::up-arrow {{ image: url({themed_icon_path('frontend/assets/icons/arrow_up.png')}); width: {SIZE_ICON_10}px; height: {SIZE_ICON_10}px; }}"
    f"QSpinBox::down-arrow {{ image: url({themed_icon_path('frontend/assets/icons/arrow_down.png')}); width: {SIZE_ICON_10}px; height: {SIZE_ICON_10}px; }}"
    f"QDoubleSpinBox::up-arrow {{ image: url({themed_icon_path('frontend/assets/icons/arrow_up.png')}); width: {SIZE_ICON_10}px; height: {SIZE_ICON_10}px; }}"
    f"QDoubleSpinBox::down-arrow {{ image: url({themed_icon_path('frontend/assets/icons/arrow_down.png')}); width: {SIZE_ICON_10}px; height: {SIZE_ICON_10}px; }}"
)

_FORM_COMBO = (
    "QComboBox {"
    f"    background-color: {_BG_BASE};"
    f"    border: {SPACE_XXXS}px solid {_BORDER_DARK};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    padding: 0 {SPACE_10}px 0 {SPACE_10}px;"
    f"    color: {_TEXT_PRI};"
    f"    min-height: {SIZE_CONTROL_22}px;"
    "    combobox-popup: 0;"
    "}"
    "QComboBox:hover {"
    f"    border-color: {_ACCENT_HI_BG_22};"
    "}"
    "QComboBox:focus {"
    f"    border-color: {_ACCENT};"
    "}"
    "QComboBox:disabled {"
    f"    color: {_TEXT_MUTED};"
    "}"
    f"QComboBox::drop-down {{ width: {SIZE_CONTROL_XS}px; background: transparent;"
    f" border: none; border-left: {SPACE_XXXS}px solid {_BORDER_DARK};"
    f" border-top-right-radius: {RADIUS_MD}px; border-bottom-right-radius: {RADIUS_MD}px; margin-right: {SPACE_XXXS}px; }}"
    f"QComboBox::down-arrow {{ image: url({themed_icon_path('frontend/assets/icons/arrow_down.png')}); width: {SIZE_ICON_12}px; height: {SIZE_ICON_12}px; }}"
    "QComboBox QAbstractItemView {"
    f"    background-color: {_BG_SURFACE};"
    f"    border: {SPACE_XXXS}px solid {_BORDER_DARK};"
    f"    border-radius: {RADIUS_NONE}px;"
    f"    selection-background-color: {_ACCENT_HI_BG_12};"
    f"    selection-color: {_TEXT_PRI};"
    "    outline: none;"
    f"    color: {_TEXT_PRI};"
    "    padding: 0;"
    "    margin: 0;"
    "}"
    "QComboBox QListView {"
    f"    border-radius: {RADIUS_NONE}px;"
    "}"
    "QComboBox QAbstractItemView::viewport {"
    f"    border-radius: {RADIUS_NONE}px;"
    "}"
    "QComboBox QAbstractItemView::item {"
    f"    padding: {SPACE_6}px {SPACE_10}px;"
    f"    border-radius: {RADIUS_NONE}px;"
    f"    min-height: {SIZE_ITEM_SM}px;"
    "}"
    "QComboBox QAbstractItemView::item:selected {"
    f"    background-color: {_ACCENT_HI_BG_12};"
    f"    border-radius: {RADIUS_NONE}px;"
    "}"
    "QComboBox QAbstractItemView::item:hover {"
    f"    background-color: {_ACCENT_HI_BG_12};"
    f"    border-radius: {RADIUS_NONE}px;"
    "}"
)

_AUTH_INPUT_LG = (
    "QLineEdit {"
    f"    background: {_BG_OVERLAY};"
    "    border: none;"
    f"    border-radius: {RADIUS_LG}px;"
    f"    padding: 0 {SPACE_LG}px;"
    f"    color: {_TEXT_PRI};"
    f"    font-size: {FONT_SIZE_SUBHEAD}px;"
    "}"
    f"QLineEdit:focus {{ background-color: {_BG_OVERLAY}; }}"
)

_AUTH_INPUT_MD = (
    "QLineEdit {"
    f"    background: {_BG_OVERLAY};"
    "    border: none;"
    f"    border-radius: {RADIUS_MD}px;"
    f"    padding: 0 {SPACE_10}px;"
    f"    color: {_TEXT_PRI};"
    f"    font-size: {FONT_SIZE_BODY}px;"
    "}"
    f"QLineEdit:focus {{ background-color: {_BG_OVERLAY}; }}"
)

_FORM_INPUT_TITLE = (
    "QLineEdit {"
    f"    background: {_BG_OVERLAY};"
    f"    border: {SPACE_XXXS}px solid {_BORDER_DARK};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    color: {_TEXT_PRI};"
    f"    font-size: {FONT_SIZE_15}px;"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    padding: {SPACE_SM}px {SPACE_10}px;"
    "}"
    f"QLineEdit:focus {{ background: {_BG_OVERLAY}; border-color: {_ACCENT}; }}"
)
