from __future__ import annotations

import re

from PySide6.QtCore import Qt, QSettings
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from frontend.app_theme import safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.widgets.animated_stack import AnimatedStackedWidget
from frontend.styles._btn_styles import _SEGMENT_TAB_BAR, _SEGMENT_TAB_BTN
from frontend.styles._input_styles import _SEARCH_INPUT
from frontend.styles._colors import _MUTED_BG_25
from frontend.styles.page_styles import header_bar_style, saved_clips_scrollbar_style, splitter_handle_style, toolbar_style
from frontend.ui_tokens import (
    FONT_SIZE_15,
    FONT_SIZE_9,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LARGE,
    FONT_WEIGHT_HEAVY,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_MD,
    SIZE_BADGE_H,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_30,
    SIZE_CONTROL_MD,
    SIZE_CONTROL_SM,
    SIZE_HEADER_H,
    SIZE_PANEL_MAX,
    SIZE_PANEL_MIN,
    SIZE_PILL_H,
    SIZE_SECTION_TALL,
    SPACE_10,
    SPACE_3,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXS,
)

from ._constants import (
    _BG_BASE,
    _BG_SURFACE,
    _BORDER_DIM,
    _PRIMARY_BTN,
    _TEXT_MUTED,
    _TEXT_PRI,
)
from ._detail_panel import DetailPanel


_SHARED_MANAGER_LAYOUT_APP = "ManagerLayout"
_SHARED_SPLITTER_LEFT_KEY = "splitter/left_width"
_DEFAULT_SPLITTER_LEFT = 340
_DEFAULT_SPLITTER_RIGHT = 660


def _coerce_left_width(value) -> int | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
    if isinstance(value, (list, tuple)) and value:
        try:
            return int(value[0])
        except (ValueError, TypeError):
            return None
    text = str(value).strip()
    if not text:
        return None
    if text.startswith("@"):
        return None
    match = re.search(r"-?\d+", text)
    if not match:
        return None
    try:
        return int(match.group(0))
    except (ValueError, TypeError):
        return None


def build_page_ui(page) -> None:

    root = QVBoxLayout(page)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)

    header_w = QWidget()
    header_w.setFixedHeight(SIZE_HEADER_H)
    header_w.setObjectName("fm_header")
    header_w.setStyleSheet(header_bar_style(widget_id="fm_header", bg=_BG_BASE, border=_BORDER_DIM))
    hl = QHBoxLayout(header_w)
    hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
    hl.setSpacing(SPACE_SM)

    _icon_lbl = QLabel()
    _icon_lbl.setFixedSize(SIZE_CONTROL_SM, SIZE_CONTROL_SM)
    _icon_pix = themed_icon_pixmap("frontend/assets/icons/faces.png", SIZE_CONTROL_SM, SIZE_CONTROL_SM)
    if not _icon_pix.isNull():
        _icon_lbl.setPixmap(_icon_pix)
    hl.addWidget(_icon_lbl)

    title_lbl = QLabel("Face Manager")
    tf = QFont()
    safe_set_point_size(tf, FONT_SIZE_LARGE)
    tf.setBold(True)
    title_lbl.setFont(tf)
    title_lbl.setStyleSheet(f"color: {_TEXT_PRI}; background: transparent; border: none; padding: 0;")
    hl.addWidget(title_lbl)
    hl.addStretch()

    import_btn = QPushButton("Import Folder")
    import_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
    import_btn.setStyleSheet(_PRIMARY_BTN)
    import_btn.clicked.connect(page._import_folder)
    hl.addWidget(import_btn)

    enroll_btn = QPushButton("+  Add Face")
    enroll_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
    enroll_btn.setStyleSheet(_PRIMARY_BTN)
    enroll_btn.clicked.connect(page._enroll_dialog)
    hl.addWidget(enroll_btn)

    root.addWidget(header_w)

    page._splitter = QSplitter(Qt.Orientation.Horizontal)
    page._splitter.setChildrenCollapsible(False)
    page._splitter.setStyleSheet(splitter_handle_style(color=_BORDER_DIM, width=SPACE_XXS))

    left_panel = QWidget()
    left_panel.setStyleSheet(f"background-color: {_BG_BASE};")
    left_panel.setMinimumWidth(SIZE_PANEL_MIN)
    left_panel.setMaximumWidth(SIZE_PANEL_MAX)
    ll = QVBoxLayout(left_panel)
    ll.setContentsMargins(0, 0, 0, 0)
    ll.setSpacing(0)

    search_container = QWidget()
    search_container.setStyleSheet(toolbar_style(bg=_BG_SURFACE, border=_BORDER_DIM))
    search_container.setFixedHeight(SIZE_SECTION_TALL)
    si = QVBoxLayout(search_container)
    si.setContentsMargins(SPACE_10, SPACE_10, SPACE_10, SPACE_10)
    si.setSpacing(SPACE_XS)

    search_row = QHBoxLayout()
    search_row.setSpacing(SPACE_6)
    search_row.setContentsMargins(0, 0, 0, 0)

    sicon = QLabel("\u2315")
    sicon.setFixedWidth(SIZE_PILL_H)
    sicon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    sicon.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent; font-size: {FONT_SIZE_15}px;")
    search_row.addWidget(sicon)

    page._search_edit = QLineEdit()
    page._search_edit.setPlaceholderText("Search by name or department\u2026")
    page._search_edit.setFixedHeight(SIZE_BADGE_H)
    page._search_edit.setStyleSheet(_SEARCH_INPUT)
    page._search_edit.textChanged.connect(page._filter_faces)
    search_row.addWidget(page._search_edit, stretch=1)
    si.addLayout(search_row)

    tab_bar = QWidget()
    tab_bar.setObjectName("TabBar")
    tab_bar.setStyleSheet(_SEGMENT_TAB_BAR)
    tab_bar.setFixedHeight(SIZE_CONTROL_30)
    tl = QHBoxLayout(tab_bar)
    tl.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
    tl.setSpacing(SPACE_XXS)

    page._tab_buttons = {}
    page._tab_counts = {}
    for key, label in [("all", "All"), ("authorized", "Auth"), ("restricted", "Rest"), ("inbox", "Inbox")]:
        btn = QPushButton()
        btn.setObjectName("Tab")
        btn.setCheckable(True)
        btn.setChecked(key == "all")
        btn.setStyleSheet(_SEGMENT_TAB_BTN)
        btn.clicked.connect(lambda checked, k=key: page._set_filter(k))

        btn_inner = QHBoxLayout(btn)
        btn_inner.setContentsMargins(SPACE_XS, 0, SPACE_XS, 0)
        btn_inner.setSpacing(SPACE_XS)
        btn_inner.setAlignment(Qt.AlignmentFlag.AlignCenter)

        text_lbl = QLabel(label)
        text_lbl.setStyleSheet(f"background: transparent; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_SEMIBOLD};")
        text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        btn_inner.addWidget(text_lbl)

        count_lbl = QLabel("0")
        count_lbl.setStyleSheet(f"""
            background: {_MUTED_BG_25}; color: {_TEXT_MUTED};
            border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px;
            font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;
        """)
        count_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        count_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        btn_inner.addWidget(count_lbl)

        tl.addWidget(btn)
        page._tab_buttons[key] = btn
        page._tab_counts[key] = count_lbl

    si.addWidget(tab_bar)
    ll.addWidget(search_container)

    page._roster_scroll = QScrollArea()
    page._roster_scroll.setWidgetResizable(True)
    page._roster_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    page._roster_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    page._roster_scroll.setStyleSheet(saved_clips_scrollbar_style(scroll_area_bg=_BG_BASE))

    page._roster_container = QWidget()
    page._roster_container.setStyleSheet(f"background: {_BG_BASE};")
    page._roster_vbox = QVBoxLayout(page._roster_container)
    page._roster_vbox.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
    page._roster_vbox.setSpacing(SPACE_6)
    page._roster_vbox.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)

    page._roster_scroll.setWidget(page._roster_container)
    ll.addWidget(page._roster_scroll, stretch=1)

    page._detail_panel = DetailPanel()
    page._detail_panel.setStyleSheet(f"background-color: {_BG_SURFACE};")
    page._detail_panel.save_requested.connect(page._save_face_details)
    page._detail_panel.close_requested.connect(page._close_details)
    page._detail_panel.delete_requested.connect(page._delete_face)
    page._detail_panel.enroll_requested.connect(page._enroll_dialog)

    page._right_stack = AnimatedStackedWidget()
    page._right_stack.addWidget(page._detail_panel)
    page._enroll_panel = None

    page._splitter.addWidget(left_panel)
    page._splitter.addWidget(page._right_stack)
    page._splitter.setStretchFactor(0, 0)
    page._splitter.setStretchFactor(1, 1)

    _qs = QSettings("SmartEye", "FaceManager")
    _shared_qs = QSettings("SmartEye", _SHARED_MANAGER_LAYOUT_APP)
    _saved = _qs.value("splitter/sizes")

    left_width = _coerce_left_width(_shared_qs.value(_SHARED_SPLITTER_LEFT_KEY))
    if left_width is None:
        left_width = _coerce_left_width(_saved)
    if left_width is None:
        left_width = _DEFAULT_SPLITTER_LEFT

    left_width = max(SIZE_PANEL_MIN, min(SIZE_PANEL_MAX, left_width))
    page._splitter.setSizes([left_width, _DEFAULT_SPLITTER_RIGHT])
    _shared_qs.setValue(_SHARED_SPLITTER_LEFT_KEY, left_width)

    def _save_splitter(pos, index):
        _qs2 = QSettings("SmartEye", "FaceManager")
        sizes = page._splitter.sizes()
        _qs2.setValue("splitter/sizes", sizes)
        if sizes and len(sizes) >= 1:
            QSettings("SmartEye", _SHARED_MANAGER_LAYOUT_APP).setValue(_SHARED_SPLITTER_LEFT_KEY, int(sizes[0]))

    page._splitter.splitterMoved.connect(_save_splitter)
    root.addWidget(page._splitter, stretch=1)
