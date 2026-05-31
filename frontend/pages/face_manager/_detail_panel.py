from __future__ import annotations

import contextlib
import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from frontend.styles._colors import _ACCENT_HI_BG_20, _BORDER_DIM_00, _BORDER_DIM_55
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_SEMIBOLD,
    SIZE_FIELD_W_SM,
    SIZE_LABEL_W_LG,
    SPACE_10,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXL,
    SPACE_XXS,
    SPACE_XXXS,
)
from ._constants import (
    _ACCENT_HI,
    _TEXT_BTN_BLUE,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
    _compose_name,
)


class DetailPanel(QWidget):
    delete_requested = Signal(int)
    save_requested = Signal(int, dict)
    close_requested = Signal()
    enroll_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._face_id = None
        self._face = None
        self._edit_mode = False
        self._active_section = None
        self._section_hint_labels = {}
        self._section_fields = {}
        self._inputs = {}
        self._value_labels = {}
        self._build_empty()

    def _clear_layout(self):
        layout = self.layout()
        if not layout:
            return

        def _del(item):
            w = item.widget()
            if w is not None:
                w.deleteLater()
                return
            cl = item.layout()
            if cl is not None:
                while cl.count():
                    _del(cl.takeAt(0))
                cl.deleteLater()

        while layout.count():
            _del(layout.takeAt(0))

    def _build_empty(self):
        self._clear_layout()
        layout = self.layout()
        if layout is None:
            layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_w = QWidget()
        empty_w.setStyleSheet("background: transparent; border: none;")
        el = QVBoxLayout(empty_w)
        el.setAlignment(Qt.AlignmentFlag.AlignCenter)
        el.setSpacing(SPACE_10)
        el.setContentsMargins(SPACE_XXL, SPACE_XXL, SPACE_XXL, SPACE_XXL)

        title_lbl = QLabel("No person selected")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_lbl.setStyleSheet(f"font-size: {FONT_SIZE_BODY}px; font-weight: {FONT_WEIGHT_BOLD}; color: {_TEXT_SEC};")
        el.addWidget(title_lbl)

        sub_lbl = QLabel("Select a person from the roster to view their details, or enroll a new face.")
        sub_lbl.setWordWrap(True)
        sub_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub_lbl.setStyleSheet(f"font-size: {FONT_SIZE_CAPTION}px; color: {_TEXT_MUTED}; line-height: 1.5;")
        el.addWidget(sub_lbl)

        layout.addWidget(empty_w)

    def _build_section_header(self, title: str, focus_key: str):
        container = QWidget()
        container.setStyleSheet("background: transparent; border: none;")
        container.setCursor(Qt.CursorShape.PointingHandCursor)
        container.mousePressEvent = lambda e, k=focus_key: self._activate_section(k)

        row = QHBoxLayout(container)
        row.setContentsMargins(0, SPACE_SM, 0, SPACE_XXS)
        row.setSpacing(SPACE_SM)

        lbl = QLabel(title.upper())
        lbl.setStyleSheet(
            f"font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD}; color: {_TEXT_MUTED}; letter-spacing: {SPACE_XXXS}px;"
        )
        row.addWidget(lbl)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(
            "background: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0, "
            f"stop:0 {_ACCENT_HI_BG_20}, stop:1 {_BORDER_DIM_00}); border: none; max-height: {SPACE_XXXS}px;"
        )
        row.addWidget(line, stretch=1)

        hint_lbl = QLabel("edit →")
        hint_lbl.setStyleSheet(
            f"color: {_ACCENT_HI}; font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_SEMIBOLD}; "
            f"background: transparent; padding: 0 {SPACE_XS}px;"
        )
        hint_lbl.setVisible(False)
        hint_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._section_hint_labels[focus_key] = hint_lbl
        row.addWidget(hint_lbl)

        wrapper = QVBoxLayout()
        wrapper.setContentsMargins(0, 0, 0, 0)
        wrapper.setSpacing(0)
        wrapper.addWidget(container)
        return wrapper

    def _activate_section(self, section_key: str):
        if not self._edit_mode:
            return
        self._active_section = section_key
        for key, edit in self._inputs.items():
            edit.setVisible(False)
            vw = self._value_labels.get(key)
            if vw:
                vw.setVisible(True)
        for key in self._section_fields.get(section_key, []):
            e = self._inputs.get(key)
            if e:
                e.setVisible(True)
            vw = self._value_labels.get(key)
            if vw:
                vw.setVisible(False)
        keys = self._section_fields.get(section_key, [])
        if keys:
            self._focus_input(keys[0])

    def _focus_input(self, key: str):
        w = self._inputs.get(key)
        if w is None:
            return
        w.setFocus()
        with contextlib.suppress(Exception):
            w.selectAll()

    def _field_row(self, label: str, key: str, value: str, parent_layout: QVBoxLayout, required: bool = False):
        wrap = QWidget()
        wrap.setStyleSheet("background: transparent; border: none;")
        row = QHBoxLayout(wrap)
        row.setContentsMargins(0, SPACE_XXS, 0, SPACE_XXS)
        row.setSpacing(SPACE_10)

        lbl_text = f"{label} *" if required else label
        lbl = QLabel(f"{lbl_text}:")
        lbl.setStyleSheet(f"color: {_TEXT_SEC}; min-width: {SIZE_FIELD_W_SM}px; font-size: {FONT_SIZE_LABEL}px;")
        lbl.setFixedWidth(SIZE_LABEL_W_LG)
        row.addWidget(lbl)

        if value:
            value_lbl = QLabel(value)
            value_lbl.setStyleSheet(f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_BODY}px;")
        else:
            value_lbl = QLabel("not set")
            value_lbl.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; font-style: italic;")
        value_lbl.setWordWrap(True)
        row.addWidget(value_lbl, stretch=1)

        edit = QLineEdit(value)
        edit.setVisible(False)
        self._inputs[key] = edit
        self._value_labels[key] = value_lbl
        row.addWidget(edit, stretch=1)

        parent_layout.addWidget(wrap)
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background: {_BORDER_DIM_55}; border: none; max-height: {SPACE_XXXS}px;")
        parent_layout.addWidget(div)

    def _set_edit_mode(self, enabled: bool):
        self._edit_mode = enabled
        self._active_section = None
        for hint in self._section_hint_labels.values():
            hint.setVisible(enabled)
        for key, edit in self._inputs.items():
            edit.setEnabled(enabled)
            edit.setVisible(False)
            vw = self._value_labels.get(key)
            if vw:
                vw.setVisible(True)
        if hasattr(self, "_edit_btn"):
            if enabled:
                self._edit_btn.setText("Save")
                self._edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
            else:
                self._edit_btn.setText("Edit")
                self._edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
        if hasattr(self, "_edit_banner"):
            self._edit_banner.setVisible(enabled)
        if enabled:
            self._activate_section("identity")

    def _toggle_edit_mode(self):
        if self._face_id is None:
            return
        if not self._edit_mode:
            self._set_edit_mode(True)
            return

        first_name = self._inputs["first_name"].text().strip()
        second_name = self._inputs["second_name"].text().strip()
        if not first_name or not second_name:
            QMessageBox.warning(self, "Required Fields", "First name and second name are required.")
            self._focus_input("first_name" if not first_name else "second_name")
            return

        birth_val = self._inputs["birth_date"].text().strip()
        if birth_val:
            if not re.fullmatch(r"\d{2}-\d{2}-\d{4}", birth_val):
                QMessageBox.warning(self, "Invalid Date", "Birth date must be in DD-MM-YYYY format.")
                self._activate_section("personal")
                return
            dd, mm, yyyy = int(birth_val[:2]), int(birth_val[3:5]), int(birth_val[6:])
            if not (1 <= mm <= 12 and 1 <= dd <= 31 and 1900 <= yyyy <= 2100):
                QMessageBox.warning(self, "Invalid Date", "Please enter a valid birth date (DD-MM-YYYY).")
                self._activate_section("personal")
                return

        email_val = self._inputs["email"].text().strip()
        if email_val and not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", email_val):
            QMessageBox.warning(self, "Invalid Email", "Please enter a valid email address (e.g. user@example.com).")
            self._activate_section("contact")
            return

        full_name = _compose_name(
            first_name,
            second_name,
            self._inputs["third_name"].text().strip(),
            self._inputs["last_name"].text().strip(),
        )

        gender_widget = self._inputs.get("gender")
        gender_value = "unknown"
        if gender_widget is not None:
            if hasattr(gender_widget, "currentText"):
                gender_value = gender_widget.currentText().strip().lower() or "unknown"
            else:
                gender_value = gender_widget.text().strip().lower() or "unknown"

        is_authorized = self._inputs["authorized"].isChecked()
        updates = {
            "name": full_name,
            "department": self._inputs["department"].text().strip(),
            "address": self._inputs["address"].text().strip(),
            "country": self._inputs["country"].text().strip(),
            "birth_date": self._inputs["birth_date"].text().strip(),
            "gender": gender_value,
            "phone": self._inputs["phone"].text().strip(),
            "email": self._inputs["email"].text().strip(),
            "authorized_cameras": "all" if is_authorized else "[]",
        }
        self.save_requested.emit(self._face_id, updates)
        self._set_edit_mode(False)

    def load_face(self, face: dict):
        from ._detail_panel_content import build_face_content

        self._face_id = face["id"]
        self._face = face
        self._section_hint_labels = {}
        self._section_fields = {}
        self._inputs = {}
        self._value_labels = {}
        self._edit_mode = False
        self._active_section = None
        self._clear_layout()
        layout = self.layout()
        if layout is None:
            from PySide6.QtWidgets import QVBoxLayout as _VL

            layout = _VL(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        build_face_content(self, face, layout)

    def clear(self):
        self._face_id = None
        self._face = None
        self._edit_mode = False
        self._inputs = {}
        self._value_labels = {}
        self._section_hint_labels = {}
        self._build_empty()
