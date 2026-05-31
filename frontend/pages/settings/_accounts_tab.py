from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QFileDialog,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.navigation import nav_keys, nav_label_map
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.widgets.checkbox_style import CHECKBOX_STYLE
from frontend.widgets.password_visibility import attach_password_visibility_toggle
from frontend.styles._colors import _BG_CHECK, _BG_NAV_ALT, _BG_NAV_DARK, _TEXT_PRI, _TEXT_SEC
from utils.auth_validation import get_email_validation_error
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_20,
    RADIUS_LG,
    SIZE_ROW_MD,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXXS,
)
from ._constants import (
    _BTN_H,
    _DANGER_BTN,
    _PRIMARY_BTN,
    _SECONDARY_BTN,
    _STYLESHEET,
    _FIELD_H,
    _make_sdiv,
    _srow,
)

_ACCOUNT_ICON = "frontend/assets/icons/account.png"


class AccountsTab(QWidget):
    bootstrap_cleared = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET + CHECKBOX_STYLE)
        self._editing_id: int | None = None
        self._editing_account: dict | None = None
        self._tab_checks: dict[str, QCheckBox] = {}
        self._build_ui()
        self._load_accounts()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet("QWidget { background: transparent; border: none; }")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, SPACE_XL)
        bl.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        bl.addWidget(_make_sdiv("Account access"))

        self._email_input = QLineEdit()
        self._email_input.setPlaceholderText("user@example.com")
        self._email_input.setFixedHeight(_FIELD_H)

        self._username_input = QLineEdit()
        self._username_input.setPlaceholderText("Optional")
        self._username_input.setFixedHeight(_FIELD_H)

        self._password_input = QLineEdit()
        self._password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._password_input.setPlaceholderText("Set a password")
        self._password_input.setFixedHeight(_FIELD_H)
        attach_password_visibility_toggle(self._password_input)

        self._confirm_input = QLineEdit()
        self._confirm_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._confirm_input.setPlaceholderText("Confirm password")
        self._confirm_input.setFixedHeight(_FIELD_H)
        attach_password_visibility_toggle(self._confirm_input)

        self._admin_toggle = ToggleSwitch()
        self._avatar_path = QLineEdit()
        self._avatar_path.setPlaceholderText("frontend/assets/icons/avatar.png")
        avatar_btn = QPushButton("Browse…")
        avatar_btn.setFixedHeight(_BTN_H)
        avatar_btn.setStyleSheet(_SECONDARY_BTN)
        avatar_btn.clicked.connect(self._pick_avatar)
        avatar_row = QHBoxLayout()
        avatar_row.addWidget(self._avatar_path)
        avatar_row.addWidget(avatar_btn)

        bl.addWidget(_srow("Email", self._email_input))
        bl.addWidget(_srow("Username", self._username_input))
        bl.addWidget(_srow("Password", self._password_input, hint="Required for new accounts. Leave blank to keep current password."))
        bl.addWidget(_srow("Confirm", self._confirm_input))
        bl.addWidget(_srow("Administrator", self._admin_toggle, hint="Admins can open every tab regardless of restrictions."))
        bl.addWidget(_srow("Avatar image", self._wrap_layout_widget(avatar_row), hint="Optional; shown in sidebar badge."))

        bl.addWidget(_make_sdiv("Recovery"))

        self._q1 = QLineEdit()
        self._q1.setPlaceholderText("What is your pet's name?")
        self._a1 = QLineEdit()
        self._a1.setEchoMode(QLineEdit.EchoMode.Password)
        attach_password_visibility_toggle(self._a1)
        bl.addWidget(_srow("Question 1", self._q1))
        bl.addWidget(_srow("Answer 1", self._a1))

        self._q2 = QLineEdit()
        self._q2.setPlaceholderText("In what city were you born?")
        self._a2 = QLineEdit()
        self._a2.setEchoMode(QLineEdit.EchoMode.Password)
        attach_password_visibility_toggle(self._a2)
        bl.addWidget(_srow("Question 2", self._q2))
        bl.addWidget(_srow("Answer 2", self._a2))

        self._q3 = QLineEdit()
        self._q3.setPlaceholderText("What is your favorite color?")
        self._a3 = QLineEdit()
        self._a3.setEchoMode(QLineEdit.EchoMode.Password)
        attach_password_visibility_toggle(self._a3)
        bl.addWidget(_srow("Question 3", self._q3))
        bl.addWidget(_srow("Answer 3", self._a3))

        perms_frame = QFrame()
        perms_layout = QVBoxLayout(perms_frame)
        perms_layout.setContentsMargins(SPACE_20, SPACE_SM, SPACE_20, SPACE_MD)
        perms_layout.setSpacing(SPACE_SM)
        perms_title = QLabel("Allowed tabs")
        perms_title.setStyleSheet(
            f"QLabel {{ color: {_TEXT_PRI}; font-weight: {FONT_WEIGHT_SEMIBOLD}; font-size: {FONT_SIZE_BODY}px; background: transparent; border: none; }}"
        )
        perms_layout.addWidget(perms_title)

        grid = QGridLayout()
        grid.setContentsMargins(0, SPACE_XS, 0, 0)
        grid.setHorizontalSpacing(SPACE_14)
        grid.setVerticalSpacing(SPACE_6)
        labels = nav_label_map()
        for idx, key in enumerate(nav_keys()):
            cb = QCheckBox(labels.get(key, key.title()))
            cb.setStyleSheet(f"QCheckBox {{ color: {_TEXT_PRI}; font-size: {FONT_SIZE_LABEL}px; background: transparent; border: none; }}")
            self._tab_checks[key] = cb
            row = idx // 2
            col = idx % 2
            grid.addWidget(cb, row, col)
        perms_layout.addLayout(grid)
        bl.addWidget(perms_frame)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(SPACE_20, SPACE_MD, SPACE_20, SPACE_XS)
        action_row.setSpacing(SPACE_10)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"QLabel {{ color: {_TEXT_SEC}; background: transparent; border: none; }}")
        action_row.addWidget(self._status_lbl)
        action_row.addStretch()

        self._save_btn = QPushButton("Save account")
        self._save_btn.setFixedHeight(_BTN_H)
        self._save_btn.setStyleSheet(_PRIMARY_BTN)
        self._save_btn.clicked.connect(self._handle_save)
        action_row.addWidget(self._save_btn)

        reset_btn = QPushButton("Reset")
        reset_btn.setFixedHeight(_BTN_H)
        reset_btn.setStyleSheet(_SECONDARY_BTN)
        reset_btn.clicked.connect(self._reset_form)
        action_row.addWidget(reset_btn)

        bl.addLayout(action_row)

        bl.addWidget(_make_sdiv("Existing accounts"))

        self._list_container = QWidget()
        self._list_container.setStyleSheet("QWidget { background: transparent; border: none; }")
        self._list_layout = QVBoxLayout(self._list_container)
        self._list_layout.setContentsMargins(SPACE_20, SPACE_SM, SPACE_20, SPACE_SM)
        self._list_layout.setSpacing(SPACE_10)
        bl.addWidget(self._list_container)

        bl.addStretch()

    def _reset_form(self):
        self._editing_id = None
        self._editing_account = None
        self._email_input.clear()
        self._username_input.clear()
        self._password_input.clear()
        self._confirm_input.clear()
        self._admin_toggle.setChecked(False)
        for cb in self._tab_checks.values():
            cb.setChecked(False)
        self._q1.clear()
        self._q2.clear()
        self._q3.clear()
        self._a1.clear()
        self._a2.clear()
        self._a3.clear()
        self._avatar_path.clear()
        self._save_btn.setText("Save account")
        self._status_lbl.setText("")

    def _set_tabs_from_list(self, tabs: list[str]):
        for key, cb in self._tab_checks.items():
            cb.setChecked(key in tabs)

    def _collect_tabs(self) -> list[str]:
        return [key for key, cb in self._tab_checks.items() if cb.isChecked()]

    def _handle_save(self):
        was_bootstrap = db.get_bool("bootstrap_password_active", False)
        email = self._email_input.text().strip()
        username = self._username_input.text().strip()
        password = self._password_input.text()
        confirm = self._confirm_input.text()
        tabs = self._collect_tabs()
        is_admin = self._admin_toggle.isChecked()
        is_new = self._editing_id is None
        email_error = get_email_validation_error(email, allow_internal=True)
        if email_error:
            self._status_lbl.setText(email_error)
            return
        if is_new and not password:
            self._status_lbl.setText("Password is required for new accounts.")
            return
        if password or confirm:
            if password != confirm:
                self._status_lbl.setText("Passwords do not match.")
                return
        if not is_admin and not tabs:
            self._status_lbl.setText("Select at least one tab for limited accounts.")
            return
        questions = [self._q1.text().strip(), self._q2.text().strip(), self._q3.text().strip()]
        answers = [self._a1.text(), self._a2.text(), self._a3.text()]
        any_answer = any(a.strip() for a in answers)
        if is_new:
            if any(not q for q in questions) or any(not a for a in answers):
                self._status_lbl.setText("Security questions and answers are required.")
                return
            security_payload = (questions, answers)
        else:
            if any_answer:
                if any(not q for q in questions) or any(not a for a in answers):
                    self._status_lbl.setText("Provide all questions and answers or leave answers blank to keep existing ones.")
                    return
                security_payload = (questions, answers)
            else:
                security_payload = None
        avatar_path = self._avatar_path.text().strip()
        try:
            if is_new:
                db.create_account(
                    email,
                    password,
                    tabs,
                    is_admin=is_admin,
                    security=(questions, answers),
                    avatar_path=avatar_path,
                    username=username,
                )
                self._status_lbl.setText("Account created.")
            else:
                db.update_account(
                    self._editing_id,
                    email=email,
                    username=username,
                    password=password or None,
                    allowed_tabs=tabs,
                    is_admin=is_admin,
                    security=security_payload,
                    avatar_path=avatar_path,
                )
                self._status_lbl.setText("Account updated.")
            db.set_setting("auth_onboarded", True)
            if was_bootstrap and not db.get_bool("bootstrap_password_active", False):
                self.bootstrap_cleared.emit()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            self._status_lbl.setText(str(exc))
            return
        self._load_accounts()
        self._reset_form()

    def _load_accounts(self):
        accounts = db.get_accounts()
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
        if not accounts:
            empty = QLabel("No accounts yet. Create one above.")
            empty.setStyleSheet(f"QLabel {{ color: {_TEXT_SEC}; background: transparent; border: none; }}")
            self._list_layout.addWidget(empty)
            return
        for acc in accounts:
            self._list_layout.addWidget(self._make_account_card(acc))
        self._list_layout.addStretch()

    def _pick_avatar(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select avatar", "", "Images (*.png *.jpg *.jpeg *.bmp)")
        if path:
            self._avatar_path.setText(path)

    def _wrap_layout_widget(self, layout: QHBoxLayout) -> QWidget:
        w = QWidget()
        w.setLayout(layout)
        w.setStyleSheet("background: transparent;")
        return w

    def _make_account_card(self, acc: dict) -> QWidget:
        card = QFrame()
        card.setStyleSheet(
            f"QFrame {{ background: {_BG_CHECK}; border: {SPACE_XXXS}px solid {_BG_NAV_ALT}; border-radius: {RADIUS_LG}px; }}"
        )
        row = QHBoxLayout(card)
        row.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        row.setSpacing(SPACE_10)

        info_col = QVBoxLayout()
        email_lbl = QLabel(acc.get("email", ""))
        email_lbl.setStyleSheet(
            f"QLabel {{ color: {_TEXT_PRI}; font-weight: {FONT_WEIGHT_SEMIBOLD}; font-size: {FONT_SIZE_BODY}px; background: transparent; border: none; }}"
        )
        info_col.addWidget(email_lbl)

        username = (acc.get("username") or "").strip()
        if username:
            username_lbl = QLabel(f"@{username}")
            username_lbl.setStyleSheet(
                f"QLabel {{ color: {_TEXT_SEC}; font-size: {FONT_SIZE_CAPTION}px; background: transparent; border: none; }}"
            )
            info_col.addWidget(username_lbl)

        role = "Administrator" if acc.get("is_admin") else "Limited"
        role_lbl = QLabel(role)
        role_lbl.setStyleSheet(f"QLabel {{ color: {_TEXT_SEC}; font-size: {FONT_SIZE_CAPTION}px; background: transparent; border: none; }}")
        info_col.addWidget(role_lbl)

        tabs = acc.get("allowed_tabs") or []
        if acc.get("is_admin"):
            tabs_text = "All tabs"
        else:
            tabs_text = ", ".join(nav_label_map().get(t, t.title()) for t in tabs) or "No access"
        tabs_lbl = QLabel(tabs_text)
        tabs_lbl.setStyleSheet(f"QLabel {{ color: {_TEXT_SEC}; font-size: {FONT_SIZE_CAPTION}px; background: transparent; border: none; }}")
        info_col.addWidget(tabs_lbl)

        avatar_lbl = QLabel()
        avatar_lbl.setFixedSize(SIZE_ROW_MD, SIZE_ROW_MD)
        avatar_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        avatar_lbl.setStyleSheet(
            f"QLabel {{ border-radius: {RADIUS_20}px; background: {_BG_NAV_DARK}; border: {SPACE_XXXS}px solid {_BG_NAV_ALT}; }}"
        )

        def _rounded_pix(path: str, size: int) -> QPixmap | None:
            pm = QPixmap(path)
            if pm.isNull():
                return None
            scaled = pm.scaled(
                size,
                size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            rounded = QPixmap(size, size)
            rounded.fill(Qt.GlobalColor.transparent)
            painter = QPainter(rounded)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            clip = QPainterPath()
            clip.addEllipse(0, 0, size, size)
            painter.setClipPath(clip)
            painter.drawPixmap(0, 0, scaled)
            painter.end()
            return rounded

        avatar_pm = None
        if acc.get("avatar_path"):
            avatar_pm = _rounded_pix(acc.get("avatar_path"), 40)
        if avatar_pm is None:
            pm = QPixmap(_ACCOUNT_ICON)
            if not pm.isNull():
                avatar_pm = pm.scaled(28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                avatar_lbl.setStyleSheet(
                    f"QLabel {{ border-radius: {RADIUS_20}px; background: {_BG_NAV_DARK}; border: {SPACE_XXXS}px solid {_BG_NAV_ALT}; padding: {SPACE_XS}px; }}"
                )

        if avatar_pm:
            avatar_lbl.setPixmap(avatar_pm)
        row.addWidget(avatar_lbl)
        row.addLayout(info_col)
        row.addStretch()

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(_BTN_H)
        edit_btn.setStyleSheet(_SECONDARY_BTN)
        edit_btn.clicked.connect(lambda _, a=acc: self._on_edit_account(a))
        row.addWidget(edit_btn)

        del_btn = ConfirmDeleteButton("Delete", "Sure?")
        del_btn.setFixedHeight(_BTN_H)
        del_btn.set_button_styles(_DANGER_BTN, _DANGER_BTN)
        del_btn.set_confirm_callback(lambda a=acc: self._on_delete_account(a))
        row.addWidget(del_btn)

        return card

    def _on_edit_account(self, acc: dict):
        self._editing_id = acc.get("id")
        self._editing_account = acc
        self._email_input.setText(acc.get("email", ""))
        self._username_input.setText(acc.get("username", "") or "")
        self._password_input.clear()
        self._confirm_input.clear()
        self._admin_toggle.setChecked(bool(acc.get("is_admin")))
        self._set_tabs_from_list(acc.get("allowed_tabs") or [])
        self._q1.setText(acc.get("sec_q1", ""))
        self._q2.setText(acc.get("sec_q2", ""))
        self._q3.setText(acc.get("sec_q3", ""))
        self._a1.clear()
        self._a2.clear()
        self._a3.clear()
        self._avatar_path.setText(acc.get("avatar_path", ""))
        self._save_btn.setText("Update account")
        self._status_lbl.setText("")

    def _on_delete_account(self, acc: dict):
        accounts = db.get_accounts()
        if len(accounts) <= 1:
            QMessageBox.warning(self, "Blocked", "At least one account is required.")
            return
        try:
            db.delete_account(acc.get("id"))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self._load_accounts()

