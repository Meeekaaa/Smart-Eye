from __future__ import annotations

from PySide6.QtCore import Qt, QRegularExpression
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.widgets.action_feedback import make_manager_footer_layout

from frontend.styles._colors import (
    _ACCENT_BG_08,
    _ACCENT_HI,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _MUTED_BG_10,
    _PURPLE_BG_12,
    _PURPLE_TINT,
    _SUCCESS,
    _SUCCESS_BG_14,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.styles._banner_styles import make_edit_banner
from frontend.styles._btn_styles import _TEXT_BTN_GHOST
from frontend.styles._input_styles import _FORM_COMBO
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_SIZE_SUBHEAD,
    FONT_SIZE_XL,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_HEAVY,
    RADIUS_LG,
    SIZE_BTN_W_80,
    SIZE_BTN_W_MD,
    SIZE_CONTROL_MD,
    SIZE_FIELD_W_SM,
    SIZE_ICON_64,
    SIZE_LABEL_W_LG,
    SIZE_ROW_72,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_3,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
)
from ._constants import (
    _AVATAR_BG_COLORS,
    _AVATAR_FG_COLORS,
    _TEXT_BTN_BLUE,
    _TEXT_BTN_RED_DEFAULT,
    _TEXT_BTN_RED_CONFIRM,
    _make_rounded_pixmap,
    _short_display_name,
    _split_name_parts,
)
from ._widgets import ClickableFrame


def _display_gender(value: str | None) -> str:
    text = (value or "").strip().lower()
    if text == "male":
        return "Male"
    if text == "female":
        return "Female"
    return "Unknown"


def build_face_content(panel, face: dict, layout: QVBoxLayout) -> None:

    is_authorized = face.get("authorized_cameras", "[]") != "[]"
    color_idx = face.get("id", 0) % len(_AVATAR_BG_COLORS)
    fg_color = _AVATAR_FG_COLORS[color_idx]
    bg_dark, bg_light = _AVATAR_BG_COLORS[color_idx]
    first_name, second_name, third_name, last_name = _split_name_parts(face.get("name", ""))

    hero_frame = QFrame()
    hero_frame.setStyleSheet(f"QFrame {{ background: {_BG_RAISED}; border: none; }}")
    hero_layout = QHBoxLayout(hero_frame)
    hero_layout.setContentsMargins(SPACE_20, SPACE_14, SPACE_20, SPACE_14)
    hero_layout.setSpacing(SPACE_14)
    hero_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    avatar_wrap = ClickableFrame()
    avatar_wrap.setFixedSize(SIZE_ROW_72, SIZE_ROW_72)
    avatar_wrap.setCursor(Qt.CursorShape.PointingHandCursor)
    avatar_wrap.setToolTip("Click to replace photo")
    avatar_wrap.setStyleSheet(f"""
        QFrame {{
            background-color: {_BG_RAISED};
            border: {SPACE_XXXS}px solid {_BORDER_DIM};
            border-radius: {RADIUS_LG}px;
        }}
        QFrame:hover {{ border-color: {_BORDER}; }}
    """)
    awl = QVBoxLayout(avatar_wrap)
    awl.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
    awl.setAlignment(Qt.AlignmentFlag.AlignCenter)

    avatar = QLabel()
    avatar.setFixedSize(SIZE_ICON_64, SIZE_ICON_64)
    avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    photo_path = face.get("image_path", "")
    initial = (face.get("name") or "?")[0].upper()
    rpix = _make_rounded_pixmap(photo_path, SIZE_ICON_64, RADIUS_LG)
    if rpix:
        avatar.setPixmap(rpix)
        avatar.setStyleSheet(f"border-radius: {RADIUS_LG}px; border: none;")
    else:
        avatar.setText(initial)
        avatar.setStyleSheet(f"""
            border-radius: {RADIUS_LG}px;
            background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:1,
                stop:0 {bg_light}, stop:1 {bg_dark});
            color: {fg_color}; font-size: {FONT_SIZE_XL}px; font-weight: {FONT_WEIGHT_HEAVY};
        """)
    awl.addWidget(avatar)

    def _replace_photo():
        from PySide6.QtWidgets import QFileDialog

        path, _ = QFileDialog.getOpenFileName(panel, "Select Photo", "", "Images (*.jpg *.jpeg *.png *.bmp *.webp)")
        if not path:
            return
        db.update_face(panel._face_id, image_path=path)
        updated = dict(face)
        updated["image_path"] = path
        panel.load_face(updated)

    avatar_wrap.clicked.connect(_replace_photo)
    hero_layout.addWidget(avatar_wrap, alignment=Qt.AlignmentFlag.AlignVCenter)

    heading_col = QVBoxLayout()
    heading_col.setContentsMargins(0, SPACE_XXS, 0, 0)
    heading_col.setSpacing(SPACE_XS)

    name_lbl = QLabel(_short_display_name(face.get("name") or "Unknown"))
    nf = QFont()
    safe_set_point_size(nf, FONT_SIZE_SUBHEAD)
    nf.setBold(True)
    name_lbl.setFont(nf)
    name_lbl.setStyleSheet(f"color: {_TEXT_PRI};")
    heading_col.addWidget(name_lbl)

    subtitle = QLabel(face.get("department") or "No department")
    subtitle.setStyleSheet(f"font-size: {FONT_SIZE_LABEL}px; color: {_TEXT_SEC};")
    heading_col.addWidget(subtitle)
    heading_col.addSpacing(SPACE_6)

    chip_row = QHBoxLayout()
    chip_row.setSpacing(SPACE_6)
    auth_badge = QLabel("\u2713  Authorized" if is_authorized else "Restricted")
    auth_badge.setStyleSheet(
        f"font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD}; "
        f"padding: {SPACE_3}px {SPACE_10}px; border-radius: {RADIUS_LG}px; "
        f"background-color: {_SUCCESS_BG_14 if is_authorized else _MUTED_BG_10}; "
        f"color: {_SUCCESS if is_authorized else _TEXT_MUTED}; "
        f"border: none;"
    )
    chip_row.addWidget(auth_badge)
    uid = str(face.get("uuid") or "")
    uuid_badge = QLabel(f"UUID {uid[:8] if uid else '--------'}")
    uuid_badge.setStyleSheet(
        f"font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD}; font-family: 'JetBrains Mono', 'Consolas', monospace; "
        f"padding: {SPACE_3}px {SPACE_10}px; border-radius: {RADIUS_LG}px; background-color: {_ACCENT_BG_08}; "
        f"color: {_ACCENT_HI}; border: none;"
    )
    chip_row.addWidget(uuid_badge)
    emb_model = (face.get("embedding_model") or "").strip()
    if not emb_model:
        try:
            from backend.models.model_loader import get_face_model

            fm = get_face_model()
            if fm and getattr(fm, "model_name", ""):
                emb_model = fm.model_name
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            emb_model = ""
    if emb_model:
        model_badge = QLabel(emb_model)
        model_badge.setToolTip(f"Embedding extracted with: {emb_model}")
        model_badge.setStyleSheet(
            f"font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD}; font-family: 'JetBrains Mono', 'Consolas', monospace; "
            f"padding: {SPACE_3}px {SPACE_10}px; border-radius: {RADIUS_LG}px; background-color: {_PURPLE_BG_12}; "
            f"color: {_PURPLE_TINT}; border: none;"
        )
        chip_row.addWidget(model_badge)
    chip_row.addStretch()
    heading_col.addLayout(chip_row)
    hero_layout.addLayout(heading_col, stretch=1)
    layout.addWidget(hero_frame)

    panel._edit_banner = make_edit_banner("Editing — click a section header to focus its fields", panel)
    panel._edit_banner.setVisible(False)
    layout.addWidget(panel._edit_banner)

    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("border: none; background: transparent;")
    scroll_body = QWidget()
    body_layout = QVBoxLayout(scroll_body)
    body_layout.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
    body_layout.setSpacing(SPACE_14)
    scroll.setWidget(scroll_body)
    layout.addWidget(scroll, stretch=1)

    content = QVBoxLayout()
    content.setSpacing(SPACE_10)
    content.addLayout(panel._build_section_header("Identity", "identity"))
    panel._field_row("First Name", "first_name", first_name, content, required=True)
    panel._field_row("Second Name", "second_name", second_name, content, required=True)
    panel._field_row("Third Name", "third_name", third_name, content)
    panel._field_row("Last Name", "last_name", last_name, content)
    panel._field_row("Department", "department", face.get("department") or "", content)
    content.addSpacing(SPACE_SM)
    content.addLayout(panel._build_section_header("Contact", "contact"))
    panel._field_row("Phone", "phone", face.get("phone") or "", content)
    panel._field_row("Email", "email", face.get("email") or "", content)
    content.addSpacing(SPACE_SM)
    content.addLayout(panel._build_section_header("Location", "location"))
    panel._field_row("Address", "address", face.get("address") or "", content)
    panel._field_row("Country", "country", face.get("country") or "", content)
    content.addSpacing(SPACE_SM)
    content.addLayout(panel._build_section_header("Personal", "personal"))

    stored_birth = face.get("birth_date") or ""
    if stored_birth and len(stored_birth) == 10 and stored_birth[4] == "-":
        _yy, _mm, _dd = stored_birth[:4], stored_birth[5:7], stored_birth[8:]
        display_birth = f"{_dd}-{_mm}-{_yy}"
    else:
        display_birth = stored_birth
    panel._field_row("Birth Date", "birth_date", display_birth, content)

    gender_row = QHBoxLayout()
    gender_row.setContentsMargins(0, 0, 0, 0)
    gender_row.setSpacing(SPACE_10)

    gender_lbl = QLabel("Gender:")
    gender_lbl.setStyleSheet(f"color: {_TEXT_SEC}; min-width: {SIZE_FIELD_W_SM}px;")
    gender_lbl.setFixedWidth(SIZE_LABEL_W_LG)
    gender_row.addWidget(gender_lbl)

    gender_current = face.get("gender") or face.get("gender_norm")
    gender_value = QLabel(_display_gender(gender_current))
    gender_value.setStyleSheet(f"color: {_TEXT_PRI};")
    gender_row.addWidget(gender_value, stretch=1)

    gender_edit = QComboBox()
    gender_edit.addItems(["Unknown", "Male", "Female"])
    gender_edit.setCurrentText(_display_gender(gender_current))
    gender_edit.setStyleSheet(_FORM_COMBO)
    gender_edit.setEnabled(False)
    gender_edit.setVisible(False)
    gender_row.addWidget(gender_edit, stretch=1)

    panel._inputs["gender"] = gender_edit
    panel._value_labels["gender"] = gender_value
    content.addLayout(gender_row)

    gender_div = QFrame()
    gender_div.setFrameShape(QFrame.Shape.HLine)
    gender_div.setStyleSheet(f"background: {_BORDER_DIM}; border: none; max-height: {SPACE_XXXS}px;")
    content.addWidget(gender_div)

    content.addSpacing(SPACE_SM)
    content.addLayout(panel._build_section_header("Access", "access"))

    from PySide6.QtGui import QRegularExpressionValidator as _REV

    _v_name = _REV(QRegularExpression(r"[\p{L} '\-.]*"))
    _v_dept = _REV(QRegularExpression(r".*"))
    _v_phone = _REV(QRegularExpression(r"[\d+\-() ]*"))
    _v_email = _REV(QRegularExpression(r"[a-zA-Z0-9!#$%&'*+\-/=?^_`{|}~@.\[\]]*"))
    _v_addr = _REV(QRegularExpression(r"[\p{L}\p{N} '\-.,/#&()]*"))
    _v_country = _REV(QRegularExpression(r"[\p{L} '\-.]*"))
    for _k, _v, _ml in [
        ("first_name", _v_name, 50),
        ("second_name", _v_name, 50),
        ("third_name", _v_name, 50),
        ("last_name", _v_name, 50),
        ("department", _v_dept, 80),
        ("phone", _v_phone, 25),
        ("email", _v_email, 100),
        ("address", _v_addr, 120),
        ("country", _v_country, 60),
    ]:
        _inp = panel._inputs.get(_k)
        if _inp:
            _inp.setValidator(_v)
            _inp.setMaxLength(_ml)

    bd_inp = panel._inputs.get("birth_date")
    if bd_inp:
        bd_inp.setMaxLength(10)
        bd_inp.setPlaceholderText("DD-MM-YYYY")
        _dg = [False]

        def _on_bd_changed(text, _inp=bd_inp, _dg=_dg):
            if _dg[0]:
                return
            digits = "".join(c for c in text if c.isdigit())[:8]
            if len(digits) >= 4:
                new_text = digits[:2] + "-" + digits[2:4] + "-" + digits[4:]
            elif len(digits) >= 2:
                new_text = digits[:2] + "-" + digits[2:]
            else:
                new_text = digits
            if new_text != text:
                _dg[0] = True
                pos = _inp.cursorPosition()
                _inp.setText(new_text)
                extra = new_text.count("-", 0, pos) - text.count("-", 0, pos)
                _inp.setCursorPosition(min(pos + extra, len(new_text)))
                _dg[0] = False

        bd_inp.textChanged.connect(_on_bd_changed)

    acc_row = QHBoxLayout()
    acc_row.setContentsMargins(0, 0, 0, 0)
    acc_row.setSpacing(SPACE_10)
    acc_lbl = QLabel("Authorized:")
    acc_lbl.setStyleSheet(f"color: {_TEXT_SEC}; min-width: {SIZE_FIELD_W_SM}px;")
    acc_lbl.setFixedWidth(SIZE_LABEL_W_LG)
    acc_row.addWidget(acc_lbl)
    acc_value_lbl = QLabel("Yes" if is_authorized else "No")
    acc_value_lbl.setStyleSheet(f"color: {_TEXT_PRI};")
    acc_row.addWidget(acc_value_lbl, stretch=1)
    acc_edit = ToggleSwitch()
    acc_edit.setChecked(is_authorized)
    acc_edit.setVisible(False)
    _acc_text_lbl = QLabel("Grant camera access")
    _acc_text_lbl.setStyleSheet(
        f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_BODY}px; background: transparent; border: none; padding: 0 {SPACE_SM}px;"
    )
    _acc_text_lbl.setVisible(False)
    _acc_wrap = QHBoxLayout()
    _acc_wrap.setContentsMargins(0, 0, 0, 0)
    _acc_wrap.setSpacing(0)
    _acc_wrap.addWidget(acc_edit)
    _acc_wrap.addWidget(_acc_text_lbl)
    _acc_wrap.addStretch()

    _orig_activate = panel._activate_section

    if not hasattr(panel, "_orig_activate_section"):
        panel._orig_activate_section = _orig_activate

    def _patched_activate(section_key, _orig=panel._orig_activate_section):
        _orig(section_key)
        try:
            _is_vis = acc_edit.isVisible()
        except RuntimeError:
            return
        _acc_text_lbl.setVisible(_is_vis)

    panel._activate_section = _patched_activate
    panel._inputs["authorized"] = acc_edit
    panel._value_labels["authorized"] = acc_value_lbl
    acc_row.addLayout(_acc_wrap)
    content.addLayout(acc_row)

    panel._section_fields = {
        "identity": ["first_name", "second_name", "third_name", "last_name", "department"],
        "contact": ["phone", "email"],
        "location": ["address", "country"],
        "personal": ["birth_date", "gender"],
        "access": ["authorized"],
    }

    body_layout.addLayout(content)
    body_layout.addStretch()

    sep2 = QFrame()
    sep2.setFrameShape(QFrame.Shape.HLine)
    sep2.setStyleSheet(f"background: {_BORDER_DIM}; border: none; max-height: {SPACE_XXXS}px;")
    layout.addWidget(sep2)

    del_btn = ConfirmDeleteButton("Delete", "Sure?")
    del_btn.setFixedHeight(SIZE_CONTROL_MD)
    del_btn.setFixedWidth(SIZE_BTN_W_MD)
    del_btn.set_button_styles(_TEXT_BTN_RED_DEFAULT, _TEXT_BTN_RED_CONFIRM)
    del_btn.set_confirm_callback(lambda fid=panel._face_id: panel.delete_requested.emit(fid))

    close_btn = QPushButton("Close")
    close_btn.setFixedHeight(SIZE_CONTROL_MD)
    close_btn.setFixedWidth(SIZE_BTN_W_80)
    close_btn.setStyleSheet(_TEXT_BTN_GHOST)
    close_btn.clicked.connect(lambda _c=False: panel.close_requested.emit())

    panel._edit_btn = QPushButton("Edit")
    panel._edit_btn.setFixedHeight(SIZE_CONTROL_MD)
    panel._edit_btn.setFixedWidth(SIZE_BTN_W_80)
    panel._edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
    panel._edit_btn.clicked.connect(panel._toggle_edit_mode)
    layout.addLayout(
        make_manager_footer_layout(
            left_widget=del_btn,
            right_widgets=[close_btn, panel._edit_btn],
            margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
            spacing=SPACE_SM,
        )
    )

