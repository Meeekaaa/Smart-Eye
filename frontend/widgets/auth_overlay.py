from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QVBoxLayout

from frontend.styles._colors import _BG_BASE_92
from frontend.widgets.auth_login_card import AuthLoginCard
from frontend.widgets.auth_reset_card import AuthResetCard
from frontend.widgets.animated_stack import AnimatedStackedWidget


class AuthOverlay(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("QFrame {{ background: {}; }}".format(_BG_BASE_92))

        self.login_card = AuthLoginCard(self)
        self.reset_card = AuthResetCard(self)

        self.stack = AnimatedStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background: transparent; }")
        self.stack.addWidget(self.login_card)
        self.stack.addWidget(self.reset_card)
        self.resize_stack(self.login_card)

        ov_l = QVBoxLayout(self)
        ov_l.setContentsMargins(0, 0, 0, 0)
        ov_l.addStretch()
        ov_l.addWidget(self.stack, alignment=Qt.AlignmentFlag.AlignHCenter)
        ov_l.addStretch()

    def resize_stack(self, widget):
        if not widget:
            return
        hint = widget.sizeHint()
        min_w = widget.minimumWidth()
        min_h = widget.minimumHeight()
        self.stack.setFixedSize(
            max(hint.width(), min_w),
            max(hint.height(), min_h),
        )

    def show_login(self):
        self.resize_stack(self.login_card)
        self.stack.setCurrentWidget(self.login_card)
        self.login_card.set_error("")
        self.reset_card.set_error("")

    def show_reset(self):
        self.resize_stack(self.reset_card)
        self.stack.setCurrentWidget(self.reset_card)
        self.reset_card.set_error("")
