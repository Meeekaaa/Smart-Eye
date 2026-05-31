from __future__ import annotations

import contextlib
import re

from PySide6.QtCore import Qt, QRegularExpression, QSettings, QTimer
from PySide6.QtGui import QFont, QIcon, QRegularExpressionValidator, QPixmap, QTransform
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QComboBox,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from frontend.app_theme import safe_set_point_size
from frontend.widgets.face_capture_widget import FaceCaptureWidget
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.styles._colors import _WARNING_ORANGE
from frontend.styles._input_styles import _FORM_COMBO
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_HEADING,
    FONT_SIZE_LABEL,
    RADIUS_MD,
    RADIUS_NONE,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_MD,
    SIZE_LABEL_W,
    SIZE_ROW_84,
    SIZE_ROW_MD,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_6,
    SPACE_MD,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXXS,
)

from ._constants import (
    _DANGER,
    _BG_RAISED,
    _BORDER_DIM,
    _STYLESHEET,
    _SUCCESS,
    _TEXT_BTN_BLUE,
    _TEXT_BTN_RED,
    _TEXT_PRI,
    _TEXT_SEC,
    _compose_name,
)
from ._workers import EnrollWorker


class _EnrollPanelMixin:
    def _enroll_dialog(self):
        if self._enroll_panel is None:
            self._enroll_panel = self._build_enroll_widget()
            self._right_stack.addWidget(self._enroll_panel)
        for edit in [
            self._ef_first,
            self._ef_second,
            self._ef_third,
            self._ef_last,
            self._ef_dept,
            self._ef_address,
            self._ef_country,
            self._ef_birth,
            self._ef_phone,
            self._ef_email,
            getattr(self, "_ef_national_id", None),
        ]:
            edit.clear()
        self._ef_auth.setChecked(True)
        self._enroll_capture.reset()
        self._stop_enroll_status_spinner()
        self._stop_enroll_button_spinner()
        self._enroll_status_lbl.setText("")
        self._pre_enroll_sizes = self._splitter.sizes()
        self._right_stack.setCurrentIndex(1)
        self._enroll_capture.start_camera(0)

    def _close_enroll_panel(self):
        self._stop_enroll_status_spinner()
        self._stop_enroll_button_spinner()
        if self._enroll_panel is not None:
            with contextlib.suppress(Exception):
                self._enroll_capture.stop_camera()
            self._right_stack.removeWidget(self._enroll_panel)
            self._enroll_panel.deleteLater()
            self._enroll_panel = None
        self._close_details()
        self._right_stack.setCurrentIndex(0)
        if hasattr(self, "_pre_enroll_sizes"):
            self._splitter.setSizes(self._pre_enroll_sizes)

    def _build_enroll_widget(self) -> QWidget:
        panel = QWidget()
        panel.setStyleSheet(_STYLESHEET)
        root = QVBoxLayout(panel)
        root.setContentsMargins(SPACE_20, SPACE_20, SPACE_20, SPACE_20)
        root.setSpacing(SPACE_14)

        hdr = QLabel("Enroll New Person")
        hf = QFont()
        safe_set_point_size(hf, FONT_SIZE_HEADING)
        hf.setBold(True)
        hdr.setFont(hf)
        root.addWidget(hdr)

        sub = QLabel("Fill in the details, then use the camera to capture face photos. At least 1 photo is required.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px;")
        root.addWidget(sub)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(SPACE_10)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        def _add_field(label, widget, *, with_bottom_border=True):
            row = QWidget()
            _row_border = (
                f"border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};" if with_bottom_border else "border-bottom: none;"
            )
            row.setStyleSheet(f"background: transparent; {_row_border}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(0)
            lbl = QLabel(label)
            lbl.setFixedWidth(SIZE_LABEL_W)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lbl.setStyleSheet(
                f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; padding-right: {SPACE_MD}px; background: transparent; border: none;"
            )
            rl.addWidget(lbl)
            # Use a non-transparent combo style for dropdowns so the popup
            # background and items are rendered with proper surface colors.
            if isinstance(widget, QComboBox):
                widget.setStyleSheet(_FORM_COMBO)
            else:
                widget.setStyleSheet(
                    f"background: transparent; border: none; border-radius: {RADIUS_NONE}px;"
                    f" padding: 0 {SPACE_XS}px; color: {_TEXT_PRI}; font-size: {FONT_SIZE_BODY}px;"
                )
            widget.setFixedHeight(SIZE_CONTROL_MD)
            rl.addWidget(widget, stretch=1)
            return row

        _name_re = QRegularExpression(r"[\p{L} '\-.]*")
        _dept_re = QRegularExpression(r".*")
        _addr_re = QRegularExpression(r"[\p{L}\p{N} '\-.,/#&()]*")
        _country_re = QRegularExpression(r"[\p{L} '\-.]*")
        _nid_re = QRegularExpression(r"[A-Za-z0-9\- ]*")
        _phone_re = QRegularExpression(r"[\d+\-() ]*")
        _email_re = QRegularExpression(r"[a-zA-Z0-9!#$%&'*+\-/=?^_`{|}~@.\[\]]*")

        self._ef_first = QLineEdit()
        self._ef_first.setPlaceholderText("e.g. John")
        self._ef_first.setValidator(QRegularExpressionValidator(_name_re))
        self._ef_first.setMaxLength(50)
        self._ef_second = QLineEdit()
        self._ef_second.setPlaceholderText("e.g. Smith")
        self._ef_second.setValidator(QRegularExpressionValidator(_name_re))
        self._ef_second.setMaxLength(50)
        self._ef_third = QLineEdit()
        self._ef_third.setPlaceholderText("Optional")
        self._ef_third.setValidator(QRegularExpressionValidator(_name_re))
        self._ef_third.setMaxLength(50)
        self._ef_last = QLineEdit()
        self._ef_last.setPlaceholderText("Optional")
        self._ef_last.setValidator(QRegularExpressionValidator(_name_re))
        self._ef_last.setMaxLength(50)
        self._ef_dept = QLineEdit()
        self._ef_dept.setPlaceholderText("e.g. Engineering")
        self._ef_dept.setValidator(QRegularExpressionValidator(_dept_re))
        self._ef_dept.setMaxLength(80)
        self._ef_address = QLineEdit()
        self._ef_address.setPlaceholderText("Optional")
        self._ef_address.setValidator(QRegularExpressionValidator(_addr_re))
        self._ef_address.setMaxLength(120)
        self._ef_country = QLineEdit()
        self._ef_country.setPlaceholderText("Optional")
        self._ef_country.setValidator(QRegularExpressionValidator(_country_re))
        self._ef_country.setMaxLength(60)
        self._ef_national_id = QLineEdit()
        self._ef_national_id.setPlaceholderText("National ID (optional)")
        self._ef_national_id.setValidator(QRegularExpressionValidator(_nid_re))
        self._ef_national_id.setMaxLength(60)
        self._ef_birth = QLineEdit()
        self._ef_birth.setPlaceholderText("DD-MM-YYYY")
        self._ef_birth.setMaxLength(10)
        self._ef_phone = QLineEdit()
        self._ef_phone.setPlaceholderText("Optional")
        self._ef_phone.setValidator(QRegularExpressionValidator(_phone_re))
        self._ef_phone.setMaxLength(25)
        self._ef_email = QLineEdit()
        self._ef_email.setPlaceholderText("Optional")
        self._ef_email.setValidator(QRegularExpressionValidator(_email_re))
        self._ef_email.setMaxLength(100)

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
                pos = self._ef_birth.cursorPosition()
                self._ef_birth.setText(new_text)
                extra = new_text.count("-", 0, pos) - text.count("-", 0, pos)
                self._ef_birth.setCursorPosition(min(pos + extra, len(new_text)))
                _date_guard[0] = False

        self._ef_birth.textChanged.connect(_on_birth_changed)

        fields_widget = QWidget()
        fields_widget.setStyleSheet(f"background: {_BG_RAISED}; border-radius: {RADIUS_MD}px;")
        fields_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        fields_layout = QVBoxLayout(fields_widget)
        fields_layout.setContentsMargins(0, 0, 0, 0)
        fields_layout.setSpacing(0)
        for lbl_text, widget in [
            ("First Name *", self._ef_first),
            ("Second Name *", self._ef_second),
            ("Third Name", self._ef_third),
            ("Last Name", self._ef_last),
            ("Department", self._ef_dept),
            ("National ID", self._ef_national_id),
            ("Address", self._ef_address),
            ("Country", self._ef_country),
            ("Birth Date", self._ef_birth),
            ("Phone", self._ef_phone),
            ("Email", self._ef_email),
        ]:
            fields_layout.addWidget(_add_field(lbl_text, widget))

        # Gender selection
        self._ef_gender = QComboBox()
        self._ef_gender.addItems(["Unknown", "Male", "Female"])
        self._ef_gender.setCurrentIndex(0)
        fields_layout.addWidget(_add_field("Gender", self._ef_gender, with_bottom_border=False))

        access_row = QWidget()
        access_row.setFixedHeight(SIZE_ROW_MD)
        access_row.setStyleSheet("background: transparent; border: none;")
        ar = QHBoxLayout(access_row)
        ar.setContentsMargins(0, 0, 0, 0)
        ar.setSpacing(0)
        access_lbl = QLabel("Access")
        access_lbl.setFixedWidth(SIZE_LABEL_W)
        access_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        access_lbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; padding-right: {SPACE_MD}px; background: transparent;"
        )
        ar.addWidget(access_lbl)
        self._ef_auth = ToggleSwitch()
        self._ef_auth.setChecked(True)
        _toggle_label = QLabel("Grant access (authorized)")
        _toggle_label.setStyleSheet(
            f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_BODY}px; background: transparent; border: none; padding: 0 {SPACE_SM}px;"
        )
        toggle_wrap = QHBoxLayout()
        toggle_wrap.setContentsMargins(SPACE_XS, 0, 0, 0)
        toggle_wrap.setSpacing(0)
        toggle_wrap.addWidget(self._ef_auth)
        toggle_wrap.addWidget(_toggle_label)
        toggle_wrap.addStretch()
        ar.addLayout(toggle_wrap, stretch=1)
        fields_layout.addWidget(access_row)

        fields_row = QHBoxLayout()
        fields_row.setContentsMargins(0, 0, 0, 0)
        fields_row.setSpacing(0)
        fields_row.addWidget(fields_widget)
        fields_row.addSpacing(SPACE_SM)
        left_layout.addLayout(fields_row, stretch=1)

        footer = QWidget()
        footer.setFixedHeight(SIZE_ROW_84)
        footer.setStyleSheet("background: transparent;")
        footer_vbox = QVBoxLayout(footer)
        footer_vbox.setContentsMargins(0, SPACE_6, 0, 0)
        footer_vbox.setSpacing(SPACE_XS)

        status_row = QHBoxLayout()
        status_row.setContentsMargins(0, 0, 0, 0)
        status_row.setSpacing(SPACE_6)
        self._enroll_loading_icon_lbl = QLabel()
        self._enroll_loading_icon_lbl.setFixedSize(14, 14)
        self._enroll_loading_icon_lbl.setVisible(False)
        status_row.addWidget(self._enroll_loading_icon_lbl)

        self._enroll_status_lbl = QLabel("")
        self._enroll_status_lbl.setWordWrap(False)
        self._enroll_status_lbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_CAPTION}px; padding: 0 {SPACE_XS}px; background: transparent;"
        )
        status_row.addWidget(self._enroll_status_lbl, 1)
        footer_vbox.addLayout(status_row)
        footer_vbox.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, SPACE_SM)
        btn_row.setSpacing(SPACE_SM)
        btn_row.addStretch()

        self._enroll_save_btn = QPushButton("Save")
        self._enroll_save_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._enroll_save_btn.setStyleSheet(_TEXT_BTN_BLUE)
        btn_row.addWidget(self._enroll_save_btn)

        cancel_btn = QPushButton("Close")
        cancel_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        cancel_btn.setStyleSheet(_TEXT_BTN_RED)
        cancel_btn.clicked.connect(self._close_enroll_panel)
        btn_row.addWidget(cancel_btn)

        btn_row.addStretch()
        footer_vbox.addLayout(btn_row)
        left_layout.addWidget(footer)

        splitter.addWidget(left_widget)
        self._enroll_capture = FaceCaptureWidget()
        splitter.addWidget(self._enroll_capture)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        _qs = QSettings("SmartEye", "FaceEnroll")
        _saved = _qs.value("splitter/sizes")
        if _saved and len(_saved) == 2:
            try:
                splitter.setSizes([int(_saved[0]), int(_saved[1])])
            except (ValueError, TypeError):
                splitter.setSizes([320, 640])
        else:
            splitter.setSizes([320, 640])
        splitter.splitterMoved.connect(lambda _pos, _idx: _qs.setValue("splitter/sizes", splitter.sizes()))
        root.addWidget(splitter, stretch=1)

        self._enroll_save_btn.clicked.connect(lambda: self._do_save_enroll(panel))
        return panel

    def _start_enroll_status_spinner(self) -> None:
        base_icon = QPixmap("frontend/assets/icons/loading.png")
        if base_icon.isNull() or not hasattr(self, "_enroll_loading_icon_lbl"):
            return

        self._stop_enroll_status_spinner()
        angle = 0

        def _render_frame() -> None:
            rotated = base_icon.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self._enroll_loading_icon_lbl.setPixmap(
                rotated.scaled(
                    14,
                    14,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        def _tick() -> None:
            nonlocal angle
            angle = (angle + 18) % 360
            _render_frame()

        _render_frame()
        self._enroll_loading_icon_lbl.setVisible(True)
        self._enroll_status_spin_timer = QTimer(self)
        self._enroll_status_spin_timer.setInterval(40)
        self._enroll_status_spin_timer.timeout.connect(_tick)
        self._enroll_status_spin_timer.start()

    def _stop_enroll_status_spinner(self) -> None:
        timer = getattr(self, "_enroll_status_spin_timer", None)
        if timer is not None:
            timer.stop()
            self._enroll_status_spin_timer = None
        if hasattr(self, "_enroll_loading_icon_lbl"):
            self._enroll_loading_icon_lbl.clear()
            self._enroll_loading_icon_lbl.setVisible(False)

    def _start_enroll_button_spinner(self) -> None:
        base_icon = QPixmap("frontend/assets/icons/loading.png")
        if base_icon.isNull():
            return

        self._stop_enroll_button_spinner()
        angle = 0

        def _render_frame() -> None:
            rotated = base_icon.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self._enroll_save_btn.setIcon(
                QIcon(
                    rotated.scaled(
                        14,
                        14,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            )

        def _tick() -> None:
            nonlocal angle
            angle = (angle + 18) % 360
            _render_frame()

        _render_frame()
        self._enroll_btn_spin_timer = QTimer(self)
        self._enroll_btn_spin_timer.setInterval(40)
        self._enroll_btn_spin_timer.timeout.connect(_tick)
        self._enroll_btn_spin_timer.start()

    def _stop_enroll_button_spinner(self) -> None:
        timer = getattr(self, "_enroll_btn_spin_timer", None)
        if timer is not None:
            timer.stop()
            self._enroll_btn_spin_timer = None
        if hasattr(self, "_enroll_save_btn"):
            self._enroll_save_btn.setIcon(QIcon())

    def _do_save_enroll(self, panel: QWidget):
        first_name = self._ef_first.text().strip()
        second_name = self._ef_second.text().strip()
        if not first_name or not second_name:
            QMessageBox.warning(panel, "Required Fields", "Please enter first name and second name.")
            (self._ef_first if not first_name else self._ef_second).setFocus()
            return

        birth_val = self._ef_birth.text().strip()
        if birth_val:
            if not re.fullmatch(r"\d{2}-\d{2}-\d{4}", birth_val):
                QMessageBox.warning(panel, "Invalid Date", "Birth date must be in DD-MM-YYYY format.")
                self._ef_birth.setFocus()
                return
            dd, mm, yyyy = int(birth_val[:2]), int(birth_val[3:5]), int(birth_val[6:])
            if not (1 <= mm <= 12 and 1 <= dd <= 31 and 1900 <= yyyy <= 2100):
                QMessageBox.warning(panel, "Invalid Date", "Please enter a valid birth date (DD-MM-YYYY).")
                self._ef_birth.setFocus()
                return

        email_val = self._ef_email.text().strip()
        if email_val and not re.fullmatch(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", email_val):
            QMessageBox.warning(panel, "Invalid Email", "Please enter a valid email address (e.g. user@example.com).")
            self._ef_email.setFocus()
            return

        name = _compose_name(first_name, second_name, self._ef_third.text().strip(), self._ef_last.text().strip())
        images = self._enroll_capture.get_captures()
        if not images:
            QMessageBox.warning(panel, "No Photos", "Please capture at least one face photo before saving.")
            return

        self._enroll_save_btn.setEnabled(False)
        self._enroll_save_btn.setText("Processing...")
        self._start_enroll_button_spinner()
        self._start_enroll_status_spinner()
        self._enroll_status_lbl.setText("Extracting face embeddings, please wait...")
        self._enroll_status_lbl.setStyleSheet(f"color: {_WARNING_ORANGE}; font-size: {FONT_SIZE_LABEL}px; padding: {SPACE_XS}px;")

        self._worker = EnrollWorker(
            images,
            name,
            self._ef_dept.text().strip(),
            self._ef_auth.isChecked(),
            gender=self._ef_gender.currentText().strip(),
            address=self._ef_address.text().strip(),
            country=self._ef_country.text().strip(),
            national_id=self._ef_national_id.text().strip(),
            birth_date=self._ef_birth.text().strip(),
            phone=self._ef_phone.text().strip(),
            email=self._ef_email.text().strip(),
        )

        def _on_progress(msg):
            self._enroll_status_lbl.setText(msg)

        def _on_done(ok, msg):
            self._enroll_save_btn.setEnabled(True)
            self._enroll_save_btn.setText("Save")
            self._stop_enroll_button_spinner()
            self._stop_enroll_status_spinner()
            self._worker = None
            if ok:
                self._enroll_status_lbl.setText(msg)
                self._enroll_status_lbl.setStyleSheet(f"color: {_SUCCESS}; font-size: {FONT_SIZE_LABEL}px; padding: {SPACE_XS}px;")

                try:
                    from backend.models.model_loader import get_face_model

                    fm = get_face_model()
                    if fm is not None:
                        fm.invalidate_known_cache()
                except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                    pass
                self._close_enroll_panel()
                self._refresh()
            else:
                self._enroll_status_lbl.setText(msg)
                self._enroll_status_lbl.setStyleSheet(f"color: {_DANGER}; font-size: {FONT_SIZE_LABEL}px; padding: {SPACE_XS}px;")

        self._worker.progress.connect(_on_progress)
        self._worker.done.connect(_on_done)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

