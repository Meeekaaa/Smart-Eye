from __future__ import annotations

import os
import re

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QFont, QPixmap, QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.dialogs import apply_popup_theme
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_SUBHEAD,
    RADIUS_LG,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_MD,
    SIZE_DIALOG_W_LG,
    SIZE_LABEL_W,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXXS,
)

from ._constants import (
    _BORDER_DIM,
    _PRIMARY_BTN,
    _STYLESHEET,
    _TEXT_PRI,
    _compose_name,
    _split_name_parts,
)


def show_edit_face_dialog(parent, face_id: int) -> None:
    face = db.get_face(face_id)
    if not face:
        return

    dlg = QDialog(parent)
    dlg.setWindowTitle(f"Edit - {face.get('name', '')}")
    dlg.setMinimumWidth(SIZE_DIALOG_W_LG)
    apply_popup_theme(dlg, _STYLESHEET)

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(SPACE_XL, SPACE_20, SPACE_XL, SPACE_20)
    layout.setSpacing(SPACE_14)

    title_lbl = QLabel(f"Editing: {face.get('name', '')}")
    etf = QFont()
    safe_set_point_size(etf, FONT_SIZE_SUBHEAD)
    etf.setBold(True)
    title_lbl.setFont(etf)
    layout.addWidget(title_lbl)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"background: {_BORDER_DIM}; border: none; max-height: {SPACE_XXXS}px;")
    layout.addWidget(sep)

    _name_re = QRegularExpression(r"[\p{L} '\-.]*")
    _dept_re = QRegularExpression(r".*")
    _addr_re = QRegularExpression(r"[\p{L}\p{N} '\-.,/#&()]*")
    _country_re = QRegularExpression(r"[\p{L} '\-.]*")
    _phone_re = QRegularExpression(r"[\d+\-() ]*")
    _email_re = QRegularExpression(r"[a-zA-Z0-9!#$%&'*+\-/=?^_`{|}~@.\[\]]*")

    form = QFormLayout()
    form.setSpacing(SPACE_10)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

    def _fe(text, validator=None, maxlen=None):
        w = QLineEdit(text)
        w.setFixedHeight(SIZE_CONTROL_MD)
        if validator:
            w.setValidator(QRegularExpressionValidator(validator))
        if maxlen:
            w.setMaxLength(maxlen)
        return w

    fn, sn, tn, ln = _split_name_parts(face.get("name", ""))
    fn_e = _fe(fn, _name_re, 50)
    form.addRow("First Name *:", fn_e)
    sn_e = _fe(sn, _name_re, 50)
    form.addRow("Second Name *:", sn_e)
    tn_e = _fe(tn, _name_re, 50)
    form.addRow("Third Name:", tn_e)
    ln_e = _fe(ln, _name_re, 50)
    form.addRow("Last Name:", ln_e)
    de_e = _fe(face.get("department") or "", _dept_re, 80)
    form.addRow("Department:", de_e)
    ad_e = _fe(face.get("address") or "", _addr_re, 120)
    form.addRow("Address:", ad_e)
    co_e = _fe(face.get("country") or "", _country_re, 60)
    form.addRow("Country:", co_e)

    stored_birth = face.get("birth_date") or ""
    if stored_birth and len(stored_birth) == 10 and stored_birth[4] == "-":
        yyyy, mm, dd = stored_birth[:4], stored_birth[5:7], stored_birth[8:]
        display_birth = f"{dd}-{mm}-{yyyy}"
    else:
        display_birth = stored_birth
    bd_e = _fe(display_birth, maxlen=10)
    bd_e.setPlaceholderText("DD-MM-YYYY")

    _date_guard = [False]

    def _on_birth_changed(text):
        if _date_guard[0]:
            return
        digits = "".join(c for c in text if c.isdigit())[:8]
        if len(digits) >= 4:
            new_text = digits[:2] + "-" + digits[2:4] + "-" + digits[4:]
        elif len(digits) >= 2:
            new_text = digits[:2] + "-" + digits[2:]
        else:
            new_text = digits
        if new_text != text:
            _date_guard[0] = True
            pos = bd_e.cursorPosition()
            bd_e.setText(new_text)
            extra = new_text.count("-", 0, pos) - text.count("-", 0, pos)
            bd_e.setCursorPosition(min(pos + extra, len(new_text)))
            _date_guard[0] = False

    bd_e.textChanged.connect(_on_birth_changed)
    form.addRow("Birth Date:", bd_e)

    ph_e = _fe(face.get("phone") or "", _phone_re, 25)
    form.addRow("Phone:", ph_e)
    em_e = _fe(face.get("email") or "", _email_re, 100)
    form.addRow("Email:", em_e)

    ac_toggle = ToggleSwitch()
    ac_toggle.setChecked(face.get("authorized_cameras", "[]") != "[]")
    ac_lbl = QLabel("Grant access (authorized)")
    ac_lbl.setStyleSheet(
        f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_BODY}px; background: transparent; border: none; padding: 0 {SPACE_SM}px;"
    )
    ac_wrap = QWidget()
    ac_wrap.setStyleSheet("background: transparent; border: none;")
    ac_wrap_layout = QHBoxLayout(ac_wrap)
    ac_wrap_layout.setContentsMargins(0, 0, 0, 0)
    ac_wrap_layout.setSpacing(0)
    ac_wrap_layout.addWidget(ac_toggle)
    ac_wrap_layout.addWidget(ac_lbl)
    ac_wrap_layout.addStretch()
    form.addRow("Access:", ac_wrap)

    layout.addLayout(form)

    pp = face.get("image_path", "")
    if pp and os.path.isfile(pp):
        prev = QLabel()
        prev.setPixmap(
            QPixmap(pp).scaled(
                SIZE_LABEL_W,
                SIZE_LABEL_W,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        prev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        prev.setStyleSheet(
            f"background: transparent; border: {SPACE_XXXS}px solid {_BORDER_DIM}; border-radius: {RADIUS_LG}px; padding: {SPACE_XS}px;"
        )
        layout.addWidget(prev)

    layout.addStretch()
    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet(f"background: {_BORDER_DIM}; border: none; max-height: {SPACE_XXXS}px;")
    layout.addWidget(sep2)

    br = QHBoxLayout()
    br.setSpacing(SPACE_SM)
    br.addStretch()
    sv = QPushButton("Save Changes")
    sv.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
    sv.setStyleSheet(_PRIMARY_BTN)

    def do_save():
        f = fn_e.text().strip()
        s = sn_e.text().strip()
        if not f or not s:
            QMessageBox.warning(dlg, "Required Fields", "First name and second name are required.")
            (fn_e if not f else sn_e).setFocus()
            return
        birth_val = bd_e.text().strip()
        if birth_val:
            if not re.fullmatch(r"\d{2}-\d{2}-\d{4}", birth_val):
                QMessageBox.warning(dlg, "Invalid Date", "Birth date must be in DD-MM-YYYY format.")
                bd_e.setFocus()
                return
            dd2, mm2, yyyy2 = int(birth_val[:2]), int(birth_val[3:5]), int(birth_val[6:])
            if not (1 <= mm2 <= 12 and 1 <= dd2 <= 31 and 1900 <= yyyy2 <= 2100):
                QMessageBox.warning(dlg, "Invalid Date", "Please enter a valid birth date (DD-MM-YYYY).")
                bd_e.setFocus()
                return
            birth_store = f"{birth_val[6:]}-{birth_val[3:5]}-{birth_val[0:2]}"
        else:
            birth_store = ""
        email_val = em_e.text().strip()
        if email_val and not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", email_val):
            QMessageBox.warning(dlg, "Invalid Email", "Please enter a valid email address (e.g. user@example.com).")
            em_e.setFocus()
            return
        db.update_face(
            face_id,
            name=_compose_name(f, s, tn_e.text().strip(), ln_e.text().strip()),
            department=de_e.text().strip(),
            address=ad_e.text().strip(),
            country=co_e.text().strip(),
            birth_date=birth_store,
            phone=ph_e.text().strip(),
            email=email_val,
            authorized_cameras="[]",
        )
        dlg.accept()

    sv.clicked.connect(do_save)
    br.addWidget(sv)
    cv = QPushButton("Cancel")
    cv.setProperty("class", "secondary")
    cv.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
    cv.clicked.connect(dlg.reject)
    br.addWidget(cv)
    layout.addLayout(br)
    dlg.exec()
