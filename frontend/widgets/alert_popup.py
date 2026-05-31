from __future__ import annotations

import contextlib
import time

from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from frontend.styles._colors import (
    _BG_OVERLAY,
    _BG_RAISED,
    _DANGER,
    _DANGER_BG_14,
    _DANGER_BORDER_55,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.styles._shadows import apply_shadow_float
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_HEADING,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_14,
    RADIUS_18,
    SIZE_DIALOG_W_MD,
    SIZE_OFFSET_LG,
    SPACE_18,
    SPACE_20,
    SPACE_6,
    SPACE_MD,
    SPACE_SM,
    SPACE_XXXS,
)

_ACTIVE_POPUP: AlertPopup | None = None
_LAST_SHOW_TS = 0.0
_SUPPRESSED_COUNT = 0


class AlertPopup(QFrame):
    def __init__(self, parent: QWidget, title: str, subtitle: str, count: int = 1):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.ToolTip
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(SIZE_DIALOG_W_MD + 80)
        self.setStyleSheet("QFrame { background: transparent; border: none; }")
        self._count = max(1, int(count or 1))

        apply_shadow_float(self, _DANGER)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.content_frame = QFrame(self)
        self.content_frame.setStyleSheet(
            """
            QFrame {{
                background: {bg};
                border: {border_w}px solid {border};
                border-radius: {radius}px;
            }}
            """.format(bg=_BG_RAISED, border_w=SPACE_XXXS, border=_DANGER_BORDER_55, radius=RADIUS_18)
        )

        content_layout = QHBoxLayout(self.content_frame)
        content_layout.setContentsMargins(SPACE_20, SPACE_18, SPACE_20, SPACE_18)
        content_layout.setSpacing(SPACE_MD)

        badge = QLabel("!", self.content_frame)
        badge.setFixedSize(34, 34)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet(
            """
            QLabel {{
                background: {bg};
                border: {border_w}px solid {border};
                border-radius: 17px;
                color: {color};
                font-weight: 800;
                font-size: 18px;
            }}
            """.format(bg=_DANGER_BG_14, border_w=SPACE_XXXS, border=_DANGER_BORDER_55, color=_DANGER)
        )
        content_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignTop)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(SPACE_6)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(SPACE_SM)

        self.title_label = QLabel(title, self.content_frame)
        self.title_label.setStyleSheet(
            """
            QLabel {{
                color: {color};
                font-weight: {weight};
                font-size: {size}px;
                background: transparent;
                border: none;
            }}
            """.format(color=_DANGER, weight=FONT_WEIGHT_SEMIBOLD, size=FONT_SIZE_HEADING)
        )
        self.title_label.setWordWrap(True)
        header_row.addWidget(self.title_label, stretch=1)

        self.count_label = QLabel("", self.content_frame)
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.count_label.setFixedHeight(24)
        self.count_label.setMinimumWidth(34)
        self.count_label.setStyleSheet(
            """
            QLabel {{
                background: {bg};
                border: {border_w}px solid {border};
                border-radius: 12px;
                color: {color};
                font-size: 12px;
                font-weight: 700;
                padding: 0 8px;
            }}
            """.format(bg=_BG_OVERLAY, border_w=SPACE_XXXS, border=_DANGER_BORDER_55, color=_TEXT_PRI)
        )
        header_row.addWidget(self.count_label, alignment=Qt.AlignmentFlag.AlignTop)
        text_col.addLayout(header_row)

        self.subtitle_label = QLabel(subtitle, self.content_frame)
        self.subtitle_label.setStyleSheet(
            """
            QLabel {{
                color: {color};
                font-size: {size}px;
                background: transparent;
                border: none;
            }}
            """.format(color=_TEXT_PRI, size=FONT_SIZE_BODY)
        )
        self.subtitle_label.setWordWrap(True)
        text_col.addWidget(self.subtitle_label)

        self.meta_label = QLabel("", self.content_frame)
        self.meta_label.setStyleSheet(
            """
            QLabel {{
                color: {color};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
            """.format(color=_TEXT_SEC)
        )
        text_col.addWidget(self.meta_label)

        content_layout.addLayout(text_col, stretch=1)
        root.addWidget(self.content_frame)

        self._close_timer = QTimer(self)
        self._close_timer.setSingleShot(True)
        self._close_timer.timeout.connect(self.close)
        self._anim = None
        self.update_content(title, subtitle, self._count)

    def update_content(self, title: str, subtitle: str, count: int = 1) -> None:
        self._count = max(1, int(count or 1))
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        if self._count > 1:
            self.count_label.setText(f"{self._count} new")
            self.count_label.setVisible(True)
            self.meta_label.setText("Grouped alert burst")
        else:
            self.count_label.setVisible(False)
            self.meta_label.setText("New violation")
        self.adjustSize()
        self._close_timer.start(8000)

    def paintEvent(self, event):
        super().paintEvent(event)

        if not hasattr(self, "content_frame"):
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        frame_rect = self.content_frame.geometry()
        x = frame_rect.x()
        y = frame_rect.y()
        w = frame_rect.width()
        h = frame_rect.height()

        outline_color = QColor(_DANGER)
        outline_color.setAlphaF(0.24)
        painter.setPen(QPen(outline_color, 1.3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(x + SPACE_6, y + SPACE_6, w - SPACE_MD, h - SPACE_MD, RADIUS_14, RADIUS_14)

    def closeEvent(self, event):
        global _ACTIVE_POPUP
        if _ACTIVE_POPUP is self:
            _ACTIVE_POPUP = None
        super().closeEvent(event)


def _popup_position(parent: QWidget, offset: int) -> QPoint:
    rect = parent.geometry()
    return parent.mapToGlobal(QPoint(rect.left() + offset, rect.top() + offset))


def show_alert(parent: QWidget, title: str, subtitle: str, offset: int = 16, cooldown_ms: int = 9000) -> None:
    global _ACTIVE_POPUP, _LAST_SHOW_TS, _SUPPRESSED_COUNT
    if parent is None:
        return

    now = time.monotonic()
    if _ACTIVE_POPUP is not None and _ACTIVE_POPUP.isVisible():
        current_count = getattr(_ACTIVE_POPUP, "_count", 1)
        _ACTIVE_POPUP.update_content(title, subtitle, current_count + 1)
        with contextlib.suppress(Exception):
            _ACTIVE_POPUP.move(_popup_position(parent, offset))
        return

    if now - _LAST_SHOW_TS < max(0.0, float(cooldown_ms) / 1000.0):
        _SUPPRESSED_COUNT += 1
        return

    count = _SUPPRESSED_COUNT + 1
    _SUPPRESSED_COUNT = 0
    _LAST_SHOW_TS = now

    popup = AlertPopup(parent, title, subtitle, count=count)
    _ACTIVE_POPUP = popup
    try:
        end_pos = _popup_position(parent, offset)
        start_pos = QPoint(end_pos.x() - SIZE_OFFSET_LG, end_pos.y())
        popup.move(start_pos)
        popup.show()
        anim = QPropertyAnimation(popup, b"pos", popup)
        anim.setDuration(520)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(start_pos)
        anim.setEndValue(end_pos)
        popup._anim = anim
        anim.start()
    except (AttributeError, RuntimeError):
        popup.move(parent.mapToGlobal(QPoint(0, 0)))
        popup.show()
