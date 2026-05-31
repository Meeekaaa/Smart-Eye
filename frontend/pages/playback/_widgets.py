from __future__ import annotations

import os
from datetime import datetime

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QPushButton

from frontend.pages.rules_manager._constants import _DEL_DEFAULT_SS, _DEL_CONFIRM_SS
from frontend.icon_theme import themed_icon_pixmap
from frontend.styles._colors import _ACCENT_HI_BG_07, _BORDER_DIM, _TEXT_PRI, _TEXT_MUTED
from frontend.ui_tokens import FONT_SIZE_CAPTION, FONT_SIZE_MICRO, FONT_WEIGHT_BOLD, RADIUS_MD, SIZE_ROW_XL
from frontend.widgets.base.roster_card_base import apply_roster_card_style, build_roster_card_layout
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton


class ClipRowWidget(QFrame):
    clicked = Signal()

    def __init__(self, name: str, tag: str, ts: float, path: str, parent=None):
        super().__init__(parent)
        self._path = path
        self._active = False
        self.setFixedHeight(SIZE_ROW_XL)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._build(name, tag, ts)

    def _build(self, name: str, tag: str, ts: float) -> None:
        apply_roster_card_style(self, "ClipCard", is_active=self._active)
        left_layout, info_col, pills_row, right_row = build_roster_card_layout(self)

        left_cell = self.findChild(QFrame, "RosterLeft")
        if left_cell:
            left_cell.setVisible(False)
        for child in self.findChildren(QFrame):
            if child.frameShape() == QFrame.Shape.VLine:
                child.setVisible(False)

        title = QLabel(name)
        title.setStyleSheet(f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD};")
        info_col.addWidget(title)

        ts_text = datetime.fromtimestamp(ts).strftime("%b %d, %Y  %H:%M")
        subtitle = QLabel(ts_text)
        subtitle.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px;")
        info_col.addWidget(subtitle)



        self._delete_btn = ConfirmDeleteButton("Delete", "Sure?")
        self._delete_btn.set_button_styles(_DEL_DEFAULT_SS, _DEL_CONFIRM_SS)
        right_row.addWidget(self._delete_btn)

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        apply_roster_card_style(self, "ClipCard", is_active=active)

    def set_delete_callback(self, fn) -> None:
        self._delete_btn.set_confirm_callback(fn)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class SnapshotRowWidget(QFrame):
    selected = Signal()
    delete_requested = Signal()
    _ROW_HEIGHT = SIZE_ROW_XL + 34

    def __init__(self, path: str, ts: int, camera_name: str | None = None, rule_text: str | None = None, parent=None):
        super().__init__(parent)
        self._path = path
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(self._ROW_HEIGHT)
        self._build(ts, camera_name or "Unknown Camera", rule_text or "No rule context")

    def _build(self, ts: int, camera_name: str, rule_text: str) -> None:
        self._apply_style(False)
        left_layout, info_col, _pills_row, _right_row = build_roster_card_layout(self)
        self._sync_card_geometry()

        left_cell = self.findChild(QFrame, "RosterLeft")
        if left_cell:
            left_cell.setFixedWidth(112)

        thumb = QLabel()
        thumb.setFixedSize(96, self._ROW_HEIGHT - 12)
        thumb.setStyleSheet(f"border: 1px solid {_BORDER_DIM}; border-radius: {RADIUS_MD}px;")
        pix = QPixmap(self._path)
        if not pix.isNull():
            thumb.setPixmap(
                pix.scaled(
                    QSize(96, self._ROW_HEIGHT - 12),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        left_layout.addWidget(thumb)

        title = QLabel(self._compact_text(camera_name, 28))
        title.setStyleSheet(f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD};")
        title.setWordWrap(False)
        title.setToolTip(camera_name)
        info_col.addWidget(title)

        when_text = datetime.fromtimestamp(max(0, int(ts))).strftime("%b %d, %Y  %H:%M")
        when = QLabel(when_text)
        when.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_MICRO}px;")
        when.setWordWrap(False)
        info_col.addWidget(when)

        rule_line = QLabel(f"Rule: {self._compact_text(rule_text, 24)}")
        rule_line.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_MICRO}px;")
        rule_line.setWordWrap(False)
        rule_line.setToolTip(rule_text)
        info_col.addWidget(rule_line)

        filename = os.path.basename(self._path)
        file_line = QLabel(f"File: {self._compact_text(filename, 20)}")
        file_line.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_MICRO}px;")
        file_line.setWordWrap(False)
        file_line.setToolTip(self._path)
        info_col.addWidget(file_line)

        self._delete_btn = QPushButton(self)
        self._delete_btn.setFixedSize(22, 22)
        self._delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._delete_btn.setToolTip("Delete snapshot")
        self._delete_btn.setStyleSheet(
            f"QPushButton{{border:none;background:transparent;border-radius:{RADIUS_MD}px;padding:0;}}"
            f"QPushButton:hover{{background:{_ACCENT_HI_BG_07};}}"
            "QPushButton:pressed{background:transparent;}"
        )
        x_pix = themed_icon_pixmap("frontend/assets/icons/x.png", 14, 14)
        if not x_pix.isNull():
            self._delete_btn.setIcon(QIcon(x_pix))
        else:
            self._delete_btn.setIcon(QIcon("frontend/assets/icons/x.png"))
        self._delete_btn.setIconSize(QSize(14, 14))
        self._delete_btn.clicked.connect(self.delete_requested.emit)
        self._delete_btn.raise_()
        self._position_delete_button()

    def _sync_card_geometry(self) -> None:
        self.setFixedHeight(self._ROW_HEIGHT)
        left_cell = self.findChild(QFrame, "RosterLeft")
        if left_cell:
            left_cell.setFixedHeight(self._ROW_HEIGHT)
        for child in self.findChildren(QFrame):
            if child.frameShape() == QFrame.Shape.VLine:
                child.setFixedHeight(self._ROW_HEIGHT)

    def _position_delete_button(self) -> None:
        if not hasattr(self, "_delete_btn"):
            return
        pad = 8
        self._delete_btn.move(max(pad, self.width() - self._delete_btn.width() - pad), pad)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_delete_button()

    @staticmethod
    def _compact_text(text: str, max_len: int) -> str:
        value = str(text or "").strip()
        if len(value) <= max_len:
            return value
        return f"{value[:max(0, max_len - 3)]}..."

    def _apply_style(self, active: bool) -> None:
        apply_roster_card_style(self, "SnapshotCard", is_active=active)
        self._sync_card_geometry()

    def set_active(self, active: bool) -> None:
        if self._active == active:
            return
        self._active = active
        self._apply_style(active)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit()
        super().mousePressEvent(event)
