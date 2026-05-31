from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.ui_tokens import (
    FONT_SIZE_LABEL,
    SIZE_ICON_34,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    SIZE_CONTROL_22,
    SIZE_CONTROL_MID,
    SIZE_PANEL_W_MD,
    SPACE_3,
)
from frontend.styles._colors import (
    _TEXT_PRI,
    _TEXT_SEC,
)

from frontend.widgets.base.roster_card_base import (
    apply_roster_card_style,
    build_roster_card_layout,
)


class ProfileCard(QFrame):
    clicked = Signal(int)

    def __init__(
        self,
        profile: dict,
        is_active: bool = False,
        on_toggle_changed=None,
        parent=None,
    ):
        super().__init__(parent)
        self._profile_id = profile["id"]
        self._on_toggle = on_toggle_changed
        self._is_active = is_active
        self._build(profile, is_active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build(self, profile: dict, is_active: bool):
        ptype = profile.get("type", "email")
        enabled = bool(profile.get("enabled", 1))
        is_email = ptype == "email"

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_roster_card_style(self, "ProfileCard", is_active)
        left_layout, info, pills, right = build_roster_card_layout(self, pills_slot_width=SIZE_PANEL_W_MD)

        badge = QLabel()
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setStyleSheet("background: transparent; border: none;")
        icon_path = "frontend/assets/icons/email.png" if is_email else "frontend/assets/icons/webhook.png"
        badge_icon = QPixmap(icon_path)
        if not badge_icon.isNull():
            badge.setPixmap(
                badge_icon.scaled(
                    SIZE_ICON_34,
                    SIZE_ICON_34,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            badge.setText("EMAIL" if is_email else "WEBHOOK")
            badge.setStyleSheet(
                f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_MICRO}px; "
                f"font-weight: {FONT_WEIGHT_BOLD}; background: transparent; border: none;"
            )

        info.setSpacing(SPACE_3)
        left_layout.addWidget(badge, alignment=Qt.AlignmentFlag.AlignCenter)

        full_name = str(profile.get("name", "Unnamed") or "Unnamed")
        name_lbl = QLabel(full_name)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name_lbl.setMinimumWidth(0)
        name_lbl.setToolTip(full_name)
        nf = QFont()
        safe_set_point_size(nf, FONT_SIZE_LABEL)
        nf.setBold(True)
        name_lbl.setFont(nf)
        name_lbl.setStyleSheet(f"color: {_TEXT_PRI if enabled else _TEXT_SEC}; background: transparent;")
        info.addWidget(name_lbl)

        toggle = ToggleSwitch(width=SIZE_CONTROL_MID, height=SIZE_CONTROL_22)
        toggle.setChecked(enabled)
        toggle.toggled.connect(
            lambda v, pid=profile["id"]: (
                db.update_notification_profile(pid, enabled=1 if v else 0),
                self._on_toggle() if self._on_toggle else None,
            )
        )
        right.addWidget(toggle)
        self._toggle = toggle

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            child = self.childAt(event.pos())
            if child is not None and self._toggle.isAncestorOf(child):
                super().mousePressEvent(event)
                return
            self.clicked.emit(self._profile_id)
            event.accept()
            return
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        if self._is_active == active:
            return
        self._is_active = active
        apply_roster_card_style(self, "ProfileCard", active)
