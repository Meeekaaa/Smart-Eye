from __future__ import annotations

from frontend.styles._colors import (
    _ACCENT_BORDER,
    _ACCENT_BG_12,
    _ACCENT_BG_15,
    _ACCENT_BG_18,
    _ACCENT_BG_30,
    _ACCENT_GRAD_END,
    _ACCENT_GRAD_HOVER_END,
    _ACCENT_GRAD_PRESSED_END,
    _ACCENT_GRAD_START,
    _ACCENT_HI,
    _ACCENT_HI_BG_06,
    _ACCENT_HI_BG_12,
    _ACCENT_SUB,
    _BG_BASE,
    _BG_CHECK,
    _BG_DARKEST,
    _BG_OVERLAY,
    _BG_RAISED,
    _BG_SIDEBAR_END,
    _BG_SURFACE,
    _BORDER,
    _BORDER_DARK,
    _BORDER_DIM,
    _DANGER_DIM,
    _DANGER_GRAD_END,
    _DANGER_GRAD_HOVER_END,
    _DANGER_GRAD_PRESSED_END,
    _TEXT_DIM,
    _TEXT_MUTED,
    _TEXT_ON_ACCENT,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_SOFT,
    _WHITE_02,
    _WHITE_03,
)
from frontend.icon_theme import themed_icon_path
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_LARGE,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_3,
    RADIUS_6,
    RADIUS_9,
    RADIUS_MD,
    RADIUS_NONE,
    RADIUS_SM,
    SIZE_CONTROL_18,
    SIZE_CONTROL_38,
    SIZE_CONTROL_MD,
    SIZE_ICON_10,
    SIZE_ICON_12,
    SIZE_ICON_TINY,
    SIZE_ITEM_SM,
    SIZE_SECTION_H,
    SPACE_10,
    SPACE_18,
    SPACE_20,
    SPACE_22,
    SPACE_28,
    SPACE_3,
    SPACE_34,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
)


def _base_styles() -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {_BG_SURFACE};
    color: {_TEXT_PRI};
    font-family: 'Segoe UI Variable', 'Segoe UI', 'Bahnschrift', 'Tahoma', sans-serif;
    font-size: {FONT_SIZE_BODY}px;
}}

QLabel {{
    color: {_TEXT_PRI};
    background: transparent;
    text-decoration: none;
}}
QPushButton, QToolButton, QCheckBox, QRadioButton {{
    text-decoration: none;
}}
"""


def _button_styles() -> str:
    return f"""
QPushButton {{
    background: {_ACCENT_GRAD_END};
    color: {_TEXT_ON_ACCENT};
    border: {SPACE_XXXS}px solid {_ACCENT_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: 0 {SPACE_20}px;
    font-weight: {FONT_WEIGHT_BOLD};
    font-size: {FONT_SIZE_BODY}px;
    min-height: {SIZE_CONTROL_MD}px;
}}
QPushButton:hover {{
    background: {_ACCENT_GRAD_HOVER_END};
    border-color: {_ACCENT_SUB};
}}
QPushButton:pressed {{
    background: {_ACCENT_GRAD_PRESSED_END};
    border-color: {_ACCENT_GRAD_END};
}}
QPushButton:disabled {{
    background: {_BORDER_DIM};
    color: {_TEXT_MUTED};
    border-color: {_BORDER_DARK};
}}

QPushButton[class="danger"] {{
    background: {_DANGER_GRAD_END};
    border: {SPACE_XXXS}px solid {_DANGER_DIM};
    color: {_TEXT_ON_ACCENT};
}}
QPushButton[class="danger"]:hover {{
    background: {_DANGER_GRAD_HOVER_END};
}}
QPushButton[class="danger"]:pressed {{
    background: {_DANGER_GRAD_PRESSED_END};
}}

QPushButton[class="secondary"] {{
    background: transparent;
    color: {_TEXT_SEC};
    border: {SPACE_XXXS}px solid {_BORDER};
}}
QPushButton[class="secondary"]:hover {{
    background: {_BG_OVERLAY};
    border-color: {_TEXT_SEC};
    color: {_TEXT_PRI};
}}
QPushButton[class="secondary"]:pressed {{
    background: {_BG_RAISED};
}}
"""


def _input_styles() -> str:
    return f"""
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_NONE}px;
    padding: {SPACE_SM}px {SPACE_MD}px;
    color: {_TEXT_PRI};
    font-size: {FONT_SIZE_BODY}px;
    selection-background-color: {_ACCENT_BG_30};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    background-color: transparent;
}}
QLineEdit:hover, QTextEdit:hover {{
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled,
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {_TEXT_MUTED};
    background-color: transparent;
}}
"""


def _spin_combo_styles() -> str:
    arrow_up = themed_icon_path("frontend/assets/icons/arrow_up.png")
    arrow_down = themed_icon_path("frontend/assets/icons/arrow_down.png")
    return f"""
QSpinBox, QDoubleSpinBox {{
    background-color: transparent;
    border: none;
    border-radius: {RADIUS_NONE}px;
    padding: {SPACE_6}px {SPACE_MD}px;
    color: {_TEXT_PRI};
    font-size: {FONT_SIZE_BODY}px;
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    background-color: transparent;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    background: transparent;
    border: none;
    width: {SPACE_20}px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    background: transparent;
    border: none;
    width: {SPACE_20}px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {_ACCENT_HI_BG_12};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({arrow_up});
    width: {SIZE_ICON_10}px; height: {SIZE_ICON_10}px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({arrow_down});
    width: {SIZE_ICON_10}px; height: {SIZE_ICON_10}px;
}}

QComboBox {{
    background-color: {_BG_BASE};
    border: {SPACE_XXXS}px solid {_BORDER_DARK};
    border-radius: {RADIUS_MD}px;
    padding: {SPACE_6}px {SPACE_34}px {SPACE_6}px {SPACE_MD}px;
    color: {_TEXT_PRI};
    min-height: {SIZE_SECTION_H}px;
    combobox-popup: 0;
}}
QComboBox:hover {{ border-color: {_ACCENT_HI_BG_12}; }}
QComboBox:focus {{ border-color: {_ACCENT_HI}; }}
QComboBox::drop-down {{
    border: none;
    border-left: {SPACE_XXXS}px solid {_BORDER_DARK};
    background: transparent;
    width: {SPACE_20}px;
    border-top-right-radius: {RADIUS_MD}px;
    border-bottom-right-radius: {RADIUS_MD}px;
}}
QComboBox::down-arrow {{
    image: url({arrow_down});
    width: {SIZE_ICON_12}px;
    height: {SIZE_ICON_12}px;
}}
QComboBox QAbstractItemView {{
    background-color: {_BG_SURFACE};
    border: {SPACE_XXXS}px solid {_BORDER_DARK};
    border-radius: {RADIUS_NONE}px;
    color: {_TEXT_PRI};
    selection-background-color: {_ACCENT_HI_BG_12};
    selection-color: {_TEXT_PRI};
    padding: 0;
    margin: 0;
    outline: none;
}}
QComboBox QListView {{
    border-radius: {RADIUS_NONE}px;
}}
QComboBox QAbstractItemView::viewport {{
    border-radius: {RADIUS_NONE}px;
}}
QComboBox QAbstractItemView::item {{
    padding: {SPACE_6}px {SPACE_MD}px;
    border-radius: {RADIUS_NONE}px;
    min-height: {SIZE_ITEM_SM}px;
}}
QComboBox QAbstractItemView::item:selected {{
    background: {_ACCENT_HI_BG_12};
    border-radius: {RADIUS_NONE}px;
}}
QComboBox QAbstractItemView::item:hover {{
    background: {_ACCENT_HI_BG_12};
    border-radius: {RADIUS_NONE}px;
}}
"""


def _slider_styles() -> str:
    return f"""
QSlider::groove:horizontal {{
    background: {_BORDER_DIM};
    height: {SPACE_6}px;
    border-radius: {RADIUS_3}px;
}}
QSlider::handle:horizontal {{
    background: {_ACCENT_GRAD_END};
    border: {SPACE_XXS}px solid {_ACCENT_GRAD_END};
    width: {SIZE_CONTROL_18}px;
    height: {SIZE_CONTROL_18}px;
    margin: -{SPACE_6}px 0;
    border-radius: {RADIUS_9}px;
}}
QSlider::sub-page:horizontal {{
    background: {_ACCENT_GRAD_END};
    border-radius: {RADIUS_3}px;
}}
"""


def _checkbox_styles() -> str:
    checkmark = themed_icon_path("frontend/assets/icons/checkmark.png")
    return f"""
QCheckBox {{
    spacing: {SPACE_SM}px;
    color: {_TEXT_PRI};
}}
QCheckBox::indicator {{
    width: {SIZE_ICON_TINY}px;
    height: {SIZE_ICON_TINY}px;
    border-radius: {RADIUS_SM}px;
    border: {SPACE_XXXS}px solid {_BORDER};
    background: {_BG_CHECK};
    image: none;
}}
QCheckBox::indicator:hover {{ border-color: {_TEXT_DIM}; }}
QCheckBox::indicator:checked {{
    background: {_ACCENT_GRAD_START};
    border-color: {_ACCENT_GRAD_END};
    image: url({checkmark});
}}
"""


def _tab_styles() -> str:
    return f"""
QTabWidget::pane {{
    background-color: {_BG_SURFACE};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-radius: {RADIUS_MD}px;
    top: -{SPACE_XXXS}px;
}}
QTabBar {{
    background: transparent;
}}
QTabBar::tab {{
    background: transparent;
    color: {_TEXT_DIM};
    border: none;
    padding: {SPACE_10}px {SPACE_22}px;
    margin-right: {SPACE_XS}px;
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    font-size: {FONT_SIZE_BODY}px;
}}
QTabBar::tab:selected {{
    color: {_ACCENT_HI};
    background: {_ACCENT_BG_12};
    border-radius: {RADIUS_6}px;
}}
QTabBar::tab:hover:!selected {{
    color: {_TEXT_SEC};
    background: {_ACCENT_HI_BG_06};
    border-radius: {RADIUS_6}px;
}}
"""


def _table_styles() -> str:
    return f"""
QTableWidget, QTableView {{
    background-color: {_BG_SURFACE};
    alternate-background-color: {_BG_SIDEBAR_END};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-radius: {RADIUS_MD}px;
    gridline-color: {_BG_OVERLAY};
    color: {_TEXT_PRI};
    selection-background-color: {_ACCENT_BG_12};
    selection-color: {_TEXT_PRI};
    outline: none;
}}
QTableWidget::item, QTableView::item {{
    padding: {SPACE_10}px {SPACE_SM}px;
    border: none;
    background: transparent;
}}
QTableWidget::item:selected, QTableView::item:selected {{
    background-color: {_ACCENT_BG_18};
    color: {_TEXT_PRI};
}}
QHeaderView::section {{
    background: {_BG_OVERLAY};
    color: {_TEXT_DIM};
    border: none;
    border: none;
    padding: {SPACE_10}px {SPACE_SM}px;
    font-weight: {FONT_WEIGHT_BOLD};
    font-size: {FONT_SIZE_CAPTION}px;
    letter-spacing: 0.{SPACE_SM}px;
    text-transform: uppercase;
}}
"""


def _scroll_styles() -> str:
    return f"""
QScrollArea {{
    border: none;
    background: transparent;
}}
QScrollArea QWidget {{ background: transparent; }}
QScrollArea::viewport {{
    background: transparent;
}}
QAbstractScrollArea::viewport {{ background: transparent; }}
QScrollArea:corner {{ background: transparent; }}

QScrollBar:vertical {{
    background: transparent;
    width: {SPACE_SM}px;
    margin: {SPACE_XS}px {SPACE_XXS}px {SPACE_XS}px {SPACE_XXS}px;
}}
QScrollBar::groove:vertical {{
    background: {_WHITE_02};
    border-radius: {RADIUS_6}px;
}}
QScrollBar::handle:vertical {{
    background: {_ACCENT_BG_18};
    border-radius: {RADIUS_6}px;
    min-height: {SPACE_28}px;
    border: {SPACE_XXXS}px solid {_WHITE_03};
}}
QScrollBar::handle:vertical:hover {{
    background: {_ACCENT_BG_30};
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}

QScrollBar:horizontal {{
    background: transparent;
    height: {SPACE_SM}px;
    margin: {SPACE_XXS}px {SPACE_XS}px {SPACE_XXS}px {SPACE_XS}px;
}}
QScrollBar::groove:horizontal {{
    background: {_WHITE_02};
    border-radius: {RADIUS_6}px;
}}
QScrollBar::handle:horizontal {{
    background: {_ACCENT_BG_18};
    border-radius: {RADIUS_6}px;
    min-width: {SPACE_28}px;
    border: {SPACE_XXXS}px solid {_WHITE_03};
}}
QScrollBar::handle:horizontal:hover {{
    background: {_ACCENT_BG_30};
}}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
"""


def _groupbox_styles() -> str:
    return f"""
QGroupBox {{
    background-color: {_BG_RAISED};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-radius: {RADIUS_MD}px;
    margin-top: {SPACE_18}px;
    padding-top: {SPACE_22}px;
    font-weight: {FONT_WEIGHT_BOLD};
    color: {_TEXT_PRI};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACE_LG}px;
    padding: 0 {SPACE_SM}px;
    color: {_TEXT_SEC};
    background: {_BG_RAISED};
    border-radius: {RADIUS_SM}px;
}}
"""


def _progress_styles() -> str:
    return f"""
QProgressBar {{
    background-color: {_BG_OVERLAY};
    border: none;
    border-radius: {RADIUS_SM}px;
    height: {SPACE_6}px;
    color: transparent;
}}
QProgressBar::chunk {{
    background: {_ACCENT_GRAD_END};
    border-radius: {RADIUS_SM}px;
}}
"""


def _dialog_styles() -> str:
    return f"""
QDialog {{
    background-color: {_BG_RAISED};
    border: {SPACE_XXXS}px solid {_BORDER};
    border-radius: {RADIUS_MD}px;
}}
"""


def _card_styles() -> str:
    return f"""
QFrame[class="card"] {{
    background: {_BG_RAISED};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-radius: {RADIUS_MD}px;
}}
"""


def _menu_styles() -> str:
    return f"""
QMenu {{
    background-color: {_BG_OVERLAY};
    border: {SPACE_XXXS}px solid {_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: {SPACE_XS}px;
    color: {_TEXT_PRI};
}}
QMenu::item {{
    padding: {SPACE_SM}px {SPACE_20}px;
    border-radius: {RADIUS_6}px;
}}
QMenu::item:selected {{
    background: {_ACCENT_GRAD_END};
    color: {_TEXT_ON_ACCENT};
}}
QMenu::separator {{
    height: {SPACE_XXXS}px;
    background: {_BORDER_DIM};
    margin: {SPACE_XS}px {SPACE_SM}px;
}}
"""


def _tooltip_styles() -> str:
    return f"""
QToolTip {{
    background-color: {_BG_OVERLAY};
    border: {SPACE_XXXS}px solid {_BORDER_DARK};
    border-radius: {RADIUS_6}px;
    color: {_TEXT_SOFT};
    padding: {SPACE_6}px {SPACE_10}px;
    font-size: {FONT_SIZE_LABEL}px;
}}
"""


def _datetime_styles() -> str:
    return f"""
QDateEdit, QTimeEdit, QDateTimeEdit {{
    background-color: {_BG_RAISED};
    border: {SPACE_XXXS}px solid {_BORDER};
    border-radius: {RADIUS_MD}px;
    padding: {SPACE_6}px {SPACE_MD}px;
    color: {_TEXT_PRI};
}}
QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {{
    border-color: {_ACCENT_GRAD_END};
}}
"""


def _splitter_styles() -> str:
    return f"""
QSplitter::handle {{
    background: {_BORDER_DIM};
}}
QSplitter::handle:vertical  {{ height: {SPACE_3}px; }}
QSplitter::handle:horizontal {{ width: {SPACE_3}px; }}
"""


def _statusbar_styles() -> str:
    return f"""
QStatusBar {{
    background: {_BG_DARKEST};
    color: {_TEXT_DIM};
    border-top: {SPACE_XXXS}px solid {_BORDER_DIM};
    font-size: {FONT_SIZE_LABEL}px;
}}
"""


def _misc_scrollarea_styles() -> str:
    return """
QAbstractScrollArea::viewport { background: transparent; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
"""


def build_dark_theme() -> str:
    return (
        _base_styles()
        + _button_styles()
        + _input_styles()
        + _spin_combo_styles()
        + _slider_styles()
        + _checkbox_styles()
        + _tab_styles()
        + _table_styles()
        + _scroll_styles()
        + _groupbox_styles()
        + _progress_styles()
        + _dialog_styles()
        + _card_styles()
        + _menu_styles()
        + _tooltip_styles()
        + _datetime_styles()
        + _splitter_styles()
        + _statusbar_styles()
        + _misc_scrollarea_styles()
    )


def build_sidebar_dark() -> str:
    return f"""
QFrame#sidebar {{
    background: {_BG_DARKEST};
    border-right: {SPACE_XXXS}px solid {_BG_OVERLAY};
}}
QLabel#sidebar-logo {{
    color: {_TEXT_PRI};
    font-size: {FONT_SIZE_LARGE}px;
    font-weight: {FONT_WEIGHT_BOLD};
    background: transparent;
    letter-spacing: -0.{SPACE_5}px;
}}
QLabel#sidebar-tagline {{
    color: {_TEXT_MUTED};
    font-size: {FONT_SIZE_MICRO}px;
    background: transparent;
    letter-spacing: {SPACE_XXXS}px;
}}
QLabel#sidebar-section {{
    color: {_TEXT_MUTED};
    font-size: {FONT_SIZE_MICRO}px;
    font-weight: {FONT_WEIGHT_BOLD};
    background: transparent;
    letter-spacing: 1.{SPACE_5}px;
    padding: {SPACE_6}px {SPACE_LG}px {SPACE_XXS}px {SPACE_LG}px;
    text-transform: uppercase;
}}
QPushButton.nav-btn {{
    background: transparent;
    color: {_TEXT_DIM};
    border: none;
    border-left: {SPACE_3}px solid transparent;
    border-radius: {RADIUS_NONE}px;
    padding: {SPACE_10}px {SPACE_LG}px;
    text-align: left;
    font-weight: {FONT_WEIGHT_NORMAL};
    font-size: {FONT_SIZE_BODY}px;
    min-height: {SIZE_CONTROL_38}px;
}}
QPushButton.nav-btn:hover {{
    background: {_BG_OVERLAY};
    color: {_TEXT_SOFT};
    border-left: {SPACE_3}px solid {_BORDER_DARK};
}}
QPushButton.nav-btn[active="true"] {{
    background: {_ACCENT_BG_15};
    color: {_ACCENT_HI};
    border-left: {SPACE_3}px solid {_ACCENT_GRAD_END};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
}}
"""