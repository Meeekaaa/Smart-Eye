from PySide6.QtGui import QFont
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from frontend.app_theme import safe_set_point_size
from frontend.styles._colors import _ACCENT, _BG_OVERLAY, _TEXT_PRI, _TEXT_MUTED, _TEXT_SEC
from frontend.styles._card_styles import _CARD_BASE
from frontend.styles.page_styles import muted_label_style, text_style, transparent_surface_style
from frontend.ui_tokens import (
    FONT_SIZE_LARGE,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_SEMIBOLD,
    FONT_WEIGHT_BOLD,
    RADIUS_MD,
    RADIUS_SM,
    SPACE_14,
    SPACE_6,
    SPACE_MD,
    SIZE_MIN_W_SM,
    SIZE_PANEL_H_SM,
)


class StatCardWidget(QFrame):
    def __init__(self, title="", value="0", subtitle="", color=_ACCENT, parent=None):
        super().__init__(parent)
        self.setObjectName("StatCard")
        self.setFixedHeight(SIZE_PANEL_H_SM)
        self.setMinimumWidth(SIZE_MIN_W_SM)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._accent = str(color or _ACCENT)
        self.setStyleSheet(
            """
            {}
            QFrame#StatCard {{ border-radius: {}px; }}
            QFrame#StatCard:hover {{ border-color: {}; background: {}; }}
            QLabel#StatCardTitle {{ color: {}; }}
            QLabel#StatCardValue {{ color: {}; font-weight: {}; }}
            QLabel#StatCardSub {{ color: {}; }}
            QLabel#StatCardDot {{ background: {}; border-radius: {}px; }}
            """.format(
                _CARD_BASE,
                RADIUS_MD,
                _TEXT_SEC,
                _BG_OVERLAY,
                _TEXT_MUTED,
                _TEXT_PRI,
                FONT_WEIGHT_BOLD,
                _TEXT_MUTED,
                self._accent,
                RADIUS_SM,
            )
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_14, SPACE_MD, SPACE_14, SPACE_MD)
        root.setSpacing(SPACE_6)

        head = QWidget(self)
        head.setStyleSheet("background: transparent; border: none;")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(0, 0, 0, 0)
        head_layout.setSpacing(SPACE_6)

        dot = QLabel()
        dot.setObjectName("StatCardDot")
        dot.setFixedSize(SPACE_6, SPACE_6)
        head_layout.addWidget(dot)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("StatCardTitle")
        title_font = QFont()
        safe_set_point_size(title_font, FONT_SIZE_MICRO)
        title_font.setBold(False)
        title_lbl.setFont(title_font)
        title_lbl.setStyleSheet(
            text_style(
                _TEXT_MUTED,
                size=FONT_SIZE_MICRO,
                weight=FONT_WEIGHT_SEMIBOLD,
                extra="letter-spacing: 0.5px; {} border: none;".format(transparent_surface_style()),
            )
        )
        head_layout.addWidget(title_lbl)
        head_layout.addStretch(1)
        root.addWidget(head)

        self._value_label = QLabel(str(value))
        self._value_label.setObjectName("StatCardValue")
        val_font = QFont()
        safe_set_point_size(val_font, FONT_SIZE_LARGE)
        val_font.setBold(True)
        self._value_label.setFont(val_font)
        self._value_label.setStyleSheet(text_style(_TEXT_PRI, extra="{} border: none;".format(transparent_surface_style())))
        root.addWidget(self._value_label)

        self._sub_label = QLabel(subtitle)
        self._sub_label.setObjectName("StatCardSub")
        self._sub_label.setStyleSheet(
            "{} {} border: none;".format(
                muted_label_style(color=_TEXT_MUTED, size=FONT_SIZE_MICRO),
                transparent_surface_style(),
            )
        )
        root.addWidget(self._sub_label)

    def set_value(self, value):
        self._value_label.setText(str(value))

    def set_subtitle(self, text):
        self._sub_label.setText(text)
