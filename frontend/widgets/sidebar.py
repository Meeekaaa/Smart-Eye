from __future__ import annotations

from pathlib import Path
import json as _json

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QBrush, QPixmap, QIcon, QRegion
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QToolButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend.app_theme import safe_set_point_size
from frontend.icon_theme import themed_existing_pixmap, themed_icon_pixmap
from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_HI,
    _ACCENT_HI_BG_10,
    _ACCENT_HI_BG_20,
    _BG_BASE_92,
    _BG_NAV_ALT,
    _BG_NAV_DARK,
    _BG_SIDEBAR_START,
    _MUTED_BORDER_60,
    _TEXT_MUTED,
    _TEXT_ON_ACCENT,
    _TEXT_PRI,
    _TEXT_SEC,
    _WHITE_02,
    _WHITE_03,
    _WHITE_04,
)
from frontend.styles._shadows import apply_shadow_float, apply_shadow_glow
from frontend.styles.page_styles import muted_label_style, text_style
from frontend.ui_tokens import (
    FONT_SIZE_15,
    FONT_SIZE_9,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_LARGE,
    FONT_SIZE_TINY,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_HEAVY,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_14,
    RADIUS_6,
    RADIUS_MD,
    RADIUS_NONE,
    RADIUS_SM,
    RADIUS_XS,
    SIZE_CONTROL_MD,
    SIZE_ICON_LG,
    SIZE_ICON_XS,
    SIZE_ROW_MD,
    SPACE_10,
    SPACE_11,
    SPACE_14,
    SPACE_20,
    SPACE_3,
    SPACE_6,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
)
from frontend.navigation import NAV_ITEMS


LOGO_ICON_PATH = "frontend/assets/icons/logo.png"

_BG_SIDEBAR = _BG_SIDEBAR_START
_BORDER_SIDE = _BG_NAV_DARK

_SIDEBAR_COLLAPSED = 62
_SIDEBAR_EXPANDED = 184
_LOGO_SIZE_EXPANDED = 128
_LOGO_SIZE_WORDMARK = 62
_LOGO_SIZE_COLLAPSED_ICON = 36
_LOGO_SIZE_EXPANDED_ICON = 46
_LOGO_TRIMMED_PIX: QPixmap | None = None


def _read_app_info() -> dict:
    try:
        with open("app_info.json", "r", encoding="utf-8") as f:
            return _json.load(f)
    except (OSError, ValueError):
        return {"version": "0.1.0-alpha"}


_APP_INFO = _read_app_info()


def _reload_color_tokens() -> None:
    global _ACCENT
    global _ACCENT_HI
    global _ACCENT_HI_BG_10
    global _ACCENT_HI_BG_20
    global _BG_BASE_92
    global _BG_NAV_ALT
    global _BG_NAV_DARK
    global _BG_SIDEBAR_ALT
    global _BG_SIDEBAR_START
    global _MUTED_BORDER_60
    global _TEXT_MUTED
    global _TEXT_ON_ACCENT
    global _TEXT_PRI
    global _TEXT_SEC
    global _WHITE_02
    global _WHITE_03
    global _WHITE_04
    global _BG_SIDEBAR
    global _BORDER_SIDE

    try:
        from frontend.styles import _colors as _c

        _ACCENT = _c._ACCENT
        _ACCENT_HI = _c._ACCENT_HI
        _ACCENT_HI_BG_10 = _c._ACCENT_HI_BG_10
        _ACCENT_HI_BG_20 = _c._ACCENT_HI_BG_20
        _BG_BASE_92 = _c._BG_BASE_92
        _BG_NAV_ALT = _c._BG_NAV_ALT
        _BG_NAV_DARK = _c._BG_NAV_DARK
        _BG_SIDEBAR_ALT = _c._BG_SIDEBAR_ALT
        _BG_SIDEBAR_START = _c._BG_SIDEBAR_START
        _MUTED_BORDER_60 = _c._MUTED_BORDER_60
        _TEXT_MUTED = _c._TEXT_MUTED
        _TEXT_ON_ACCENT = _c._TEXT_ON_ACCENT
        _TEXT_PRI = _c._TEXT_PRI
        _TEXT_SEC = _c._TEXT_SEC
        _WHITE_02 = _c._WHITE_02
        _WHITE_03 = _c._WHITE_03
        _WHITE_04 = _c._WHITE_04
        _BG_SIDEBAR = _BG_SIDEBAR_START
        _BORDER_SIDE = _BG_NAV_DARK
    except Exception:
        pass


class _LogoMonogram(QWidget):
    def __init__(self, size: int, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(size, size)
        self._pix = None
        global _LOGO_TRIMMED_PIX
        try:
            if _LOGO_TRIMMED_PIX is None:
                pix = QPixmap(LOGO_ICON_PATH)
                if not pix.isNull():
                    # Use Qt's native alpha-mask bounds (fast C++ path) instead of Python pixel loops.
                    mask = pix.mask()
                    rect = QRegion(mask).boundingRect() if not mask.isNull() else pix.rect()
                    _LOGO_TRIMMED_PIX = pix.copy(rect) if rect.isValid() else pix
            self._pix = _LOGO_TRIMMED_PIX
        except (OSError, RuntimeError):
            self._pix = None

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self._pix:
            scaled = self._pix.scaled(
                self.width(),
                self.height(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            scaled = themed_existing_pixmap(scaled)
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            p.drawPixmap(x, y, scaled)
        else:
            path = QPainterPath()
            path.addRoundedRect(0, 0, self.width(), self.height(), self.width() * 0.22, self.height() * 0.22)
            p.fillPath(path, QBrush(QColor(_ACCENT)))
            p.setPen(QColor(_TEXT_ON_ACCENT))
            f = QFont()
            f.setPixelSize(int(self.height() * 0.44))
            f.setBold(True)
            p.setFont(f)
            p.drawText(0, 0, self.width(), self.height(), Qt.AlignmentFlag.AlignCenter, "S")
        p.end()


class NavButton(QWidget):
    def __init__(self, label: str, icon: str, key: str, on_click, parent=None):
        super().__init__(parent)
        self._key = key
        self._on_click = on_click
        self._active = False
        self._locked = False
        self._has_pix = False
        self._focused = False
        self._icon_path = str(icon or "")
        self.setFixedHeight(SIZE_CONTROL_MD)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        icon_cell = QWidget()
        icon_cell.setFixedWidth(SIZE_ROW_MD)
        icon_cell_l = QHBoxLayout(icon_cell)
        icon_cell_l.setContentsMargins(SPACE_10, 0, 0, 0)
        icon_cell_l.setSpacing(0)
        layout.addWidget(icon_cell)

        inner = QHBoxLayout()
        inner.setContentsMargins(0, 0, SPACE_10, 0)
        inner.setSpacing(SPACE_10)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setFixedWidth(SIZE_ICON_XS)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_glow = None
        if self._icon_path:
            pix = themed_icon_pixmap(self._icon_path, FONT_SIZE_LARGE, FONT_SIZE_LARGE)
            if not pix.isNull():
                self._icon_lbl.setPixmap(pix)
                self._icon_lbl.setText("")
                self._has_pix = True
                self._icon_lbl.setStyleSheet("background: transparent; border: none;")
                self._icon_glow = apply_shadow_float(self._icon_lbl, _ACCENT_HI)
            else:
                self._icon_lbl.setStyleSheet(
                    f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_15}px;"
                    f" background: {_WHITE_02};"
                    f" border: {SPACE_XXXS}px dashed {_MUTED_BORDER_60}; border-radius: {RADIUS_SM}px;"
                )
        else:
            self._icon_lbl.setStyleSheet(
                f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_15}px;"
                f" background: {_WHITE_02};"
                f" border: {SPACE_XXXS}px dashed {_MUTED_BORDER_60}; border-radius: {RADIUS_SM}px;"
            )
        icon_cell_l.addWidget(self._icon_lbl)

        self._text_lbl = QLabel(label)
        self._text_lbl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD}; background: transparent;"
        )
        self._text_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self._text_lbl.setMaximumWidth(0)
        inner.addWidget(self._text_lbl)

        self._text_anim = QPropertyAnimation(self._text_lbl, b"maximumWidth", self)
        self._text_anim.setDuration(260)
        self._text_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        layout.addLayout(inner)
        layout.addStretch(0)
        self._inner = inner
        self._apply_style(False)

    def refresh_icon_tint(self) -> None:
        if not self._icon_path:
            return
        pix = themed_icon_pixmap(self._icon_path, FONT_SIZE_LARGE, FONT_SIZE_LARGE)
        if pix.isNull():
            self._has_pix = False
            self._icon_lbl.setPixmap(QPixmap())
            self._icon_lbl.setText("")
            return
        self._icon_lbl.setPixmap(pix)
        self._icon_lbl.setText("")
        self._has_pix = True
        self._icon_lbl.setStyleSheet("background: transparent; border: none;")
        if self._icon_glow is None:
            self._icon_glow = apply_shadow_glow(self._icon_lbl, _ACCENT_HI)
        self._apply_style(False)

    def set_active(self, active: bool):
        self._active = active
        self._apply_style(False)

    def set_locked(self, locked: bool):
        self._locked = locked
        self.setEnabled(not locked)
        self.setCursor(Qt.CursorShape.ForbiddenCursor if locked else Qt.CursorShape.PointingHandCursor)
        self._apply_style(False)

    def expand(self, expanded: bool):
        self._text_anim.stop()
        self._text_anim.setStartValue(self._text_lbl.maximumWidth())
        self._text_anim.setEndValue(300 if expanded else 0)
        self._text_anim.start()

    def _apply_style(self, hovered: bool):
        focused = self._focused and not self._locked
        if self._locked:
            self.setStyleSheet("background: transparent; border-radius: {r}px;".format(r=RADIUS_MD))
            if self._has_pix and self._icon_glow:
                self._icon_glow.setBlurRadius(0)
            self._icon_lbl.setStyleSheet(
                "{style} background: transparent; opacity: 0.6;".format(style=muted_label_style(size=FONT_SIZE_LABEL))
            )
            self._text_lbl.setStyleSheet(
                f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};"
                f" background: transparent; opacity: 0.5;"
            )
            return
        if self._active:
            self.setStyleSheet("background: transparent; border-radius: {r}px;".format(r=RADIUS_MD))
            if self._has_pix and self._icon_glow:
                glow_color = self._icon_glow.color()
                glow_color.setAlpha(180)
                self._icon_glow.setColor(glow_color)
                self._icon_glow.setBlurRadius(18)
            if not self._has_pix:
                self._icon_lbl.setStyleSheet(
                    f"color: {_ACCENT_HI}; font-size: {FONT_SIZE_15}px;"
                    f" background: {_WHITE_04};"
                    f" border: {SPACE_XXXS}px dashed {_MUTED_BORDER_60}; border-radius: {RADIUS_SM}px;"
                )
            self._text_lbl.setStyleSheet(
                f"color: {_ACCENT_HI}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_BOLD}; background: transparent;"
            )
        elif hovered or focused:
            self.setStyleSheet("background: transparent; border-radius: {r}px;".format(r=RADIUS_MD))
            if self._has_pix and self._icon_glow:
                glow_color = self._icon_glow.color()
                glow_color.setAlpha(140)
                self._icon_glow.setColor(glow_color)
                self._icon_glow.setBlurRadius(10)
            if not self._has_pix:
                self._icon_lbl.setStyleSheet(
                    f"color: {_ACCENT_HI}; font-size: {FONT_SIZE_15}px;"
                    f" background: {_WHITE_03};"
                    f" border: {SPACE_XXXS}px dashed {_MUTED_BORDER_60}; border-radius: {RADIUS_SM}px;"
                )
            self._text_lbl.setStyleSheet(
                f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD}; background: transparent;"
            )
            if focused:
                self.setStyleSheet("background: {bg}; border-radius: {r}px;".format(bg=_ACCENT_HI_BG_10, r=RADIUS_MD))
        else:
            self.setStyleSheet("background: transparent; border-radius: {r}px;".format(r=RADIUS_MD))
            if self._has_pix and self._icon_glow:
                glow_color = self._icon_glow.color()
                glow_color.setAlpha(0)
                self._icon_glow.setColor(glow_color)
                self._icon_glow.setBlurRadius(0)
            if not self._has_pix:
                self._icon_lbl.setStyleSheet(
                    f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_15}px;"
                    f" background: {_WHITE_02};"
                    f" border: {SPACE_XXXS}px dashed {_MUTED_BORDER_60}; border-radius: {RADIUS_SM}px;"
                )
            self._text_lbl.setStyleSheet(
                f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD}; background: transparent;"
            )

    def enterEvent(self, event):
        if not self._active and not self._locked:
            self._apply_style(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if not self._active and not self._locked:
            self._apply_style(False)
        super().leaveEvent(event)

    def focusInEvent(self, event):
        self._focused = True
        self._apply_style(False)
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._focused = False
        self._apply_style(False)
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self._locked and callable(self._on_click):
                self._on_click(self._key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if not self._locked and callable(self._on_click):
                self._on_click(self._key)
            return
        super().keyPressEvent(event)


class SidebarWidget(QWidget):
    def __init__(self, on_navigate, on_logout, current_theme: str, parent=None):
        super().__init__(parent)
        self._on_navigate = on_navigate
        self._on_logout = on_logout
        self._expanded = False
        self._nav_btns: dict[str, NavButton] = {}
        self._section_labels: list[QLabel] = []
        self._section_anims: list[QPropertyAnimation] = []
        self._section_btn_keys: list[list[str]] = []
        self._account: dict | None = None
        self._top_divider = None
        self._bottom_divider = None
        self._scroll = None
        self._logout_icon_path = "frontend/assets/icons/logout.png"
        self._logo_font_family = "Bahnschrift SemiCondensed"

        self.setFixedWidth(_SIDEBAR_COLLAPSED)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("""
            QWidget {{
                background: {bg0};
            }}
        """.format(bg0=_BG_SIDEBAR))

        self._width_anim = QPropertyAnimation(self, b"minimumWidth", self)
        self._width_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._width_anim.setDuration(300)
        self._width_anim.valueChanged.connect(lambda v: self.setMaximumWidth(v))
        self._width_anim.finished.connect(self._on_anim_finished)

        self._pending_expanded = False

        self._collapse_timer = QTimer(self)
        self._collapse_timer.setSingleShot(True)
        self._collapse_timer.setInterval(120)
        self._collapse_timer.timeout.connect(lambda: self._set_expanded(False))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        logo_row = QWidget(self)
        logo_row.setFixedHeight(_LOGO_SIZE_EXPANDED)
        logo_row.setStyleSheet("background: transparent;")
        logo_row.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        logo_row.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        logo_row.setStyleSheet("background: transparent;")
        lr = QHBoxLayout(logo_row)
        lr.setContentsMargins(0, 0, 0, 0)
        lr.setSpacing(0)
        lr.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self._logo_row_layout = lr

        logo_icon_cell = QWidget(logo_row)
        logo_icon_cell.setFixedWidth(_SIDEBAR_COLLAPSED)
        logo_icon_cell_l = QHBoxLayout(logo_icon_cell)
        logo_icon_cell_l.setContentsMargins(SPACE_11, 0, 0, 0)
        logo_icon_cell_l.setSpacing(0)
        self._logo_icon_cell_layout = logo_icon_cell_l
        lr.addWidget(logo_icon_cell)

        self._logo_icon = _LogoMonogram(_LOGO_SIZE_COLLAPSED_ICON, logo_icon_cell)
        logo_icon_cell_l.addWidget(self._logo_icon)

        self._logo_lbl = QLabel("mart Eye", logo_row)
        logo_color = _TEXT_PRI
        font_family = "Bahnschrift SemiCondensed"
        self._logo_font_family = font_family
        logo_font = QFont()
        logo_font.setFamily(font_family)
        safe_set_point_size(logo_font, FONT_SIZE_LARGE)
        logo_font.setBold(True)
        self._logo_lbl.setFont(logo_font)
        self._logo_lbl.setFixedHeight(_LOGO_SIZE_WORDMARK)
        self._logo_lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._logo_lbl.setStyleSheet(
            f"font-family: '{font_family}', 'Bahnschrift Condensed',"
            f" 'Bahnschrift SemiBold', 'Segoe UI Semibold', 'Segoe UI';"
            f"font-size: {FONT_SIZE_LARGE}px; font-weight: {FONT_WEIGHT_HEAVY}; color: {logo_color};"
            f"background: transparent; letter-spacing: 0.8px; padding: 0; margin-left: {RADIUS_NONE}px; margin-top: {RADIUS_NONE}px;"
        )
        self._logo_lbl.setMaximumWidth(0)
        self._logo_lbl.setMinimumWidth(0)
        self._logo_lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        apply_shadow_float(self._logo_lbl, _ACCENT_HI)
        lr.addWidget(self._logo_lbl)

        self._logo_lbl_anim = QPropertyAnimation(self._logo_lbl, b"maximumWidth", self)
        self._logo_lbl_anim.setDuration(280)
        self._logo_lbl_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        root.addWidget(logo_row)

        divider = QFrame(self)
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setFixedHeight(SPACE_XXXS)
        divider.setStyleSheet("background: {bg}; border: none;".format(bg=_BORDER_SIDE))
        self._top_divider = divider
        root.addWidget(divider)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
            f" QScrollBar:vertical {{ background: transparent; width: {SPACE_XS}px; margin: {SPACE_XS}px 0; }}"
            f" QScrollBar::handle:vertical {{ background: {_ACCENT_HI_BG_20};"
            f" border-radius: {RADIUS_XS}px; min-height: {SPACE_20}px; }}"
            " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
        )

        self._scroll = scroll

        nav_w = QWidget()
        nav_w.setStyleSheet("background: transparent;")
        self._nav_layout = QVBoxLayout(nav_w)
        self._nav_layout.setContentsMargins(SPACE_6, SPACE_SM, SPACE_6, SPACE_SM)
        self._nav_layout.setSpacing(SPACE_XXS)

        current_section = None
        for label, key, icon in NAV_ITEMS:
            if key is None:
                sec = QLabel(label)
                sec.setStyleSheet(
                    f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_TINY}px; font-weight: {FONT_WEIGHT_HEAVY};"
                    f" letter-spacing: 1.{SPACE_XS}px; padding: {SPACE_10}px {SPACE_14}px {SPACE_3}px;"
                    f" background: transparent;"
                )
                sec.setMaximumWidth(0)
                self._nav_layout.addWidget(sec)
                self._section_labels.append(sec)
                current_section = []
                self._section_btn_keys.append(current_section)

                sec_anim = QPropertyAnimation(sec, b"maximumWidth", self)
                sec_anim.setDuration(260)
                sec_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                self._section_anims.append(sec_anim)
            else:
                btn = NavButton(label, icon, key, self._on_nav_clicked, self)
                self._nav_layout.addWidget(btn)
                self._nav_btns[key] = btn
                if current_section is None:
                    current_section = []
                    self._section_btn_keys.append(current_section)
                current_section.append(key)

        self._nav_layout.addStretch()
        scroll.setWidget(nav_w)
        root.addWidget(scroll, stretch=1)

        bot_divider = QFrame(self)
        bot_divider.setFrameShape(QFrame.Shape.HLine)
        bot_divider.setFixedHeight(SPACE_XXXS)
        bot_divider.setStyleSheet("background: {bg}; border: none;".format(bg=_BORDER_SIDE))
        self._bottom_divider = bot_divider
        root.addWidget(bot_divider)

        acc_w = QWidget()
        acc_w.setStyleSheet("background: transparent;")
        acc_l = QVBoxLayout(acc_w)
        acc_l.setContentsMargins(SPACE_10, SPACE_6, SPACE_10, SPACE_6)
        acc_l.setSpacing(SPACE_6)

        acc_row = QHBoxLayout()
        acc_row.setContentsMargins(SPACE_6, SPACE_6, SPACE_6, SPACE_6)
        acc_row.setSpacing(SPACE_10)
        self._avatar = QLabel()
        self._avatar.setFixedSize(SIZE_ICON_LG, SIZE_ICON_LG)
        self._avatar.setScaledContents(True)
        self._avatar.setStyleSheet(
            f"border-radius: {RADIUS_14}px; background: {_ACCENT_HI};"
            f"color: white; font-weight: {FONT_WEIGHT_HEAVY}; font-size: {FONT_SIZE_LABEL}px; "
            "qproperty-alignment: 'AlignCenter';"
        )
        acc_row.addWidget(self._avatar)

        self._acc_email = QLabel("")
        self._acc_email.setStyleSheet(text_style(_TEXT_PRI, size=FONT_SIZE_CAPTION, extra="background: transparent;"))
        acc_row.addWidget(self._acc_email, stretch=1)

        self._logout_btn = QToolButton()
        self._logout_btn.setIconSize(QSize(SIZE_ICON_XS, SIZE_ICON_XS))
        self._logout_btn.setStyleSheet(
            f"QToolButton {{ background: transparent; border: none; padding: {SPACE_XS}px; }}"
            f"QToolButton:hover {{ background: {_ACCENT_HI_BG_10}; border-radius: {RADIUS_6}px; }}"
            f"QToolButton:pressed {{ background: {_ACCENT_HI_BG_20}; border-radius: {RADIUS_6}px; }}"
            f"QToolButton:disabled {{ background: {_BG_BASE_92}; }}"
        )
        self._refresh_logout_icon()
        self._logout_btn.clicked.connect(self._on_logout)
        acc_row.addWidget(self._logout_btn)

        acc_l.addLayout(acc_row)

        self._ver_lbl = QLabel(f"v{_APP_INFO.get('version', '0.1.0-alpha')}")
        self._ver_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._ver_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_9) + " background: transparent;")
        acc_l.addWidget(self._ver_lbl)

        root.addWidget(acc_w)

        self._ver_lbl_anim = QPropertyAnimation(self._ver_lbl, b"maximumWidth", self)
        self._ver_lbl_anim.setDuration(260)
        self._ver_lbl_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

    def _on_nav_clicked(self, key: str):
        try:
            print(f"NAV_CLICK: {key}")
        except (RuntimeError, OSError):
            pass
        self._on_navigate(key)

    def set_active(self, key: str):
        for k, btn in self._nav_btns.items():
            btn.set_active(k == key)

    def _refresh_logout_icon(self) -> None:
        pix = themed_icon_pixmap(self._logout_icon_path, SIZE_ICON_XS, SIZE_ICON_XS)
        if pix.isNull():
            self._logout_btn.setIcon(QIcon(self._logout_icon_path))
            return
        self._logout_btn.setIcon(QIcon(pix))

    def refresh_theme(self) -> None:
        _reload_color_tokens()

        self.setStyleSheet(
            """
            QWidget {{
                background: {bg0};
            }}
        """.format(bg0=_BG_SIDEBAR)
        )

        if self._top_divider is not None:
            self._top_divider.setStyleSheet("background: {bg}; border: none;".format(bg=_BORDER_SIDE))
        if self._bottom_divider is not None:
            self._bottom_divider.setStyleSheet("background: {bg}; border: none;".format(bg=_BORDER_SIDE))
        if self._scroll is not None:
            self._scroll.setStyleSheet(
                "QScrollArea { border: none; background: transparent; }"
                f" QScrollBar:vertical {{ background: transparent; width: {SPACE_XS}px; margin: {SPACE_XS}px 0; }}"
                f" QScrollBar::handle:vertical {{ background: {_ACCENT_HI_BG_20};"
                f" border-radius: {RADIUS_XS}px; min-height: {SPACE_20}px; }}"
                " QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            )

        self._logo_lbl.setStyleSheet(
            f"font-family: '{self._logo_font_family}', 'Bahnschrift Condensed',"
            f" 'Bahnschrift SemiBold', 'Segoe UI Semibold', 'Segoe UI';"
            f"font-size: {FONT_SIZE_LARGE}px; font-weight: {FONT_WEIGHT_HEAVY}; color: {_TEXT_PRI};"
            f"background: transparent; letter-spacing: 0.8px; padding: 0; margin-left: {RADIUS_NONE}px; margin-top: {RADIUS_NONE}px;"
        )

        self._acc_email.setStyleSheet(text_style(_TEXT_PRI, size=FONT_SIZE_CAPTION, extra="background: transparent;"))
        self._ver_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_9) + " background: transparent;")

        for sec in self._section_labels:
            sec.setStyleSheet(
                f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_TINY}px; font-weight: {FONT_WEIGHT_HEAVY};"
                f" letter-spacing: 1.{SPACE_XS}px; padding: {SPACE_10}px {SPACE_14}px {SPACE_3}px;"
                f" background: transparent;"
            )

        for btn in self._nav_btns.values():
            btn.refresh_icon_tint()
            btn._apply_style(False)

        self._refresh_logout_icon()
        if self._account is not None:
            self.set_account(self._account)

    def set_access(self, allowed_keys: set[str], is_admin: bool):
        for key, btn in self._nav_btns.items():
            locked = not is_admin and key not in allowed_keys
            btn.set_locked(locked)
            btn.setVisible(is_admin or key in allowed_keys)
        for idx, sec_lbl in enumerate(self._section_labels):
            keys_in_sec = self._section_btn_keys[idx] if idx < len(self._section_btn_keys) else []
            visible = is_admin or any(self._nav_btns[k].isVisible() for k in keys_in_sec if k in self._nav_btns)
            sec_lbl.setVisible(visible)
            self._section_anims[idx].setTargetObject(sec_lbl)

    def set_account(self, account: dict | None):
        self._account = account
        if not account or not account.get("email"):
            self._acc_email.setText("")
            self._avatar.setText("")
            self._logout_btn.hide()
            return
        email = account.get("email", "")
        self._acc_email.setText(email)
        avatar_path = account.get("avatar_path") if isinstance(account, dict) else ""

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
            p = QPainter(rounded)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            path_obj = QPainterPath()
            path_obj.addEllipse(0, 0, size, size)
            p.setClipPath(path_obj)
            p.drawPixmap(0, 0, scaled)
            p.end()
            return rounded

        avatar_pm = None
        if avatar_path and Path(avatar_path).exists():
            avatar_pm = _rounded_pix(avatar_path, 28)

        if avatar_pm is not None:
            self._avatar.setText("")
            self._avatar.setPixmap(avatar_pm)
            self._avatar.setStyleSheet(
                f"border-radius: {RADIUS_14}px; background: {_BG_NAV_DARK}; border: {SPACE_XXXS}px solid {_BG_NAV_ALT};"
            )
        else:
            default_icon = Path("frontend/assets/icons/account.png")
            if default_icon.exists():
                pm = themed_icon_pixmap(str(default_icon), 24, 24)
                if not pm.isNull():
                    self._avatar.setText("")
                    self._avatar.setPixmap(pm)
                    self._avatar.setStyleSheet(
                        f"border-radius: {RADIUS_14}px; background: {_BG_NAV_DARK}; "
                        f"border: {SPACE_XXXS}px solid {_BG_NAV_ALT}; padding: {SPACE_XXS}px;"
                    )
                    self._logout_btn.show()
                    return
            initials = (email[:2] if email else "").upper()
            self._avatar.setText(initials)
            self._avatar.setStyleSheet(
                f"border-radius: {RADIUS_14}px; background: {_ACCENT_HI};"
                f"color: white; font-weight: {FONT_WEIGHT_HEAVY}; font-size: {FONT_SIZE_LABEL}px; "
                "qproperty-alignment: 'AlignCenter';"
            )
        self._logout_btn.show()

    def enterEvent(self, event):
        self._collapse_timer.stop()
        self._set_expanded(True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._collapse_timer.start()
        super().leaveEvent(event)

    def _set_expanded(self, expanded: bool):
        if self._expanded == expanded:
            return
        self._expanded = expanded
        self._pending_expanded = expanded
        target = _SIDEBAR_EXPANDED if expanded else _SIDEBAR_COLLAPSED

        if expanded:
            self._logo_icon_cell_layout.setContentsMargins(SPACE_11, 0, 0, 0)
            self._logo_icon_cell_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._logo_row_layout.setContentsMargins(0, 0, 0, 0)
            self._logo_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self._logo_icon.setFixedSize(_LOGO_SIZE_EXPANDED_ICON, _LOGO_SIZE_EXPANDED_ICON)
        else:
            self._logo_icon.setFixedSize(_LOGO_SIZE_COLLAPSED_ICON, _LOGO_SIZE_COLLAPSED_ICON)
            self._logo_icon_cell_layout.setContentsMargins(0, 0, 0, 0)
            self._logo_icon_cell_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._logo_row_layout.setContentsMargins(0, 0, 0, 0)
            self._logo_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self._width_anim.stop()
        self._width_anim.setStartValue(self.minimumWidth())
        self._width_anim.setEndValue(target)
        self._width_anim.start()

        self._logo_lbl_anim.stop()
        self._logo_lbl_anim.setStartValue(self._logo_lbl.maximumWidth())
        self._logo_lbl_anim.setEndValue(300 if expanded else 0)
        self._logo_lbl_anim.start()

        self._ver_lbl_anim.stop()
        self._ver_lbl_anim.setStartValue(self._ver_lbl.maximumWidth())
        self._ver_lbl_anim.setEndValue(300 if expanded else 0)
        self._ver_lbl_anim.start()

        for i, anim in enumerate(self._section_anims):
            lbl = self._section_labels[i]
            anim.stop()
            anim.setStartValue(lbl.maximumWidth())
            anim.setEndValue(300 if expanded else 0)
            anim.start()

        for btn in self._nav_btns.values():
            btn.expand(expanded)

    def _on_anim_finished(self):
        target = _SIDEBAR_EXPANDED if self._expanded else _SIDEBAR_COLLAPSED
        self.setMinimumWidth(target)
        self.setMaximumWidth(target)
        if self._pending_expanded != self._expanded:
            self._set_expanded(self._pending_expanded)
