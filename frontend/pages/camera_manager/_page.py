from __future__ import annotations

import logging
import re

from PySide6.QtCore import QEvent, QSettings, Qt, QObject
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLayout,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.widgets.animated_stack import AnimatedStackedWidget
from frontend.styles._btn_styles import _SEGMENT_TAB_BAR, _SEGMENT_TAB_BTN
from frontend.styles._input_styles import _SEARCH_INPUT
from frontend.styles._colors import _ACCENT_BG_22, _MUTED_BG_25
from frontend.styles.page_styles import header_bar_style, saved_clips_scrollbar_style, splitter_handle_style, toolbar_style
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
    SIZE_BADGE_H,
    SIZE_BTN_W_XL,
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
    SPACE_XXL,
    SPACE_XXS,
    SPACE_XXXS,
)

from ._cards import CameraCard
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
from ._detail_panel import CameraDetailPanel
from ._forms import AddCameraPanel

logger = logging.getLogger(__name__)

_SETTINGS_KEY = "CameraManager"
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


class CameraManagerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._cameras: list[dict] = []
        self._active_cam_id: int | None = None
        self._card_widgets: dict = {}
        self._active_filter = "all"
        self._tab_buttons: dict = {}
        self._tab_counts: dict = {}
        self._build_ui()
        self._install_dialog_logger()

    def on_activated(self):
        self._refresh()

    def on_deactivated(self):
        self._detail_panel.clear()
        self._render_roster([])

    def on_unload(self):
        self._detail_panel.clear()
        self._render_roster([])

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header_w = QWidget()
        header_w.setFixedHeight(SIZE_HEADER_H)
        header_w.setObjectName("cm_header")
        header_w.setStyleSheet(header_bar_style(widget_id="cm_header", bg=_BG_BASE, border=_BORDER_DIM))
        hl = QHBoxLayout(header_w)
        hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        hl.setSpacing(SPACE_SM)

        _icon_lbl = QLabel()
        _icon_lbl.setFixedSize(SIZE_CONTROL_SM, SIZE_CONTROL_SM)
        _icon_pix = themed_icon_pixmap("frontend/assets/icons/cameras.png", SIZE_CONTROL_SM, SIZE_CONTROL_SM)
        if not _icon_pix.isNull():
            _icon_lbl.setPixmap(_icon_pix)
        hl.addWidget(_icon_lbl)

        title = QLabel("Camera Manager")
        tf = QFont()
        safe_set_point_size(tf, FONT_SIZE_LARGE)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(f"color: {_TEXT_PRI}; background: transparent; border: none; padding: 0;")
        hl.addWidget(title)
        hl.addStretch()

        self._add_cam_btn = QPushButton("+  Add Camera")
        self._add_cam_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._add_cam_btn.setFixedWidth(SIZE_BTN_W_XL)
        self._add_cam_btn.setStyleSheet(_PRIMARY_BTN)
        self._add_cam_btn.clicked.connect(self._open_add_camera_panel)
        hl.addWidget(self._add_cam_btn)

        root.addWidget(header_w)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setStyleSheet(splitter_handle_style(color=_BORDER_DIM, width=SPACE_XXXS))

        left_panel = QWidget()
        left_panel.setStyleSheet(f"background-color: {_BG_BASE};")
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
        sicon.setFixedWidth(SIZE_PILL_H)
        sicon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sicon.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent; font-size: {FONT_SIZE_15}px;")
        search_row.addWidget(sicon)
        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search cameras…")
        self._search_edit.setFixedHeight(SIZE_BADGE_H)
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
            txt.setStyleSheet(f"background: transparent; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_SEMIBOLD};")
            txt.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            bi.addWidget(txt)
            cnt = QLabel("0")
            cnt.setStyleSheet(f"""
                background: {_MUTED_BG_25}; color: {_TEXT_MUTED};
                border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px;
                font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;
            """)
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
        self._roster_scroll.setStyleSheet(saved_clips_scrollbar_style(scroll_area_bg=_BG_BASE))
        self._roster_container = QWidget()
        self._roster_container.setStyleSheet(f"background: {_BG_BASE};")
        self._roster_vbox = QVBoxLayout(self._roster_container)
        self._roster_vbox.setContentsMargins(SPACE_SM, SPACE_SM, SPACE_SM, SPACE_SM)
        self._roster_vbox.setSpacing(SPACE_6)
        self._roster_vbox.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        self._roster_scroll.setWidget(self._roster_container)
        ll.addWidget(self._roster_scroll, stretch=1)

        self._detail_panel = CameraDetailPanel()
        self._detail_panel.setStyleSheet(f"background-color: {_BG_SURFACE};")
        self._detail_panel.delete_requested.connect(self._on_delete_camera)
        self._detail_panel.saved.connect(self._on_detail_saved)
        self._detail_panel.close_requested.connect(self._close_detail)

        self._add_panel = AddCameraPanel()
        self._add_panel.setStyleSheet(_STYLESHEET + f"background-color: {_BG_SURFACE};")
        self._add_panel.saved.connect(self._on_add_camera_saved)
        self._add_panel.close_requested.connect(self._close_add_panel)

        self._right_stack = AnimatedStackedWidget()
        self._right_stack.addWidget(self._detail_panel)
        self._right_stack.addWidget(self._add_panel)

        self._splitter.addWidget(left_panel)
        self._splitter.addWidget(self._right_stack)
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        _qs = QSettings("SmartEye", "CameraManager")
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

    def _save_splitter(self, pos=None, index=None):
        _qs = QSettings("SmartEye", "CameraManager")
        sizes = self._splitter.sizes()
        _qs.setValue("splitter/sizes", sizes)
        if sizes and len(sizes) >= 1:
            QSettings("SmartEye", _SHARED_MANAGER_LAYOUT_APP).setValue(_SHARED_SPLITTER_LEFT_KEY, int(sizes[0]))

    def _refresh(self):
        try:
            self._cameras = db.get_cameras() or []
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.exception("Failed to load cameras")
            self._cameras = []
        total = len(self._cameras)
        active = sum(1 for c in self._cameras if c.get("enabled"))
        inactive = total - active
        for key, val in [("all", total), ("active", active), ("inactive", inactive)]:
            if key in self._tab_counts:
                self._tab_counts[key].setText(str(val))
        self._update_tab_count_styles()
        self._apply_filter_and_search()
        if self._active_cam_id is not None:
            cam = next((c for c in self._cameras if c["id"] == self._active_cam_id), None)
            if cam:
                self._detail_panel.load_camera(cam)
            else:
                self._active_cam_id = None
                self._detail_panel.clear()

    def _set_filter(self, key: str):
        self._active_filter = key
        for k, btn in self._tab_buttons.items():
            btn.setChecked(k == key)
        self._update_tab_count_styles()
        self._apply_filter_and_search()

    def _update_tab_count_styles(self):
        for key, lbl in self._tab_counts.items():
            if self._tab_buttons.get(key) and self._tab_buttons[key].isChecked():
                lbl.setStyleSheet(f"""
                    background: {_ACCENT_BG_22}; color: {_ACCENT_HI};
                    border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px;
                    font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;
                """)
            else:
                lbl.setStyleSheet(f"""
                    background: {_MUTED_BG_25}; color: {_TEXT_MUTED};
                    border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px;
                    font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;
                """)

    def _apply_filter_and_search(self):
        text = self._search_edit.text().lower().strip()
        cams = self._cameras
        if self._active_filter == "active":
            cams = [c for c in cams if c.get("enabled")]
        elif self._active_filter == "inactive":
            cams = [c for c in cams if not c.get("enabled")]
        if text:
            cams = [
                c
                for c in cams
                if text in c.get("name", "").lower() or text in (c.get("source") or "").lower() or text in (c.get("location") or "").lower()
            ]
        self._render_roster(cams)

    def _render_roster(self, cameras: list[dict]):
        self._card_widgets.clear()
        while self._roster_vbox.count():
            item = self._roster_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not cameras:
            empty_w = QWidget()
            empty_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            empty_w.setStyleSheet("background: transparent; border: none;")
            el = QVBoxLayout(empty_w)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setSpacing(SPACE_10)
            el.setContentsMargins(SPACE_LG, SPACE_XXL, SPACE_LG, SPACE_XXL)
            has_filter = self._active_filter != "all"
            has_search = bool(self._search_edit.text().strip())
            title = QLabel("No results" if (has_search or has_filter) else "No cameras yet")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(f"font-size: {FONT_SIZE_BODY}px; font-weight: {FONT_WEIGHT_BOLD}; color: {_TEXT_SEC};")
            el.addWidget(title)
            sub = QLabel(
                "Try adjusting your search or filter." if (has_search or has_filter) else "Click '+  Add Camera' to add your first camera."
            )
            sub.setWordWrap(True)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(f"font-size: {FONT_SIZE_CAPTION}px; color: {_TEXT_MUTED};")
            el.addWidget(sub)
            self._roster_vbox.addWidget(empty_w)
            return

        for cam in cameras:
            is_active = cam["id"] == self._active_cam_id
            card = CameraCard(
                cam,
                is_active=is_active,
                on_toggle_changed=self._refresh,
            )
            card.clicked.connect(self._on_card_clicked)
            self._roster_vbox.addWidget(card)
            self._card_widgets[cam["id"]] = card


        self._roster_vbox.addStretch(1)

    def _update_roster_active_state(self):
        for cid, card in list(self._card_widgets.items()):
            if card.parent():
                idx = self._roster_vbox.indexOf(card)
                if idx >= 0:
                    cam = next((c for c in self._cameras if c["id"] == cid), None)
                    if cam:
                        new_card = CameraCard(
                            cam,
                            is_active=(cid == self._active_cam_id),
                            on_toggle_changed=self._refresh,
                        )
                        new_card.clicked.connect(self._on_card_clicked)
                        self._roster_vbox.replaceWidget(card, new_card)
                        card.deleteLater()
                        self._card_widgets[cid] = new_card

    def _on_card_clicked(self, cam_id: int):
        self._active_cam_id = cam_id
        cam = next((c for c in self._cameras if c["id"] == cam_id), None)
        if cam is None:
            try:
                cam = db.get_camera(cam_id)
            except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                return
        if cam is None:
            return
        self._right_stack.setCurrentIndex(0)
        self._detail_panel.load_camera(cam)
        self._update_roster_active_state()

    def _close_detail(self):
        self._active_cam_id = None
        self._detail_panel.clear()
        self._update_roster_active_state()

    def _close_add_panel(self):
        self._right_stack.setCurrentIndex(0)

    def _open_add_camera_panel(self):
        self._active_cam_id = None
        self._add_panel.reset()
        self._update_roster_active_state()
        self._right_stack.setCurrentIndex(1)

    def _on_add_camera_saved(self):
        self._right_stack.setCurrentIndex(0)
        self._refresh()
        if self._cameras:
            newest = self._cameras[-1]
            self._active_cam_id = newest["id"]
            self._detail_panel.load_camera(newest)
            self._update_roster_active_state()

    def _on_detail_saved(self):
        self._refresh()

    def _on_delete_camera(self, cam_id: int):
        try:
            from backend.camera.camera_manager import get_camera_manager

            try:
                get_camera_manager().stop_camera(cam_id)
            except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                pass
            db.delete_camera(cam_id)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.exception("Failed to delete camera %s", cam_id)
            return
        self._active_cam_id = None
        self._detail_panel.clear()
        self._refresh()

    def _install_dialog_logger(self):
        app = QApplication.instance()
        if app is None or hasattr(self, "_dlg_logger"):
            return

        class _DialogLogger(QObject):
            def eventFilter(self, obj, event):
                if event.type() == QEvent.Type.Show and isinstance(obj, QDialog):
                    try:
                        logger.warning(
                            "camera_manager dialog show class=%s title=%s",
                            obj.__class__.__name__,
                            obj.windowTitle(),
                        )
                    except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                        pass
                return False

        self._dlg_logger = _DialogLogger()
        app.installEventFilter(self._dlg_logger)
        logger.info("camera_manager dialog logger installed")

