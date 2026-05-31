from frontend.styles._colors import (
    _ACCENT_HI,
    _ACCENT_BORDER,
    _ACCENT_GRAD_END,
    _ACCENT_GRAD_HOVER_END,
    _ACCENT_GRAD_PRESSED_END,
    _ACCENT_TINT,
    _ACCENT_TINT_STRONG,
    _ACCENT_HI_BG_06,
    _BG_OVERLAY,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _BORDER_DARK,
    _DANGER,
    _DANGER_BG_10,
    _DANGER_BG_22,
    _DANGER_BG_32,
    _DANGER_BORDER_45,
    _DANGER_BG_15,
    _DANGER_DIM,
    _DANGER_GRAD_END,
    _DANGER_GRAD_HOVER_END,
    _DANGER_GRAD_PRESSED_END,
    _DANGER_TINT,
    _DANGER_TINT_STRONG,
    _DANGER_TINT_CONFIRM,
    _DANGER_TINT_HOVER,
    _DANGER_TINT_PRESSED,
    _TEXT_ON_ACCENT,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_HEAVY,
    FONT_WEIGHT_NORMAL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_6,
    RADIUS_MD,
    RADIUS_NONE,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_LG,
    SIZE_CONTROL_MD,
    SIZE_CONTROL_SM,
    SIZE_PILL_H,
    SPACE_20,
    SPACE_6,
    SPACE_MD,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
)


_PRIMARY_BTN = (
    "QPushButton {"
    f"    border: {SPACE_XXXS}px solid {_ACCENT_BORDER};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    background-color: {_ACCENT_GRAD_END};"
    f"    color: {_TEXT_ON_ACCENT};"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    font-size: {FONT_SIZE_BODY}px;"
    f"    padding: 0 {SPACE_MD}px;"
    f"    min-height: {SIZE_CONTROL_MD}px;"
    f"    min-width: {SIZE_BTN_W_LG}px;"
    "}"
    "QPushButton:hover {"
    f"    background-color: {_ACCENT_GRAD_HOVER_END};"
    "}"
    "QPushButton:focus {"
    f"    border-color: {_ACCENT_HI};"
    "}"
    "QPushButton:pressed {"
    f"    background-color: {_ACCENT_GRAD_PRESSED_END};"
    "}"
    "QPushButton:disabled {"
    f"    background: {_BORDER_DIM};"
    f"    color: {_TEXT_MUTED};"
    f"    border-color: {_BORDER_DARK};"
    "}"
)

_DANGER_BTN = (
    "QPushButton {"
    f"    border: {SPACE_XXXS}px solid {_DANGER_DIM};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    background-color: {_DANGER_GRAD_END};"
    f"    color: {_TEXT_ON_ACCENT};"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    font-size: {FONT_SIZE_BODY}px;"
    f"    padding: 0 {SPACE_MD}px;"
    f"    min-height: {SIZE_CONTROL_MD}px;"
    f"    min-width: {SIZE_BTN_W_LG}px;"
    "}"
    "QPushButton:hover {"
    f"    background-color: {_DANGER_GRAD_HOVER_END};"
    "}"
    "QPushButton:focus {"
    f"    border-color: {_DANGER};"
    "}"
    "QPushButton:pressed {"
    f"    background-color: {_DANGER_GRAD_PRESSED_END};"
    "}"
    "QPushButton:disabled {"
    f"    background: {_BORDER_DIM};"
    f"    color: {_TEXT_MUTED};"
    f"    border-color: {_BORDER_DARK};"
    "}"
)

_SECONDARY_BTN = (
    "QPushButton {"
    f"    border: {SPACE_XXXS}px solid {_BORDER};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    background-color: {_BG_RAISED};"
    f"    color: {_TEXT_SEC};"
    f"    font-weight: {FONT_WEIGHT_SEMIBOLD};"
    f"    font-size: {FONT_SIZE_BODY}px;"
    f"    padding: 0 {SPACE_MD}px;"
    f"    min-height: {SIZE_CONTROL_MD}px;"
    f"    min-width: {SIZE_BTN_W_LG}px;"
    "}"
    "QPushButton:hover {"
    f"    background-color: {_BG_OVERLAY};"
    f"    color: {_TEXT_PRI};"
    f"    border-color: {_TEXT_SEC};"
    "}"
    "QPushButton:focus {"
    f"    border-color: {_ACCENT_HI};"
    f"    color: {_TEXT_PRI};"
    "}"
    "QPushButton:pressed {"
    f"    background-color: {_BG_OVERLAY};"
    "}"
    "QPushButton:disabled {"
    f"    background: {_BORDER_DIM};"
    f"    color: {_TEXT_MUTED};"
    f"    border-color: {_TEXT_MUTED};"
    "}"
)


_ICON_BTN = (
    "QPushButton {"
    f"    border: {SPACE_XXXS}px solid {_BORDER};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    background-color: {_BG_RAISED};"
    "    padding: 0;"
    "}"
    "QPushButton:hover {"
    f"    background-color: {_BG_OVERLAY};"
    f"    border-color: {_TEXT_MUTED};"
    "}"
    "QPushButton:focus {"
    f"    border-color: {_ACCENT_HI};"
    f"    background-color: {_BG_OVERLAY};"
    "}"
    "QPushButton:pressed {"
    f"    background-color: {_BG_RAISED};"
    f"    border-color: {_TEXT_SEC};"
    "}"
    "QPushButton:disabled {"
    f"    background-color: {_BORDER_DIM};"
    f"    border-color: {_BORDER_DARK};"
    f"    color: {_TEXT_MUTED};"
    "}"
)

_ICON_BTN_DANGER = (
    "QPushButton {"
    f"    border: {SPACE_XXXS}px solid {_DANGER_BORDER_45};"
    f"    border-radius: {RADIUS_MD}px;"
    f"    background-color: {_DANGER_BG_10};"
    f"    color: {_TEXT_ON_ACCENT};"
    "    padding: 0;"
    "}"
    "QPushButton:hover {"
    f"    background-color: {_DANGER_BG_22};"
    f"    border-color: {_DANGER};"
    "}"
    "QPushButton:focus {"
    f"    border-color: {_DANGER};"
    "}"
    "QPushButton:pressed {"
    f"    background-color: {_DANGER_BG_32};"
    "}"
)

_ICON_BTN_GHOST_DANGER = (
    "QPushButton {"
    "    border: none;"
    "    background: transparent;"
    f"    border-radius: {RADIUS_6}px;"
    "}"
    "QPushButton:hover {"
    f"    background: {_DANGER_BG_15};"
    "}"
    "QPushButton:focus {"
    f"    background: {_DANGER_BG_22};"
    "}"
    "QPushButton:pressed {"
    f"    background: {_DANGER_BG_22};"
    "}"
    "QPushButton:disabled {"
    f"    background: {_DANGER_BG_10};"
    f"    color: {_TEXT_MUTED};"
    "}"
)


_TEXT_BTN_BLUE = (
    "QPushButton {"
    "    border: none;"
    "    background: transparent;"
    f"    color: {_ACCENT_HI};"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    font-size: {FONT_SIZE_CAPTION}px;"
    f"    padding: 0 {SPACE_6}px;"
    f"    min-height: {SIZE_CONTROL_SM}px;"
    "}"
    f"QPushButton:hover  {{ color: {_ACCENT_TINT}; }}"
    f"QPushButton:focus {{ color: {_ACCENT_TINT}; }}"
    f"QPushButton:pressed {{ color: {_ACCENT_TINT_STRONG}; }}"
    f"QPushButton:disabled {{ color: {_TEXT_MUTED}; }}"
)

_TEXT_BTN_RED = (
    "QPushButton {"
    "    border: none;"
    "    background: transparent;"
    f"    color: {_DANGER};"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    font-size: {FONT_SIZE_CAPTION}px;"
    f"    padding: 0 {SPACE_6}px;"
    f"    min-height: {SIZE_CONTROL_SM}px;"
    "}"
    f"QPushButton:hover  {{ color: {_DANGER_TINT}; }}"
    f"QPushButton:focus {{ color: {_DANGER_TINT}; }}"
    f"QPushButton:pressed {{ color: {_DANGER_TINT_STRONG}; }}"
    f"QPushButton:disabled {{ color: {_TEXT_MUTED}; }}"
)


_TEXT_BTN_RED_DEFAULT = _TEXT_BTN_RED

_TEXT_BTN_RED_CONFIRM = (
    "QPushButton {"
    "    border: none;"
    "    background: transparent;"
    f"    color: {_DANGER_TINT_CONFIRM};"
    f"    font-weight: {FONT_WEIGHT_HEAVY};"
    f"    font-size: {FONT_SIZE_CAPTION}px;"
    f"    padding: 0 {SPACE_6}px;"
    f"    min-height: {SIZE_CONTROL_SM}px;"
    "}"
    f"QPushButton:hover  {{ color: {_DANGER_TINT_HOVER}; }}"
    f"QPushButton:focus {{ color: {_DANGER_TINT_HOVER}; }}"
    f"QPushButton:pressed {{ color: {_DANGER_TINT_PRESSED}; }}"
    f"QPushButton:disabled {{ color: {_TEXT_MUTED}; }}"
)

_TEXT_BTN_GHOST = (
    "QPushButton {"
    "    border: none;"
    "    background: transparent;"
    f"    color: {_TEXT_SEC};"
    f"    font-size: {FONT_SIZE_CAPTION}px;"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    padding: 0 {SPACE_MD}px;"
    f"    border-radius: {RADIUS_MD}px;"
    "}"
    f"QPushButton:hover  {{ color: {_ACCENT_TINT}; }}"
    f"QPushButton:focus {{ color: {_ACCENT_TINT}; }}"
    f"QPushButton:pressed {{ color: {_ACCENT_TINT_STRONG}; }}"
    f"QPushButton:disabled {{ color: {_TEXT_MUTED}; }}"
)


_TAB_BTN = (
    "QPushButton {"
    "    border: none;"
    f"    border-bottom: {SPACE_XXS}px solid transparent;"
    f"    border-radius: {RADIUS_NONE}px;"
    "    background: transparent;"
    f"    color: {_TEXT_SEC};"
    f"    font-size: {FONT_SIZE_BODY}px;"
    f"    font-weight: {FONT_WEIGHT_NORMAL};"
    f"    padding: 0 {SPACE_20}px;"
    f"    min-height: {SIZE_CONTROL_LG}px;"
    f"    max-height: {SIZE_CONTROL_LG}px;"
    "}"
    "QPushButton:hover {"
    f"    color: {_TEXT_PRI};"
    f"    background: {_ACCENT_HI_BG_06};"
    "}"
    "QPushButton:focus {"
    f"    color: {_TEXT_PRI};"
    f"    background: {_ACCENT_HI_BG_06};"
    "}"
)

_TAB_BTN_ACTIVE = (
    "QPushButton {"
    "    border: none;"
    f"    border-bottom: {SPACE_XXS}px solid {_ACCENT_HI};"
    f"    border-radius: {RADIUS_NONE}px;"
    "    background: transparent;"
    f"    color: {_ACCENT_HI};"
    f"    font-size: {FONT_SIZE_BODY}px;"
    f"    font-weight: {FONT_WEIGHT_BOLD};"
    f"    padding: 0 {SPACE_20}px;"
    f"    min-height: {SIZE_CONTROL_LG}px;"
    f"    max-height: {SIZE_CONTROL_LG}px;"
    "}"
)

_SEGMENT_TAB_BAR = (
    f"QWidget#TabBar {{    background: {_BG_RAISED};    border: {SPACE_XXXS}px solid {_BORDER_DIM};    border-radius: {RADIUS_MD}px;}}"
)

_SEGMENT_TAB_BTN = (
    "QPushButton#Tab {"
    "    background: transparent;"
    "    border: none;"
    f"    border-radius: {RADIUS_6}px;"
    f"    color: {_TEXT_MUTED};"
    f"    font-size: {FONT_SIZE_CAPTION}px;"
    f"    font-weight: {FONT_WEIGHT_SEMIBOLD};"
    f"    min-height: {SIZE_PILL_H}px;"
    f"    padding: 0 {SPACE_XS}px;"
    "}"
    "QPushButton#Tab:hover {"
    f"    color: {_TEXT_SEC};"
    "}"
    "QPushButton#Tab:focus {"
    f"    color: {_TEXT_SEC};"
    "}"
    "QPushButton#Tab:checked {"
    f"    background: {_BG_OVERLAY};"
    f"    border: {SPACE_XXXS}px solid {_BORDER};"
    f"    color: {_TEXT_PRI};"
    "}"
)
