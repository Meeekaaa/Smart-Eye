from __future__ import annotations

import json
import logging
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.widgets.animated_stack import AnimatedStackedWidget
from frontend.styles.page_styles import divider_style
from frontend.ui_tokens import (
    FONT_SIZE_LARGE,
    SIZE_BTN_W_100,
    SIZE_HEADER_H,
    SIZE_ICON_LG,
    SPACE_10,
    SPACE_MD,
    SPACE_XL,
    SPACE_XXXS,
)

from ._constants import (
    _BG_SURFACE,
    _BORDER_DIM,
    _BTN_H,
    _PRIMARY_BTN,
    _STYLESHEET,
    _TAB_BAR_H,
    _TAB_BTN,
    _TAB_BTN_ACTIVE,
    _TEXT_PRI,
)
from ._general_tab import GeneralTab
from ._performance_tab import PerformanceTab
from ._detection_tab import DetectionTab
from ._accounts_tab import AccountsTab
from ._database_tab import DatabaseTab
from ._debug_tab import DebugTab
from ._experimental_tab import ExperimentalTab

logger = logging.getLogger(__name__)

_ICON_DIR = os.path.join("frontend", "assets", "icons")
_ICON_SIZE = QSize(16, 16)


_TABS: list[tuple[str, str]] = [
    ("General", "settings.png"),
    ("Performance", "dashboard.png"),
    ("Detection and recogention", "faces.png"),
    ("Accounts", "account.png"),
    ("Database", "folder.png"),
]


def _load_icon(filename: str) -> QIcon:
    path = os.path.join(_ICON_DIR, filename)
    if not os.path.isfile(path):
        return QIcon()
    pix = themed_icon_pixmap(path, _ICON_SIZE.width(), _ICON_SIZE.height())
    return QIcon(pix) if not pix.isNull() else QIcon(path)


class SettingsPage(QWidget):
    theme_changed = Signal(str)
    tab_transitions_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._tab_buttons: list[QPushButton] = []
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_tab_bar())
        root.addWidget(self._build_tab_bar_separator())
        root.addWidget(self._build_content(), stretch=1)

    def _build_header(self) -> QWidget:
        hdr = QWidget()
        hdr.setFixedHeight(SIZE_HEADER_H)
        hdr.setStyleSheet(f"background: {_BG_SURFACE}; border-bottom: none;")
        row = QHBoxLayout(hdr)
        row.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        row.setSpacing(SPACE_10)

        _icon_lbl = QLabel()
        _icon_lbl.setFixedSize(SIZE_ICON_LG, SIZE_ICON_LG)
        _icon_pix = themed_icon_pixmap("frontend/assets/icons/settings.png", SIZE_ICON_LG, SIZE_ICON_LG)
        if not _icon_pix.isNull():
            _icon_lbl.setPixmap(_icon_pix)
        row.addWidget(_icon_lbl)

        title = QLabel("Settings")
        f = QFont()
        safe_set_point_size(f, FONT_SIZE_LARGE)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(f"color: {_TEXT_PRI}; background: transparent;")
        row.addWidget(title)
        row.addStretch()

        import_btn = QPushButton("Import…")
        import_btn.setStyleSheet(_PRIMARY_BTN)
        import_btn.setFixedSize(SIZE_BTN_W_100, _BTN_H)
        import_btn.clicked.connect(self._import_settings)
        row.addWidget(import_btn)

        export_btn = QPushButton("Export…")
        export_btn.setStyleSheet(_PRIMARY_BTN)
        export_btn.setFixedSize(SIZE_BTN_W_100, _BTN_H)
        export_btn.clicked.connect(self._export_settings)
        row.addWidget(export_btn)
        return hdr

    def _build_tab_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(_TAB_BAR_H)
        bar.setStyleSheet(f"background: {_BG_SURFACE}; border: none;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(SPACE_MD, 0, SPACE_MD, 0)
        row.setSpacing(0)

        for idx, (label, icon_file) in enumerate(_TABS):
            btn = QPushButton(f"  {label}")
            btn.setIcon(_load_icon(icon_file))
            btn.setIconSize(_ICON_SIZE)
            btn.setStyleSheet(_TAB_BTN)
            btn.clicked.connect(lambda _, i=idx: self._switch_to(i))
            row.addWidget(btn)
            self._tab_buttons.append(btn)

        debug_btn = QPushButton("  Debug")
        debug_btn.setIcon(_load_icon("debug.png"))
        debug_btn.setIconSize(_ICON_SIZE)
        debug_btn.setStyleSheet(_TAB_BTN)
        debug_btn.clicked.connect(lambda: self._switch_to(len(_TABS)))
        debug_btn.setVisible(False)
        row.addWidget(debug_btn)
        self._tab_buttons.append(debug_btn)
        self._debug_tab_btn = debug_btn

        exp_btn = QPushButton("  Experimental")
        exp_btn.setIcon(_load_icon("experimental.png"))
        exp_btn.setIconSize(_ICON_SIZE)
        exp_btn.setStyleSheet(_TAB_BTN)
        exp_btn.clicked.connect(lambda: self._switch_to(len(_TABS) + 1))
        exp_btn.setVisible(False)
        row.addWidget(exp_btn)
        self._tab_buttons.append(exp_btn)
        self._experimental_tab_btn = exp_btn

        row.addStretch()
        return bar

    def _build_tab_bar_separator(self) -> QFrame:
        sep = QFrame()
        sep.setFixedHeight(SPACE_XXXS)
        sep.setStyleSheet(divider_style(color=_BORDER_DIM, height=SPACE_XXXS))
        return sep

    def _build_content(self) -> QWidget:
        self._stack = AnimatedStackedWidget()
        self._stack.setStyleSheet(f"background: {_BG_SURFACE};")

        self._general_tab = GeneralTab()
        self._performance_tab = PerformanceTab()
        self._detection_tab = DetectionTab()
        self._accounts_tab = AccountsTab()
        self._database_tab = DatabaseTab()
        self._debug_tab = DebugTab()
        self._experimental_tab = ExperimentalTab()

        self._stack.addWidget(self._general_tab)
        self._stack.addWidget(self._performance_tab)
        self._stack.addWidget(self._detection_tab)
        self._stack.addWidget(self._accounts_tab)
        self._stack.addWidget(self._database_tab)
        self._stack.addWidget(self._debug_tab)
        self._stack.addWidget(self._experimental_tab)

        self._general_tab.debug_mode_changed.connect(self._set_debug_visible)
        self._general_tab.experimental_mode_changed.connect(self._set_experimental_visible)
        self._general_tab.theme_changed.connect(self.theme_changed.emit)
        self._performance_tab.tab_transitions_changed.connect(self.tab_transitions_changed.emit)

        self._switch_to(0)
        return self._stack

    def _switch_to(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._tab_buttons):
            btn.setStyleSheet(_TAB_BTN_ACTIVE if i == index else _TAB_BTN)

    def focus_accounts_tab(self) -> None:
        self._switch_to(3)

    def bind_bootstrap_cleared(self, handler) -> None:
        if hasattr(self._accounts_tab, "bootstrap_cleared"):
            self._accounts_tab.bootstrap_cleared.connect(handler)

    def on_activated(self) -> None:
        self._load_all()

    def _load_all(self) -> None:
        self._general_tab.load()
        self._performance_tab.load()
        self._detection_tab.load()
        self._database_tab.load()
        self._debug_tab.load()
        self._experimental_tab.load()

        from backend.repository import db as _db

        self._set_debug_visible(_db.get_bool("debug_mode_enabled", False))
        self._set_experimental_visible(_db.get_bool("experimental_mode_enabled", False))

    def _set_debug_visible(self, enabled: bool) -> None:
        self._debug_tab_btn.setVisible(enabled)
        if not enabled and self._stack.currentIndex() == len(_TABS):
            self._switch_to(0)

    def _set_experimental_visible(self, enabled: bool) -> None:
        self._experimental_tab_btn.setVisible(enabled)
        if not enabled and self._stack.currentIndex() == len(_TABS) + 1:
            self._switch_to(0)

    def _export_settings(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Export Settings", "settings.json", "JSON Files (*.json)")
        if not path:
            return
        try:
            settings = db.export_settings()
            with open(path, "w") as fh:
                json.dump(settings, fh, indent=2)
            QMessageBox.information(self, "Exported", f"Settings saved to:\n{path}")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _import_settings(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Settings", "", "JSON Files (*.json)")
        if not path:
            return
        try:
            with open(path) as fh:
                settings = json.load(fh)
            db.import_settings(settings)
            self._load_all()
            QMessageBox.information(self, "Imported", "Settings imported successfully.")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))

