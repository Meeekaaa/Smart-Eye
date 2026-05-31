from __future__ import annotations

import logging

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from shiboken6 import isValid

from backend.repository import db
from backend.notifications.email_notifier import test_email
from backend.notifications.webhook_notifier import test_webhook
from frontend.app_theme import safe_set_point_size
from frontend.services.notification_validation import validate_notification_target
from frontend.styles._hero_header import make_hero_header
from frontend.styles._banner_styles import make_edit_banner
from frontend.styles._btn_styles import _SECONDARY_BTN
from frontend.styles.page_styles import divider_style, muted_label_style, section_kicker_style, text_style, transparent_surface_style
from frontend.widgets.toast import show_toast
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.widgets.password_visibility import attach_password_visibility_toggle
from frontend.widgets.action_feedback import (
    build_status_label,
    flash_status,
    make_close_button,
    make_manager_footer_layout,
    make_save_button,
)

from frontend.styles._input_styles import _FORM_INPUT_TITLE
from frontend.styles._colors import (
    _ACCENT_BG_08,
    _ACCENT_BG_12,
    _ACCENT_HI,
    _ACCENT_HI_BG_18,
    _BG_RAISED,
    _BG_SURFACE,
    _BORDER_DIM,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    RADIUS_6,
    RADIUS_LG,
    SIZE_BTN_W_72,
    SIZE_BTN_W_88,
    SIZE_BTN_W_MD,
    SIZE_BTN_W_SM,
    SIZE_BTN_W_80,
    SIZE_CONTROL_32,
    SIZE_CONTROL_MD,
    SIZE_LABEL_W,
    SIZE_ROW_LG,
    SIZE_ROW_72,
    SPACE_LG,
    SPACE_10,
    SPACE_XXS,
    SPACE_20,
    SPACE_3,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    SPACE_XL,
    SPACE_XXL,
    SPACE_XXXS,
)
from ._constants import (
    _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST,
    _TEXT_BTN_RED,
    _TEXT_BTN_RED_CONFIRM,
    _combo_ss,
    _make_banner,
    _make_sdiv,
    _srow,
)

logger = logging.getLogger(__name__)
_SURFACE_BG_STYLE = f"background:{_BG_SURFACE};"
_SCROLL_SURFACE_STYLE = f"QScrollArea {{ border:none; background:{_BG_SURFACE}; }}"
_TLS_LABEL_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_LABEL, extra="background:transparent;")
_MUTED_CAPTION_STYLE = muted_label_style(size=FONT_SIZE_CAPTION)

class SmtpPanel(QWidget):
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(
            _make_banner(
                "SMTP Configuration",
                _ACCENT_HI,
                _ACCENT_BG_08,
                _ACCENT_HI_BG_18,
            )
        )

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(_SCROLL_SURFACE_STYLE)
        body = QWidget()
        body.setStyleSheet(_SURFACE_BG_STYLE)
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, SPACE_XXL)
        body_l.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        body_l.addWidget(_make_sdiv("Server"))

        self._smtp_host = QLineEdit()
        self._smtp_host.setPlaceholderText("smtp.gmail.com")
        body_l.addWidget(_srow("SMTP Host", self._smtp_host))

        port_tls = QWidget()
        port_tls.setStyleSheet("background:transparent; border:none;")
        pt = QHBoxLayout(port_tls)
        pt.setContentsMargins(0, 0, 0, 0)
        pt.setSpacing(SPACE_MD)
        self._smtp_port = QSpinBox()
        self._smtp_port.setRange(1, 65535)
        self._smtp_port.setValue(587)
        self._smtp_port.setFixedWidth(SIZE_BTN_W_88)
        self._smtp_tls = ToggleSwitch()
        self._smtp_tls.setChecked(True)
        tls_lbl = QLabel("Use TLS / STARTTLS")
        tls_lbl.setStyleSheet(_TLS_LABEL_STYLE)
        pt.addWidget(self._smtp_port)
        pt.addWidget(self._smtp_tls)
        pt.addWidget(tls_lbl)
        pt.addStretch()
        body_l.addWidget(_srow("Port", port_tls))

        body_l.addWidget(_make_sdiv("Credentials"))

        self._smtp_user = QLineEdit()
        self._smtp_user.setPlaceholderText("your-email@gmail.com")
        body_l.addWidget(_srow("Username", self._smtp_user))

        pw_wrap = QWidget()
        pw_wrap.setStyleSheet("background:transparent; border:none;")
        ph = QHBoxLayout(pw_wrap)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.setSpacing(SPACE_SM)
        self._smtp_pass = QLineEdit()
        self._smtp_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self._smtp_pass.setPlaceholderText("App password or SMTP password")
        attach_password_visibility_toggle(self._smtp_pass)
        ph.addWidget(self._smtp_pass, stretch=1)
        body_l.addWidget(_srow("Password", pw_wrap))

        hint_fr = QFrame()
        hint_fr.setStyleSheet("background:transparent; border:none;")
        hl = QVBoxLayout(hint_fr)
        hl.setContentsMargins(SPACE_XL, SPACE_10, SPACE_XL, SPACE_10)
        hint = QLabel("Tip: for Gmail use an <b>App Password</b> (Google Account \u2192 Security \u2192 App Passwords).")
        hint.setStyleSheet(_MUTED_CAPTION_STYLE)
        hint.setWordWrap(True)
        hl.addWidget(hint)
        body_l.addWidget(hint_fr)
        body_l.addStretch()

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(divider_style(_BORDER_DIM))
        root.addWidget(div)

        test_btn = QPushButton("Send Test Email")
        test_btn.setFixedHeight(SIZE_CONTROL_MD)
        test_btn.setStyleSheet(_SECONDARY_BTN)
        test_btn.clicked.connect(self._test_smtp)
        self._smtp_test_btn = test_btn
        self._smtp_status_lbl = build_status_label()

        cancel_btn = make_close_button("Cancel")
        cancel_btn.setFixedWidth(SIZE_BTN_W_SM)
        cancel_btn.clicked.connect(self.close_requested.emit)

        save_btn = make_save_button("Save")
        save_btn.clicked.connect(self._save_smtp)

        ab = QHBoxLayout()
        ab.setContentsMargins(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD)
        ab.setSpacing(SPACE_SM)
        ab.addWidget(test_btn)
        ab.addWidget(self._smtp_status_lbl)
        ab.addStretch()
        ab.addWidget(cancel_btn)
        ab.addWidget(save_btn)
        root.addLayout(ab)

    def load(self):
        self._smtp_host.setText(db.get_setting("smtp_host", "") or "")
        self._smtp_port.setValue(int(db.get_setting("smtp_port", "587") or "587"))
        self._smtp_user.setText(db.get_setting("smtp_user", "") or "")
        self._smtp_pass.setText(db.get_setting("smtp_pass", "") or "")
        tls_raw = db.get_setting("smtp_tls", True)
        if isinstance(tls_raw, bool):
            self._smtp_tls.setChecked(tls_raw)
        else:
            self._smtp_tls.setChecked(str(tls_raw) not in ("0", "false", "no"))

    def _save_smtp(self):
        db.set_setting("smtp_host", self._smtp_host.text().strip())
        db.set_setting("smtp_port", str(self._smtp_port.value()))
        db.set_setting("smtp_user", self._smtp_user.text().strip())
        db.set_setting("smtp_pass", self._smtp_pass.text())
        db.set_setting("smtp_tls", "1" if self._smtp_tls.isChecked() else "0")
        from utils.config import invalidate_cache

        invalidate_cache()
        flash_status(self._smtp_status_lbl, "Saved")

    def _test_smtp(self):
        to = self._smtp_user.text().strip()
        if not to:
            QMessageBox.warning(
                self,
                "No Address",
                "Enter a username / email address first, then save before testing.",
            )
            return
        try:
            ok = test_email(to)
            if ok:
                flash_status(self._smtp_status_lbl, "Test sent")
            else:
                QMessageBox.warning(
                    self,
                    "Send Failed",
                    "Could not send the test email.\nVerify host / port / credentials and ensure the settings are saved.",
                )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Error", str(exc))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            logger.exception("Unexpected SMTP test failure")
            QMessageBox.critical(self, "Error", str(exc))


class ProfilePanel(QWidget):
    saved = Signal(int)
    suppress_requested = Signal()
    close_requested = Signal()
    delete_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._profile: dict | None = None
        self._edit_mode = False
        self.build_empty()

    def _clear(self):
        self._reset_refs()
        for w in self.findChildren(QWidget):
            w.setParent(None)
            w.deleteLater()
        old = self.layout()
        if old is not None:
            from shiboken6 import delete

            delete(old)

    def build_empty(self):
        self._clear()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        wrap = QWidget()
        wrap.setStyleSheet("background:transparent; border:none;")
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.setSpacing(SPACE_10)
        wl.setContentsMargins(SPACE_XXL, SPACE_XXL, SPACE_XXL, SPACE_XXL)

        t = QLabel("No profile selected")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_BODY, weight=FONT_WEIGHT_BOLD, extra="background:transparent;"))
        wl.addWidget(t)

        s = QLabel("Select a profile from the list to edit it,\nor click  '+  Add Profile'  to create a new one.")
        s.setWordWrap(True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet(muted_label_style(size=FONT_SIZE_CAPTION) + " background:transparent;")
        wl.addWidget(s)

        lay.addWidget(wrap)

    def load_profile(self, profile: dict):
        self._profile = profile
        self._edit_mode = False
        self._rebuild_form(profile)

    def new_profile(self):
        self._profile = None
        self._edit_mode = True
        self._rebuild_form(None)

    def _rebuild_form(self, profile: dict | None):
        self._clear()
        editing = profile is not None
        p = profile or {}
        view_mode = editing and not self._edit_mode

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        if not editing:
            banner = QFrame()
            banner.setStyleSheet(f"QFrame{{background:{_BG_RAISED};border:none;}}")
            bh = QHBoxLayout(banner)
            bh.setContentsMargins(SPACE_20, SPACE_10, SPACE_20, SPACE_10)
            bh.setSpacing(SPACE_MD)
            nf = QFont()
            safe_set_point_size(nf, FONT_SIZE_BODY)
            nf.setBold(True)
            title = QLabel("Add Profile")
            title.setFont(nf)
            title.setStyleSheet(f"color:{_TEXT_PRI};")
            bh.addWidget(title)
            bh.addStretch()
            close_x = QPushButton("✕")
            close_x.setFixedSize(SIZE_CONTROL_32, SIZE_CONTROL_32)
            close_x.setStyleSheet(_TEXT_BTN_GHOST + f"border-radius:{RADIUS_6}px;")
            close_x.clicked.connect(self.close_requested.emit)
            bh.addWidget(close_x)
            root.addWidget(banner)
        else:
            name = p.get("name", "Notification Profile")
            subtitle = p.get("endpoint", "") or "No target set"
            ptype = (p.get("type") or "email").upper()
            type_badge = QLabel(ptype)
            type_badge.setStyleSheet(
                f"font-size:{FONT_SIZE_MICRO}px; font-weight:{FONT_WEIGHT_BOLD}; "
                f"padding:{SPACE_3}px {SPACE_10}px; border-radius:{RADIUS_LG}px; "
                f"background:{_ACCENT_BG_12}; color:{_ACCENT_HI};"
            )
            badge_wrap = QFrame()
            badge_wrap.setFixedSize(SIZE_ROW_72, SIZE_ROW_72)
            badge_wrap.setStyleSheet(
                f"QFrame {{ background: {_BG_RAISED}; border: {SPACE_XXXS}px solid {_BORDER_DIM}; border-radius: {RADIUS_LG}px; }}"
            )
            bw = QVBoxLayout(badge_wrap)
            bw.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
            bw.setAlignment(Qt.AlignmentFlag.AlignCenter)
            bw.addWidget(type_badge)
            root.addWidget(
                make_hero_header(
                    "",
                    name,
                    subtitle,
                    left_widget=badge_wrap,
                    parent=self,
                )
            )

        self._edit_banner = make_edit_banner(f"Editing — {p.get('name', '')}", self)
        self._edit_banner.setVisible(editing and self._edit_mode)
        root.addWidget(self._edit_banner)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(_SCROLL_SURFACE_STYLE)
        body = QWidget()
        body.setStyleSheet(_SURFACE_BG_STYLE)
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, SPACE_XXL)
        body_l.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        if view_mode:
            body_l.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
            body_l.setSpacing(SPACE_XXS)

            def _info_row(label: str, value: str):
                w = QWidget()
                w.setStyleSheet("background:transparent;border:none;")
                r = QHBoxLayout(w)
                r.setContentsMargins(SPACE_XL, SPACE_XS, SPACE_XL, SPACE_XS)
                r.setSpacing(SPACE_10)
                lb = QLabel(f"{label}:")
                lb.setFixedWidth(SIZE_LABEL_W)
                lb.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_LABEL))
                r.addWidget(lb)
                vl = QLabel(value if value else "—")
                vl.setStyleSheet(
                    f"color:{_TEXT_PRI};font-size:{FONT_SIZE_BODY}px;"
                    if value
                    else f"color:{_TEXT_MUTED};font-size:{FONT_SIZE_CAPTION}px;font-style:italic;"
                )
                vl.setWordWrap(True)
                r.addWidget(vl, stretch=1)
                return w

            def _div():
                d = QFrame()
                d.setFrameShape(QFrame.Shape.HLine)
                d.setStyleSheet(divider_style(_BORDER_DIM))
                return d

            def _section(title: str):
                c = QWidget()
                c.setStyleSheet("background:transparent;border:none;")
                r = QHBoxLayout(c)
                r.setContentsMargins(SPACE_XL, SPACE_SM, SPACE_XL, SPACE_XXS)
                r.setSpacing(SPACE_SM)
                lb = QLabel(title.upper())
                lb.setStyleSheet(section_kicker_style())
                r.addWidget(lb)
                ln = QFrame()
                ln.setFrameShape(QFrame.Shape.HLine)
                ln.setStyleSheet(divider_style(_BORDER_DIM))
                r.addWidget(ln, stretch=1)
                return c

            body_l.addWidget(_section("General"))
            body_l.addWidget(_info_row("Profile Name", p.get("name", "")))
            body_l.addWidget(_div())
            body_l.addWidget(_info_row("Type", (p.get("type") or "").upper()))
            body_l.addWidget(_div())
            body_l.addWidget(_info_row("Target", p.get("endpoint", "")))
            body_l.addWidget(_div())
            enabled_label = "Active" if bool(p.get("enabled", True)) else "Inactive"
            body_l.addWidget(_info_row("Active", enabled_label))
            body_l.addWidget(_div())
            if (p.get("type") or "") == "webhook":
                body_l.addWidget(_info_row("Auth Token", "Set" if p.get("auth_token") else "—"))
                body_l.addWidget(_div())
            body_l.addStretch()
        else:
            name_fr = QFrame()
            name_fr.setFixedHeight(SIZE_ROW_LG)
            name_fr.setStyleSheet(
                "QFrame{{{base} border:none;border-bottom:{w}px solid {border};}}".format(
                    base=transparent_surface_style(),
                    w=SPACE_XXXS,
                    border=_BORDER_DIM,
                )
            )
            nr = QHBoxLayout(name_fr)
            nr.setContentsMargins(SPACE_XL, SPACE_MD, SPACE_XL, SPACE_MD)
            nr.setSpacing(SPACE_20)
            nlb = QLabel("Profile Name")
            nlb.setFixedWidth(SIZE_LABEL_W)
            nlb.setAlignment(Qt.AlignmentFlag.AlignVCenter)
            nlb.setStyleSheet(
                f"color:{_TEXT_SEC}; font-size:{FONT_SIZE_LABEL}px; font-weight:{FONT_WEIGHT_NORMAL};background:transparent; border:none;"
            )
            nr.addWidget(nlb)
            self._e_name = QLineEdit(p.get("name", ""))
            self._e_name.setPlaceholderText("e.g.  Security Team Email")
            self._e_name.setStyleSheet(_FORM_INPUT_TITLE)
            nr.addWidget(self._e_name, stretch=1)
            body_l.addWidget(name_fr)

            if not (editing and self._edit_mode):
                body_l.addWidget(_make_sdiv("Settings"))

            self._e_type = QComboBox()
            self._e_type.setStyleSheet(_combo_ss())
            self._e_type.addItems(["email", "webhook"])
            if p.get("type"):
                self._e_type.setCurrentText(p["type"])
            body_l.addWidget(_srow("Type", self._e_type))

            self._e_endpoint = QLineEdit(p.get("endpoint", ""))
            self._e_endpoint.setPlaceholderText("email@example.com  or  https://hooks.example.com/?")
            body_l.addWidget(_srow("Target", self._e_endpoint))

            self._e_auth = QLineEdit(p.get("auth_token", ""))
            self._e_auth.setPlaceholderText("Bearer token (optional)")
            self._e_auth.setEchoMode(QLineEdit.EchoMode.Password)
            attach_password_visibility_toggle(self._e_auth)
            self._auth_row = _srow("Auth Token", self._e_auth)
            body_l.addWidget(self._auth_row)

            def _sync_auth(text: str):
                self._auth_row.setVisible(text == "webhook")

            self._e_type.currentTextChanged.connect(_sync_auth)
            _sync_auth(self._e_type.currentText())

            en_wrap = QWidget()
            en_wrap.setStyleSheet("background:transparent; border:none;")
            eh = QHBoxLayout(en_wrap)
            eh.setContentsMargins(0, 0, 0, 0)
            eh.setSpacing(SPACE_10)
            self._e_enabled = ToggleSwitch()
            self._e_enabled.setChecked(bool(p.get("enabled", True)))
            elbl = QLabel("Profile is active")
            elbl.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_LABEL, extra="background:transparent;"))
            eh.addWidget(self._e_enabled)
            eh.addWidget(elbl)
            eh.addStretch()
            body_l.addWidget(_srow("Active", en_wrap))

            body_l.addStretch()

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(divider_style(_BORDER_DIM))
        root.addWidget(div)

        del_btn = None
        if editing:
            pid = p.get("id")
            del_btn = ConfirmDeleteButton("Delete", "Sure?")
            del_btn.setFixedHeight(SIZE_CONTROL_MD)
            del_btn.setFixedWidth(SIZE_BTN_W_MD)
            del_btn.set_button_styles(_TEXT_BTN_RED, _TEXT_BTN_RED_CONFIRM)
            del_btn.set_confirm_callback(lambda: self.delete_requested.emit(pid))

        test_btn = QPushButton("Test")
        test_btn.setFixedHeight(SIZE_CONTROL_MD)
        test_btn.setFixedWidth(SIZE_BTN_W_72)
        test_btn.setStyleSheet(_SECONDARY_BTN)
        test_btn.setVisible(editing)
        test_btn.clicked.connect(lambda: self._test_profile(p))
        self._test_btn = test_btn

        self._profile_status_lbl = build_status_label()

        self._cancel_btn = make_close_button("Cancel")
        self._cancel_btn.setFixedWidth(SIZE_BTN_W_SM)
        self._cancel_btn.clicked.connect(self.close_requested.emit)

        self._close_btn = make_close_button("Close")
        self._close_btn.setFixedWidth(SIZE_BTN_W_80)
        self._close_btn.clicked.connect(self.close_requested.emit)

        self._edit_btn = QPushButton("Edit")
        self._edit_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._edit_btn.setFixedWidth(SIZE_BTN_W_80)
        self._edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
        self._edit_btn.clicked.connect(self._toggle_edit_mode)

        self._save_btn = make_save_button("Save")
        self._save_btn.clicked.connect(self._do_save)
        root.addLayout(
            make_manager_footer_layout(
                left_widget=del_btn,
                center_widget=test_btn,
                right_widgets=[
                    self._profile_status_lbl,
                    self._cancel_btn,
                    self._close_btn,
                    self._edit_btn,
                    self._save_btn,
                ],
                margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
                spacing=SPACE_SM,
            )
        )

        self._set_edit_mode(self._edit_mode or not editing)

    def _set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        fields = [self._e_name, self._e_type, self._e_endpoint, self._e_auth]
        for w in fields:
            if w is not None and isValid(w):
                w.setEnabled(enabled)
        if self._e_enabled is not None and isValid(self._e_enabled):
            self._e_enabled.setEnabled(enabled)
        if self._edit_btn is not None and isValid(self._edit_btn):
            if self._profile is None:
                self._edit_btn.setVisible(False)
            else:
                self._edit_btn.setVisible(True)
                if enabled:
                    self._edit_btn.setText("Save")
                    self._edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
                else:
                    self._edit_btn.setText("Edit")
                    self._edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
        if self._save_btn is not None and isValid(self._save_btn):
            self._save_btn.setVisible(self._profile is None)
        if self._cancel_btn is not None and isValid(self._cancel_btn):
            self._cancel_btn.setVisible(enabled or self._profile is None)
        if self._close_btn is not None and isValid(self._close_btn):
            self._close_btn.setVisible(not enabled and self._profile is not None)
        if hasattr(self, "_edit_banner") and self._edit_banner is not None and isValid(self._edit_banner):
            self._edit_banner.setVisible(enabled and self._profile is not None)

    def _toggle_edit_mode(self):
        if self._profile is None:
            return
        if not self._edit_mode:
            self._edit_mode = True
            self.suppress_requested.emit()
            self._rebuild_form(self._profile)
            return
        self.suppress_requested.emit()
        self._do_save()

    def _do_save(self):
        if self._e_name is None or not isValid(self._e_name):
            return
        self.suppress_requested.emit()
        name = self._e_name.text().strip()
        target = self._e_endpoint.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Notification profile name is required.")
            self._e_name.setFocus()
            return
        if not target:
            QMessageBox.warning(self, "Missing Target", "Notification profile target is required.")
            self._e_endpoint.setFocus()
            return
        ptype = self._e_type.currentText()
        validation_error = validate_notification_target(ptype, target)
        if validation_error:
            QMessageBox.warning(self, "Invalid Target", validation_error)
            self._e_endpoint.setFocus()
            return
        token = self._e_auth.text().strip() if ptype == "webhook" else ""
        en_val = 1 if self._e_enabled.isChecked() else 0
        saved_id = None
        if self._profile:
            db.update_notification_profile(
                self._profile["id"],
                name=name,
                type=ptype,
                endpoint=target,
                auth_token=token,
                enabled=en_val,
            )
            saved_id = self._profile["id"]
        else:
            pid = db.add_notification_profile(name, ptype, target, token)
            if not en_val:
                db.update_notification_profile(pid, enabled=0)
            saved_id = pid
        if saved_id is not None:
            self.saved.emit(saved_id)
            if hasattr(self, "_profile_status_lbl") and self._profile_status_lbl is not None and isValid(self._profile_status_lbl):
                flash_status(self._profile_status_lbl, "Saved")
        self._set_edit_mode(False)

    def _test_profile(self, profile: dict):
        if self._e_type is not None and isValid(self._e_type):
            ptype = self._e_type.currentText()
            target = self._e_endpoint.text().strip() if self._e_endpoint is not None and isValid(self._e_endpoint) else ""
            token = self._e_auth.text().strip() if self._e_auth is not None and isValid(self._e_auth) else ""
        else:
            ptype = profile.get("type", "email")
            target = profile.get("endpoint", "")
            token = profile.get("auth_token", "")
        validation_error = validate_notification_target(ptype, target)
        if validation_error:
            QMessageBox.warning(self, "Invalid Target", validation_error)
            return
        try:
            if ptype == "email":
                ok = test_email(target)
            else:
                ok = test_webhook(target, token or None)
            if ok:
                if hasattr(self, "_profile_status_lbl") and self._profile_status_lbl is not None and isValid(self._profile_status_lbl):
                    flash_status(self._profile_status_lbl, "Test sent")
                else:
                    show_toast(self, f"Test {ptype} sent to {target}")
            else:
                QMessageBox.warning(
                    self,
                    "Failed",
                    f"Could not send test {ptype} to:\n{target}",
                )
        except (OSError, RuntimeError, ValueError) as exc:
            QMessageBox.critical(self, "Error", str(exc))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            logger.exception("Unexpected notification profile test failure")
            QMessageBox.critical(self, "Error", str(exc))
    def _reset_refs(self):
        self._e_name = None
        self._e_type = None
        self._e_endpoint = None
        self._e_auth = None
        self._e_enabled = None
        self._edit_btn = None
        self._save_btn = None
        self._cancel_btn = None
        self._close_btn = None
        self._profile_status_lbl = None
        self._smtp_status_lbl = None

