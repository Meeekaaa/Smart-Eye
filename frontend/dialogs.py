from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFontMetrics, QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
    QMessageBox,
)

from frontend.styles._btn_styles import _DANGER_BTN, _PRIMARY_BTN, _SECONDARY_BTN
from frontend.styles._colors import (
    _DB_BG_GRAD_2,
    _DB_BG_GRAD_3,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.styles.page_styles import muted_label_style
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_MICRO,
    RADIUS_LG,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_MD,
    SPACE_10,
    SPACE_LG,
    SPACE_MD,
    SPACE_XL,
    SPACE_XXXS,
)


_ICON_PATH = "frontend/assets/icons/icon.ico"


def _theme_color(name: str, fallback: str) -> str:
    try:
        from frontend.styles import _colors as _c

        return str(getattr(_c, name, fallback))
    except Exception:
        return fallback


def _button_styles() -> tuple[str, str, str]:
    try:
        from frontend.styles import _btn_styles as _b

        return str(_b._PRIMARY_BTN), str(_b._SECONDARY_BTN), str(_b._DANGER_BTN)
    except Exception:
        return _PRIMARY_BTN, _SECONDARY_BTN, _DANGER_BTN


def _scope_qpushbutton_qss(qss: str, scope: str = "QDialog") -> str:
    return qss.replace("QPushButton", f"{scope} QPushButton")


def _window_icon() -> QIcon:
    icon = QIcon(_ICON_PATH)
    return icon


def popup_surface_qss() -> str:
    bg2 = _theme_color("_DB_BG_GRAD_2", _DB_BG_GRAD_2)
    bg3 = _theme_color("_DB_BG_GRAD_3", _DB_BG_GRAD_3)
    bg_base = _theme_color("_BG_BASE", "#141a22")
    border_dark = _theme_color("_BORDER_DARK", "#2a3240")
    text_pri = _theme_color("_TEXT_PRI", _TEXT_PRI)
    text_muted = _theme_color("_TEXT_MUTED", _TEXT_MUTED)
    accent = _theme_color("_ACCENT", "#2f81f7")
    overlay = _theme_color("_BG_OVERLAY", "#1b2230")
    _primary, secondary, _danger = _button_styles()
    secondary_scoped = _scope_qpushbutton_qss(secondary)
    return f"""
        QDialog {{
            background-color: {bg2};
            border: {SPACE_XXXS}px solid {bg3};
            border-radius: {RADIUS_LG}px;
        }}
        QDialog QLabel {{ color: {text_pri}; background: transparent; }}
        QDialog QLineEdit, QDialog QTextEdit, QDialog QPlainTextEdit,
        QDialog QComboBox, QDialog QSpinBox, QDialog QDoubleSpinBox {{
            background-color: {bg_base};
            border: {SPACE_XXXS}px solid {border_dark};
            border-radius: {RADIUS_LG}px;
            color: {text_pri};
        }}
        QDialog QLineEdit:focus, QDialog QTextEdit:focus, QDialog QPlainTextEdit:focus,
        QDialog QComboBox:focus, QDialog QSpinBox:focus, QDialog QDoubleSpinBox:focus {{
            border-color: {accent};
        }}
        QDialog QComboBox QAbstractItemView {{
            background: {overlay};
            color: {text_pri};
            border: {SPACE_XXXS}px solid {border_dark};
            border-radius: {RADIUS_LG}px;
            selection-background-color: {accent};
        }}
        QDialog QAbstractButton:disabled {{ color: {text_muted}; }}
        {secondary_scoped}
    """


def apply_popup_theme(dlg: QDialog, base_stylesheet: str = "") -> None:
    flags = dlg.windowFlags() | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint
    dlg.setWindowFlags(flags)
    try:
        dlg.setWindowIcon(_window_icon())
    except (RuntimeError, OSError):
        return
    qss = popup_surface_qss()
    dlg.setStyleSheet("{}\n{}".format(base_stylesheet, qss) if base_stylesheet else qss)


def _std_icon(dialog: QDialog, icon: QMessageBox.Icon) -> QIcon:
    style = QApplication.style()
    if icon == QMessageBox.Icon.Warning:
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxWarning, None, dialog)
    if icon == QMessageBox.Icon.Critical:
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxCritical, None, dialog)
    if icon == QMessageBox.Icon.Question:
        return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxQuestion, None, dialog)
    return style.standardIcon(QStyle.StandardPixmap.SP_MessageBoxInformation, None, dialog)


def _build_dialog(title: str, text: str, icon: QMessageBox.Icon, buttons: list[tuple[str, int]], default_btn: int):
    dlg = QDialog()
    dlg.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.Dialog | Qt.WindowType.WindowTitleHint | Qt.WindowType.WindowCloseButtonHint)
    dlg.setWindowModality(Qt.ApplicationModal)
    dlg.setWindowTitle(title)
    pri = _theme_color("_TEXT_PRI", _TEXT_PRI)
    sec = _theme_color("_TEXT_SEC", _TEXT_SEC)
    primary_btn, secondary_btn, danger_btn = _button_styles()

    apply_popup_theme(
        dlg,
        f"""
        QLabel {{
            color: {pri};
            font-size: {FONT_SIZE_BODY}px;
            background: transparent;
        }}
        """,
    )

    layout = QVBoxLayout(dlg)
    layout.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
    layout.setSpacing(SPACE_MD)

    content_row = QHBoxLayout()
    content_row.setSpacing(SPACE_MD)

    icon_lbl = QLabel()
    icon_pix = _std_icon(dlg, icon).pixmap(44, 44)
    icon_lbl.setPixmap(icon_pix)
    icon_lbl.setFixedSize(44, 44)
    content_row.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignTop)

    text_wrap = QWidget()
    text_v = QVBoxLayout(text_wrap)
    text_v.setContentsMargins(0, 0, 0, 0)
    text_v.setSpacing(SPACE_10)

    msg_lbl = QLabel(text)
    msg_lbl.setWordWrap(True)
    msg_lbl.setStyleSheet(muted_label_style(color=sec, size=FONT_SIZE_MICRO))
    text_v.addWidget(msg_lbl)

    content_row.addWidget(text_wrap, stretch=1)
    layout.addLayout(content_row)

    btn_row = QHBoxLayout()
    btn_row.addStretch()
    btn_widgets: dict[int, QPushButton] = {}
    danger_default = icon in (QMessageBox.Icon.Warning, QMessageBox.Icon.Critical, QMessageBox.Icon.Question)
    for label, code in buttons:
        btn = QPushButton(label)
        btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        if code == default_btn and danger_default:
            btn.setStyleSheet(danger_btn)
        elif code == default_btn:
            btn.setStyleSheet(primary_btn)
        else:
            btn.setStyleSheet(secondary_btn)
        btn.clicked.connect(lambda _=False, c=code: dlg.done(c))
        btn_row.addWidget(btn)
        btn_widgets[code] = btn
    layout.addLayout(btn_row)

    if default_btn in btn_widgets:
        btn_widgets[default_btn].setFocus()

    try:
        fm = QFontMetrics(msg_lbl.font())
        lines = (text or "").splitlines() or [""]
        max_line = max(fm.horizontalAdvance(line) for line in lines)
        min_w = max_line + 44 + SPACE_XL * 2 + SPACE_MD * 2
        dlg.setMinimumWidth(max(360, min_w))
    except (ValueError, TypeError):
        pass

    return dlg


def _center_on_active(dlg: QDialog) -> None:
    ref = QApplication.activeWindow()
    if ref is None:
        return
    try:
        dlg.adjustSize()
        rect = dlg.frameGeometry()
        rect.moveCenter(ref.frameGeometry().center())
        dlg.move(rect.topLeft())
    except (RuntimeError, AttributeError):
        pass


def _buttons_from_mask(mask: int) -> list[tuple[str, int]]:
    mapping = [
        ("Yes", QMessageBox.StandardButton.Yes),
        ("No", QMessageBox.StandardButton.No),
        ("Cancel", QMessageBox.StandardButton.Cancel),
        ("OK", QMessageBox.StandardButton.Ok),
    ]
    out: list[tuple[str, int]] = []
    for label, code in mapping:
        if mask & code:
            out.append((label, code))
    return out or [("OK", QMessageBox.StandardButton.Ok)]


def show_info(parent, title, text, buttons=QMessageBox.StandardButton.Ok, default_button=None) -> int:
    btns = _buttons_from_mask(int(buttons))
    default_btn = default_button if default_button in {c for _, c in btns} else btns[0][1]
    dlg = _build_dialog(title, text, QMessageBox.Icon.Information, btns, default_btn)
    _center_on_active(dlg)
    return dlg.exec()


def show_warning(parent, title, text, buttons=QMessageBox.StandardButton.Ok, default_button=None) -> int:
    btns = _buttons_from_mask(int(buttons))
    default_btn = default_button if default_button in {c for _, c in btns} else btns[0][1]
    dlg = _build_dialog(title, text, QMessageBox.Icon.Warning, btns, default_btn)
    _center_on_active(dlg)
    return dlg.exec()


def show_error(parent, title, text, buttons=QMessageBox.StandardButton.Ok, default_button=None) -> int:
    btns = _buttons_from_mask(int(buttons))
    default_btn = default_button if default_button in {c for _, c in btns} else btns[0][1]
    dlg = _build_dialog(title, text, QMessageBox.Icon.Critical, btns, default_btn)
    _center_on_active(dlg)
    return dlg.exec()


def confirm(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, default_button=None) -> int:
    btns = _buttons_from_mask(int(buttons))
    default_btn = default_button if default_button in {c for _, c in btns} else btns[0][1]
    dlg = _build_dialog(title, text, QMessageBox.Icon.Question, btns, default_btn)
    _center_on_active(dlg)
    return dlg.exec()


def patch_messagebox():
    QMessageBox.information = show_info
    QMessageBox.warning = show_warning
    QMessageBox.critical = show_error
    QMessageBox.question = confirm
