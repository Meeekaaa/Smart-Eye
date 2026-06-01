from __future__ import annotations

import logging
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
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from frontend.services.rules_service import RulesService
from frontend.app_theme import safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.widgets.animated_stack import AnimatedStackedWidget

from frontend.styles._colors import _ACCENT_BG_22, _MUTED_BG_25
from frontend.styles._btn_styles import _SEGMENT_TAB_BAR, _SEGMENT_TAB_BTN
from frontend.styles._input_styles import _SEARCH_INPUT
from frontend.styles.page_styles import header_bar_style, saved_clips_scrollbar_style, splitter_handle_style, text_style, toolbar_style
from frontend.ui_tokens import (
    FONT_SIZE_15,
    FONT_SIZE_9,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LARGE,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_HEAVY,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_MD,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_30,
    SIZE_CONTROL_32,
    SIZE_CONTROL_MD,
    SIZE_HEADER_H,
    SIZE_ICON_LG,
    SIZE_ICON_SM,
    SIZE_PANEL_MAX,
    SIZE_PANEL_MIN,
    SIZE_SECTION_TALL,
    SPACE_10,
    SPACE_3,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXL,
    SPACE_XXS,
    SPACE_XXXS,
)
from ._constants import (
    _ACCENT_HI,
    _BG_BASE,
    _BG_SURFACE,
    _BORDER_DIM,
    _PRIMARY_BTN,
    _STYLESHEET,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from ._detail_panel import RuleDetailPanel
from ._forms import NewRulePanel
from ._widgets import RuleCard

logger = logging.getLogger(__name__)
_TITLE_STYLE = text_style(_TEXT_PRI, extra="background: transparent; border: none; padding: 0;")
_SEARCH_ICON_STYLE = text_style(_TEXT_MUTED, size=FONT_SIZE_15, extra="background: transparent;")
_BG_BASE_STYLE = f"background-color: {_BG_BASE};"
_SCROLL_BASE_STYLE = saved_clips_scrollbar_style(scroll_area_bg=_BG_BASE)
_DETAIL_PANEL_BG_STYLE = f"background-color: {_BG_SURFACE};"
_TAB_LABEL_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_CAPTION, weight=FONT_WEIGHT_SEMIBOLD, extra="background: transparent;")
_COUNT_BADGE_INACTIVE_STYLE = (
    f"background: {_MUTED_BG_25}; color: {_TEXT_MUTED}; "
    f"border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px; "
    f"font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;"
)
_COUNT_BADGE_ACTIVE_STYLE = (
    f"background: {_ACCENT_BG_22}; color: {_ACCENT_HI}; "
    f"border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px; "
    f"font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;"
)
_EMPTY_TITLE_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_BODY, weight=FONT_WEIGHT_BOLD)
_EMPTY_SUB_STYLE = text_style(_TEXT_MUTED, size=FONT_SIZE_CAPTION)
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

class RulesManagerPage(QWidget):
    def __init__(self, parent=None, rules_service: RulesService | None = None):
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._rules_service = rules_service or RulesService()
        self._all_rules: list = []
        self._active_rule_id = None
        self._card_widgets: dict = {}
        self._new_rule_panel = None
        self._active_filter = "all"
        self._tab_buttons: dict = {}
        self._tab_counts: dict = {}
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header_w = QWidget()
        header_w.setFixedHeight(SIZE_HEADER_H)
        header_w.setObjectName("rm_header")
        header_w.setStyleSheet(header_bar_style(widget_id="rm_header", bg=_BG_BASE, border=_BORDER_DIM))
        hl = QHBoxLayout(header_w)
        hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        hl.setSpacing(SPACE_SM)

        _icon_lbl = QLabel()
        _icon_lbl.setFixedSize(SIZE_ICON_LG, SIZE_ICON_LG)
        _icon_pix = themed_icon_pixmap("frontend/assets/icons/rules.png", SIZE_ICON_LG, SIZE_ICON_LG)
        if not _icon_pix.isNull():
            _icon_lbl.setPixmap(_icon_pix)
        hl.addWidget(_icon_lbl)

        title = QLabel("Rules Manager")
        tf = QFont()
        safe_set_point_size(tf, FONT_SIZE_LARGE)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(_TITLE_STYLE)
        hl.addWidget(title)
        hl.addStretch()

        simulate_btn = QPushButton("Simulate")
        simulate_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        simulate_btn.setStyleSheet(_PRIMARY_BTN)
        simulate_btn.clicked.connect(self._open_simulation_panel)
        hl.addWidget(simulate_btn)

        new_btn = QPushButton("+  Add Rule")
        new_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        new_btn.setStyleSheet(_PRIMARY_BTN)
        new_btn.clicked.connect(self._open_new_rule_panel)
        hl.addWidget(new_btn)

        root.addWidget(header_w)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStyleSheet(splitter_handle_style(color=_BORDER_DIM, width=SPACE_XXXS))

        left_panel = QWidget()
        left_panel.setStyleSheet(_BG_BASE_STYLE)
        left_panel.setMinimumWidth(SIZE_PANEL_MIN)
        left_panel.setMaximumWidth(SIZE_PANEL_MAX)
        ll = QVBoxLayout(left_panel)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(0)

        search_container = QWidget()
        search_container.setStyleSheet(toolbar_style(bg=_BG_SURFACE, border=_BORDER_DIM))
        si = QVBoxLayout(search_container)
        si.setContentsMargins(SPACE_10, SPACE_10, SPACE_10, SPACE_10)
        si.setSpacing(0)

        search_row = QHBoxLayout()
        search_row.setSpacing(SPACE_6)
        sicon = QLabel("⌕")
        sicon.setFixedWidth(SIZE_ICON_SM)
        sicon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sicon.setStyleSheet(_SEARCH_ICON_STYLE)
        search_row.addWidget(sicon)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search rules…")
        self._search_edit.setFixedHeight(SIZE_CONTROL_32)
        self._search_edit.setStyleSheet(_SEARCH_INPUT)
        self._search_edit.textChanged.connect(self._apply_filter_and_search)
        search_row.addWidget(self._search_edit, stretch=1)
        si.addLayout(search_row)

        tab_bar = QWidget()
        tab_bar.setObjectName("TabBar")
        tab_bar.setStyleSheet(_SEGMENT_TAB_BAR)
        tab_bar.setFixedHeight(SIZE_CONTROL_30)
        tl = QHBoxLayout(tab_bar)
        tl.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        tl.setSpacing(SPACE_XXS)

        for key, label in [("all", "All"), ("active", "Active"), ("inactive", "Inactive")]:
            btn = QPushButton()
            btn.setObjectName("Tab")
            btn.setCheckable(True)
            btn.setChecked(key == "all")
            btn.setStyleSheet(_SEGMENT_TAB_BTN)
            btn.clicked.connect(lambda _checked, k=key: self._set_filter(k))

            bi = QHBoxLayout(btn)
            bi.setContentsMargins(SPACE_XS, 0, SPACE_XS, 0)
            bi.setSpacing(SPACE_XS)
            bi.setAlignment(Qt.AlignmentFlag.AlignCenter)
            txt = QLabel(label)
            txt.setStyleSheet(_TAB_LABEL_STYLE)
            txt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            bi.addWidget(txt)
            cnt = QLabel("0")
            cnt.setStyleSheet(_COUNT_BADGE_INACTIVE_STYLE)
            cnt.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cnt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            bi.addWidget(cnt)
            tl.addWidget(btn)
            self._tab_buttons[key] = btn
            self._tab_counts[key] = cnt

        si.addSpacing(SPACE_XS)
        si.addWidget(tab_bar)
        search_container.setFixedHeight(SIZE_SECTION_TALL)
        ll.addWidget(search_container)

        self._roster_scroll = QScrollArea()
        self._roster_scroll.setWidgetResizable(True)
        self._roster_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._roster_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._roster_scroll.setStyleSheet(_SCROLL_BASE_STYLE)
        self._roster_container = QWidget()
        self._roster_container.setStyleSheet(_BG_BASE_STYLE)
        self._roster_vbox = QVBoxLayout(self._roster_container)
        self._roster_vbox.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        self._roster_vbox.setSpacing(SPACE_6)
        self._roster_vbox.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self._roster_scroll.setWidget(self._roster_container)
        ll.addWidget(self._roster_scroll, stretch=1)

        self._detail_panel = RuleDetailPanel(rules_service=self._rules_service)
        self._detail_panel.setStyleSheet(_DETAIL_PANEL_BG_STYLE)
        self._detail_panel.delete_requested.connect(self._delete_rule)
        self._detail_panel.saved.connect(self._on_rule_saved)
        self._detail_panel.close_requested.connect(self._close_detail)

        self._right_stack = AnimatedStackedWidget()
        self._right_stack.addWidget(self._detail_panel)

        self._splitter.addWidget(left_panel)
        self._splitter.addWidget(self._right_stack)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        _qs = QSettings("SmartEye", "RulesManager")
        _shared_qs = QSettings("SmartEye", _SHARED_MANAGER_LAYOUT_APP)
        _saved = _qs.value("splitter/sizes")

        left_width = _coerce_left_width(_shared_qs.value(_SHARED_SPLITTER_LEFT_KEY))
        if left_width is None:
            left_width = _coerce_left_width(_saved)

        if left_width is None:
            left_width = _DEFAULT_SPLITTER_LEFT

        left_width = max(SIZE_PANEL_MIN, min(SIZE_PANEL_MAX, left_width))
        self._splitter.setSizes([left_width, _DEFAULT_SPLITTER_RIGHT])
        _shared_qs.setValue(_SHARED_SPLITTER_LEFT_KEY, left_width)

        self._splitter.splitterMoved.connect(self._save_splitter)
        root.addWidget(self._splitter, stretch=1)

    def _save_splitter(self, pos, index):
        _qs = QSettings("SmartEye", "RulesManager")
        sizes = self._splitter.sizes()
        _qs.setValue("splitter/sizes", sizes)
        if sizes and len(sizes) >= 1:
            left = int(sizes[0])
            QSettings("SmartEye", _SHARED_MANAGER_LAYOUT_APP).setValue(_SHARED_SPLITTER_LEFT_KEY, left)

    def on_activated(self):
        self._refresh()

    def _refresh(self):
        self._all_rules = self._rules_service.get_rules()
        total = len(self._all_rules)
        active = sum(1 for r in self._all_rules if r.get("enabled", 1))
        inactive = total - active
        for key, val in [("all", total), ("active", active), ("inactive", inactive)]:
            if key in self._tab_counts:
                self._tab_counts[key].setText(str(val))
        self._update_tab_count_styles()
        self._apply_filter_and_search()
        if self._active_rule_id is not None:
            rule = next((r for r in self._all_rules if r["id"] == self._active_rule_id), None)
            if rule:
                self._detail_panel.load_rule(rule)
            else:
                self._active_rule_id = None
                self._detail_panel.clear()

    def _set_filter(self, key: str):
        self._active_filter = key
        for k, btn in self._tab_buttons.items():
            btn.setChecked(k == key)
        self._update_tab_count_styles()
        self._apply_filter_and_search()

    def _update_tab_count_styles(self):
        for key, lbl in self._tab_counts.items():
            if self._tab_buttons.get(key, None) and self._tab_buttons[key].isChecked():
                lbl.setStyleSheet(_COUNT_BADGE_ACTIVE_STYLE)
            else:
                lbl.setStyleSheet(_COUNT_BADGE_INACTIVE_STYLE)

    def _apply_filter_and_search(self):
        text = self._search_edit.text().lower().strip()
        rules = self._all_rules
        if self._active_filter == "active":
            rules = [r for r in rules if r.get("enabled", 1)]
        elif self._active_filter == "inactive":
            rules = [r for r in rules if not r.get("enabled", 1)]
        if text:
            rules = [r for r in rules if text in r.get("name", "").lower() or text in (r.get("description") or "").lower()]
        self._render_roster(rules)

    def _render_roster(self, rules: list):
        self._card_widgets.clear()
        while self._roster_vbox.count():
            item = self._roster_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not rules:
            empty_w = QWidget()
            empty_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            empty_w.setStyleSheet("background: transparent; border: none;")
            el = QVBoxLayout(empty_w)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setSpacing(SPACE_10)
            el.setContentsMargins(SPACE_LG, SPACE_XXL, SPACE_LG, SPACE_XXL)
            has_filter = self._active_filter != "all"
            has_search = bool(self._search_edit.text().strip())
            title = QLabel("No results" if (has_search or has_filter) else "No rules yet")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(_EMPTY_TITLE_STYLE)
            el.addWidget(title)
            sub = QLabel(
                "Try adjusting your search or filter." if (has_search or has_filter) else "Click '+  Add Rule' to create your first rule."
            )
            sub.setWordWrap(True)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(_EMPTY_SUB_STYLE)
            el.addWidget(sub)
            self._roster_vbox.addWidget(empty_w)
            return

        for rule in rules:
            is_active = rule["id"] == self._active_rule_id
            card = RuleCard(
                rule,
                is_active=is_active,
                on_stop_sounds=self._stop_alarm_sounds,
                on_toggle_changed=self._set_rule_enabled,
            )
            card.clicked.connect(self._on_card_clicked)
            self._roster_vbox.addWidget(card)
            self._card_widgets[rule["id"]] = card


        self._roster_vbox.addStretch(1)

    def _set_rule_enabled(self, rule_id: int, enabled: bool):
        try:
            self._rules_service.set_rule_enabled(rule_id, enabled)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.exception("Failed to toggle rule %s", rule_id)
        self._refresh()

    def _on_card_clicked(self, rule_id: int):
        self._active_rule_id = rule_id
        rule = next((r for r in self._all_rules if r["id"] == rule_id), None)
        if rule:
            if self._new_rule_panel is not None:
                self._close_new_rule_panel()
            self._right_stack.setCurrentIndex(0)
            self._detail_panel.load_rule(rule)
        self._update_roster_active_state()

    def _close_detail(self):
        self._active_rule_id = None
        self._detail_panel.clear()
        self._update_roster_active_state()

    def _on_rule_saved(self):
        self._refresh()

    def _update_roster_active_state(self):
        for rid, card in list(self._card_widgets.items()):
            card.set_active(rid == self._active_rule_id)

    def _open_new_rule_panel(self):
        if self._new_rule_panel is None:
            self._new_rule_panel = NewRulePanel(self._rules_service)
            self._new_rule_panel.setStyleSheet(_STYLESHEET + _DETAIL_PANEL_BG_STYLE)
            self._new_rule_panel.saved.connect(self._on_new_rule_saved)
            self._new_rule_panel.close_requested.connect(self._close_new_rule_panel)
            self._right_stack.addWidget(self._new_rule_panel)
        else:
            self._new_rule_panel.reset()
        self._active_rule_id = None
        self._update_roster_active_state()
        self._right_stack.setCurrentIndex(1)

    def _close_new_rule_panel(self):
        if self._new_rule_panel is not None:
            self._right_stack.removeWidget(self._new_rule_panel)
            self._new_rule_panel.deleteLater()
            self._new_rule_panel = None
        self._right_stack.setCurrentIndex(0)

    def _on_new_rule_saved(self, rule_id: int):
        self._close_new_rule_panel()
        self._refresh()
        saved_rule = next((r for r in self._all_rules if int(r.get("id", -1)) == int(rule_id)), None)
        if saved_rule:
            self._active_rule_id = saved_rule["id"]
            self._detail_panel.load_rule(saved_rule)
            self._update_roster_active_state()

    def _delete_rule(self, rule_id: int):
        self._rules_service.delete_rule(rule_id)
        self._active_rule_id = None
        self._detail_panel.clear()
        self._refresh()

    def _stop_alarm_sounds(self):
        try:
            from backend.pipeline.alarm_handler import stop_all_sounds

            stop_all_sounds()
        except (ImportError, RuntimeError, OSError):
            logger.warning("Failed to stop alarm sounds", exc_info=True)

    def _open_simulation_panel(self):
        if self._active_rule_id is None and self._all_rules:
            self._on_card_clicked(self._all_rules[0]["id"])
        if self._active_rule_id is not None:
            self._right_stack.setCurrentIndex(0)
            self._detail_panel.open_simulation()
