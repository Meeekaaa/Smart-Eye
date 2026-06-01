from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
)

from ._constants import (
    _AVATAR_BG_COLORS,
    _AVATAR_FG_COLORS,
    _make_rounded_pixmap,
    _short_display_name,
)
from frontend.styles._colors import (
    _ACCENT_BG_10,
    _ACCENT_HI,
    _MUTED_BG_10,
    _SUCCESS,
    _SUCCESS_BG_14,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)

from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.ui_tokens import (
    FONT_SIZE_LABEL,
    FONT_SIZE_LARGE,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_HEAVY,
    RADIUS_LG,
    SIZE_BTN_W_62,
    SIZE_CONTROL_22,
    SIZE_CONTROL_MID,
    SIZE_CONTROL_XS,
    SIZE_PANEL_W_MD,
    SIZE_ROW_XL,
    SIZE_ICON_64,
    SPACE_SM,
    SPACE_XXS,
)
from frontend.widgets.base.roster_card_base import (
    apply_roster_card_style,
    build_roster_card_layout,
)


class ClickableFrame(QFrame):
    clicked = Signal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class RosterRowWidget(QFrame):
    clicked = Signal(int)
    enabled_toggled = Signal(int, bool)

    def __init__(self, face: dict, is_active: bool = False, parent=None):
        super().__init__(parent)
        self._face_id = face["id"]
        self._is_active = is_active
        self._face = face
        self._build(face, is_active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build(self, face: dict, is_active: bool):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        is_authorized = face.get("authorized_cameras", "[]") != "[]"
        is_enabled = bool(face.get("enabled", 1))
        color_idx = face.get("id", 0) % len(_AVATAR_BG_COLORS)
        fg_color = _AVATAR_FG_COLORS[color_idx]
        bg_dark, bg_light = _AVATAR_BG_COLORS[color_idx]

        apply_roster_card_style(self, "RosterCard", is_active)
        left_layout, info_col, pills, right = build_roster_card_layout(self, pills_slot_width=SIZE_PANEL_W_MD)
        pills_wrap = pills.parentWidget()
        if pills_wrap is not None:
            pills_wrap.setFixedWidth(0)
            pills_wrap.hide()

        avatar = QLabel()

        avatar_size = min(SIZE_ICON_64, max(32, SIZE_ROW_XL - 18))
        avatar_rad = avatar_size // 2
        avatar.setFixedSize(avatar_size, avatar_size)
        avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
        initial = (face.get("name") or "?")[0].upper()
        pix = _make_rounded_pixmap(face.get("image_path", ""), avatar_size, avatar_rad)
        if pix:
            avatar.setPixmap(
                pix.scaled(avatar_size, avatar_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        else:
            avatar.setText(initial)
            avatar.setStyleSheet(f"""
                border-radius: {avatar_rad}px;
                background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg_light}, stop:1 {bg_dark});
                color: {fg_color}; font-size: {FONT_SIZE_LARGE}px; font-weight: {FONT_WEIGHT_HEAVY};
            """)
        left_layout.addWidget(avatar, alignment=Qt.AlignmentFlag.AlignCenter)
        info_col.setSpacing(SPACE_XXS)

        display_name = _short_display_name(face.get("name", ""))
        name_lbl = QLabel(display_name)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name_lbl.setMinimumWidth(0)
        name_lbl.setToolTip(display_name)
        name_lbl.setStyleSheet(
            f"font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_BOLD}; "
            f"color: {_TEXT_PRI if is_enabled else _TEXT_MUTED}; background: transparent;"
        )
        info_col.addWidget(name_lbl)

        status_pill = QLabel("AUTHORIZED" if is_authorized else "RESTRICTED")
        status_pill.setFixedHeight(SIZE_CONTROL_XS)
        status_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if is_authorized:
            status_pill.setStyleSheet(f"""
                color: {_SUCCESS}; background-color: {_SUCCESS_BG_14};
                border: none; border-radius: {RADIUS_LG}px;
                padding: 0 {SPACE_SM}px; font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD};
            """)
        else:
            status_pill.setStyleSheet(f"""
                color: {_TEXT_SEC}; background-color: {_MUTED_BG_10};
                border: none; border-radius: {RADIUS_LG}px;
                padding: 0 {SPACE_SM}px; font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD};
            """)
        if is_authorized:
            status_pill.setText("AUTH")
        else:
            status_pill.setText("REST")
        status_pill.setFixedWidth(SIZE_BTN_W_62)
        right.addWidget(status_pill)

        uid = str(face.get("uuid") or "")
        uid_pill = QLabel(f"{uid[:6] if uid else '------'}")
        uid_pill.setFixedHeight(SIZE_CONTROL_XS)
        uid_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
        uid_pill.setStyleSheet(f"""
            color: {_ACCENT_HI}; background-color: {_ACCENT_BG_10};
            border: none; border-radius: {RADIUS_LG}px;
            padding: 0 {SPACE_SM}px; font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD};
            font-family: 'JetBrains Mono', 'Consolas', monospace;
        """)
        uid_pill.setFixedWidth(SIZE_BTN_W_62)
        right.addWidget(uid_pill)

        toggle = ToggleSwitch(width=SIZE_CONTROL_MID, height=SIZE_CONTROL_22)
        toggle.setChecked(is_enabled)
        toggle.setToolTip("Enable / disable face recognition for this person")
        toggle.toggled.connect(lambda state: self.enabled_toggled.emit(self._face_id, state))
        right.addWidget(toggle)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._face_id)
        super().mousePressEvent(event)
