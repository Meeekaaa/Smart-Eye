import contextlib
import json
import os
import subprocess
import sys
from PySide6.QtGui import QTextCharFormat, QColor

from PySide6.QtCore import QDate, Qt, QTimer, QSettings, QSignalBlocker
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.dialogs import apply_popup_theme
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton
from frontend.app_theme import page_base_styles, safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.services.log_service import LogService
from frontend.widgets.animated_stack import AnimatedStackedWidget

from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_BG_15,
    _ACCENT_HI,
    _ACCENT_HI_BG_06,
    _ACCENT_HI_BG_28,
    _ACCENT_HI_BG_55,
    _BG_BASE,
    _BG_RAISED,
    _BG_SURFACE,
    _BORDER,
    _BORDER_DIM,
    _DANGER,
    _DANGER_GRAD_END,
    _DANGER_GRAD_PRESSED_END,
    _DANGER_GRAD_PRESSED_START,
    _DANGER_GRAD_START,
    _DANGER_GRAD_DEEP_END,
    _TEXT_MUTED,
    _TEXT_ON_ACCENT,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_SOFT,
)
from frontend.styles._input_styles import _FORM_INPUTS, _FORM_COMBO
from frontend.styles._btn_styles import _DANGER_BTN, _PRIMARY_BTN, _SECONDARY_BTN, _TAB_BTN, _TAB_BTN_ACTIVE
from frontend.styles._calendar_styles import date_popup_styles
from frontend.styles.page_styles import (
    card_shell_style,
    divider_style,
    header_bar_style,
    section_kicker_style,
    text_style,
    toolbar_style,
)
from frontend.date_utils import normalize_date_range, qdate_to_date
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_LARGE,
    FONT_SIZE_SUBHEAD,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_LG,
    RADIUS_SM,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_LG,
    SIZE_CONTROL_MD,
    SIZE_DIALOG_W,
    SIZE_FIELD_W,
    SIZE_FIELD_W_SM,
    SIZE_HEADER_H,
    SIZE_ICON_LG,
    SIZE_ROW_MD,
    SPACE_10,
    SPACE_20,
    SPACE_28,
    SPACE_40,
    SPACE_5,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XXS,
    SPACE_XXXS,
)

_STYLESHEET = (
    page_base_styles(FONT_SIZE_BODY)
    + f"""
QCheckBox {{ color: {_TEXT_PRI}; spacing: {SPACE_SM}px; }}
QCheckBox::indicator {{
    width: {SPACE_LG}px; height: {SPACE_LG}px; border: {SPACE_XXXS}px solid {_BORDER};
    border-radius: {RADIUS_SM}px; background-color: {_BG_RAISED};
    image: none;
}}
QCheckBox::indicator:checked {{
    background-color: {_ACCENT}; border-color: {_ACCENT};
    image: url(frontend/assets/icons/checkmark.png);
}}
QScrollBar:vertical {{ border: none; background: transparent; width: {SPACE_SM}px; margin: {SPACE_XXS}px {SPACE_XXXS}px; }}
QScrollBar::handle:vertical {{
    background: {_ACCENT_HI_BG_28}; min-height: {SPACE_28}px; border-radius: {RADIUS_SM}px;
}}
QScrollBar::handle:vertical:hover {{ background: {_ACCENT_HI_BG_55}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QDialog {{ background-color: {_BG_SURFACE}; }}
{date_popup_styles()}
"""
)
_TITLE_STYLE = text_style(_TEXT_PRI)
_BG_BASE_STYLE = f"background: {_BG_BASE};"
_DETAIL_LABEL_STYLE = text_style(_TEXT_PRI, size=FONT_SIZE_SUBHEAD)
_FILTER_LABEL_STYLE = text_style(
    _TEXT_MUTED,
    size=FONT_SIZE_CAPTION,
    weight=FONT_WEIGHT_BOLD,
    extra="background: transparent;",
)
_TABLE_HEADER_SEP_STYLE = divider_style(_BORDER_DIM)
_TABLE_COMPACT_STYLE = f"""
QTableWidget {{
    background: {_BG_SURFACE};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    outline: none;
    gridline-color: {_BORDER_DIM};
    alternate-background-color: {_BG_RAISED};
}}
QTableWidget::item {{
    padding: {SPACE_SM}px {SPACE_SM}px;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
    color: {_TEXT_PRI};
}}
QTableWidget::item:selected {{
    background-color: {_ACCENT_BG_15};
    color: {_TEXT_PRI};
    border-left: none;
    border-top: none;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
}}
QTableWidget::item:focus {{
    outline: none;
    border-left: none;
    border-top: none;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
}}
QHeaderView::section {{
    background-color: {_BG_RAISED};
    color: {_TEXT_SEC};
    padding: {SPACE_10}px {SPACE_LG}px;
    border: none;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
    font-weight: {FONT_WEIGHT_SEMIBOLD}; font-size: {FONT_SIZE_CAPTION}px; letter-spacing: 0.{SPACE_5}px;
}}
"""
_DETAIL_TEXT_STYLE = f"""
QPlainTextEdit {{
    background: {_BG_BASE};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-radius: 0px;
    color: {_TEXT_PRI};
    padding: {SPACE_MD}px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: {FONT_SIZE_LABEL}px;
}}
QPlainTextEdit:focus {{
    border-color: {_ACCENT};
}}
"""
_DETAIL_TABLE_STYLE = f"""
QTableWidget {{
    background: {_BG_SURFACE};
    border: {SPACE_XXXS}px solid {_BORDER_DIM};
    outline: none;
    gridline-color: {_BORDER_DIM};
    alternate-background-color: {_BG_RAISED};
}}
QTableWidget::item {{
    padding: {SPACE_SM}px {SPACE_MD}px;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
    color: {_TEXT_PRI};
}}
QTableWidget::item:selected {{
    background-color: {_ACCENT_BG_15};
    color: {_TEXT_PRI};
    border-left: none;
    border-top: none;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
}}
QTableWidget::item:focus {{
    outline: none;
    border-left: none;
    border-top: none;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
}}
QHeaderView::section {{
    background-color: {_BG_RAISED};
    color: {_TEXT_SEC};
    padding: {SPACE_10}px {SPACE_MD}px;
    border: none;
    border-right: {SPACE_XXXS}px solid {_BORDER_DIM};
    border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    font-size: {FONT_SIZE_CAPTION}px;
}}
"""
_DETAIL_TABS_STYLE = """
QWidget#DetailsStackWrap {
    border: none;
    background: transparent;
}
"""
_DETAIL_ACTION_BTN = f"""
QPushButton {{
    border: none;
    border-bottom: {SPACE_XXS}px solid transparent;
    border-radius: 0px;
    background: transparent;
    color: {_TEXT_SEC};
    font-size: {FONT_SIZE_BODY}px;
    font-weight: {FONT_WEIGHT_NORMAL};
    padding: 0 {SPACE_20}px;
}}
QPushButton:hover {{
    color: {_TEXT_PRI};
    background: {_ACCENT_HI_BG_06};
    border-bottom-color: transparent;
}}
QPushButton:focus {{
    color: {_TEXT_PRI};
    background: {_ACCENT_HI_BG_06};
    border-bottom-color: transparent;
}}
QPushButton:pressed {{
    color: {_ACCENT_HI};
    background: transparent;
    border-bottom-color: transparent;
    font-weight: {FONT_WEIGHT_NORMAL};
}}
QPushButton[inactive="true"] {{
    color: {_TEXT_MUTED};
    background: transparent;
    border-bottom-color: transparent;
}}
QPushButton[inactive="true"]:hover {{
    color: {_TEXT_PRI};
    background: {_ACCENT_HI_BG_06};
    border-bottom-color: transparent;
}}
QPushButton[inactive="true"]:pressed {{
    color: {_ACCENT_HI};
    background: transparent;
    border-bottom-color: transparent;
    font-weight: {FONT_WEIGHT_NORMAL};
}}
"""


class LogsViewerPage(QWidget):
    def _toolbar_field(self, label: str, widget: QWidget, width: int | None = None) -> QWidget:
        if width is not None:
            widget.setMinimumWidth(width)
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        wrap = QWidget()
        wrap.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_XXS)
        caption = QLabel(label)
        caption.setStyleSheet(_FILTER_LABEL_STYLE)
        layout.addWidget(caption)
        layout.addWidget(widget)
        return wrap

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._settings = QSettings("SmartEye", "LogsViewer")
        self._log_service = LogService()
        self._is_active = False
        self._filters_ready = False
        self._last_result = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header_w = QWidget()
        header_w.setFixedHeight(SIZE_HEADER_H)
        header_w.setStyleSheet(header_bar_style(bg=_BG_BASE, border=_BORDER_DIM))
        hl = QHBoxLayout(header_w)
        hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        hl.setSpacing(SPACE_10)
        icon_lbl = QLabel()
        icon_lbl.setFixedSize(SIZE_ICON_LG, SIZE_ICON_LG)
        _pix = themed_icon_pixmap("frontend/assets/icons/logs.png", SIZE_ICON_LG, SIZE_ICON_LG)
        if not _pix.isNull():
            icon_lbl.setPixmap(_pix)
        hl.addWidget(icon_lbl)
        title = QLabel("Detection Logs")
        title_font = QFont()
        safe_set_point_size(title_font, FONT_SIZE_LARGE)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(_TITLE_STYLE)
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(header_w)

        filter_bar1 = QWidget()
        filter_bar1.setFixedHeight(118)
        filter_bar1.setStyleSheet(toolbar_style(bg=_BG_SURFACE, border=_BORDER_DIM))
        filter_wrap = QVBoxLayout(filter_bar1)
        filter_wrap.setContentsMargins(SPACE_20, SPACE_SM, SPACE_20, SPACE_SM)
        filter_wrap.setSpacing(SPACE_10)

        filter_top = QWidget()
        fl1 = QHBoxLayout(filter_top)
        fl1.setContentsMargins(0, 0, 0, 0)
        fl1.setSpacing(SPACE_10)
        filter_wrap.addWidget(filter_top)

        filter_bottom = QWidget()
        fl2 = QHBoxLayout(filter_bottom)
        fl2.setContentsMargins(0, 0, 0, 0)
        fl2.setSpacing(SPACE_SM)
        filter_wrap.addWidget(filter_bottom)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        saved_from = QDate.fromString(str(self._settings.value("filters/date_from", "") or ""), "yyyy-MM-dd")
        self._date_from.setDate(saved_from if saved_from.isValid() else QDate.currentDate().addDays(-7))
        self._date_from.setDisplayFormat("MMM dd, yyyy")
        self._date_from.setFixedHeight(SIZE_CONTROL_MD)
        self._date_from.setMinimumWidth(SIZE_FIELD_W)
        self._date_from.setStyleSheet(_FORM_INPUTS)
        _cal_from = self._date_from.calendarWidget()
        _cal_from.setMinimumSize(400, 300)
        _cal_from.setGridVisible(False)
        _cal_from.setHorizontalHeaderFormat(_cal_from.HorizontalHeaderFormat.SingleLetterDayNames)
        _wknd_fmt = QTextCharFormat()
        _wknd_fmt.setForeground(QColor(_TEXT_SOFT))
        _cal_from.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, _wknd_fmt)
        _cal_from.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, _wknd_fmt)
        fl1.addWidget(self._toolbar_field("From", self._date_from, SIZE_FIELD_W), stretch=1)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        saved_to = QDate.fromString(str(self._settings.value("filters/date_to", "") or ""), "yyyy-MM-dd")
        self._date_to.setDate(saved_to if saved_to.isValid() else QDate.currentDate())
        self._date_to.setDisplayFormat("MMM dd, yyyy")
        self._date_to.setFixedHeight(SIZE_CONTROL_MD)
        self._date_to.setMinimumWidth(SIZE_FIELD_W)
        self._date_to.setStyleSheet(_FORM_INPUTS)
        _cal_to = self._date_to.calendarWidget()
        _cal_to.setMinimumSize(400, 300)
        _cal_to.setGridVisible(False)
        _cal_to.setHorizontalHeaderFormat(_cal_to.HorizontalHeaderFormat.SingleLetterDayNames)
        _wknd_fmt2 = QTextCharFormat()
        _wknd_fmt2.setForeground(QColor(_TEXT_SOFT))
        _cal_to.setWeekdayTextFormat(Qt.DayOfWeek.Saturday, _wknd_fmt2)
        _cal_to.setWeekdayTextFormat(Qt.DayOfWeek.Sunday, _wknd_fmt2)
        fl1.addWidget(self._toolbar_field("To", self._date_to, SIZE_FIELD_W), stretch=1)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All cameras", None)
        self._camera_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._camera_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._toolbar_field("Camera", self._camera_combo, SIZE_FIELD_W), stretch=1)

        self._type_combo = QComboBox()
        self._type_combo.addItem("All types", None)
        self._type_combo.addItem("Faces", "face")
        self._type_combo.addItem("Objects", "object")
        self._type_combo.addItem("Violations", "violation")
        self._type_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._type_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._toolbar_field("Type", self._type_combo, SIZE_FIELD_W_SM), stretch=1)

        self._rule_combo = QComboBox()
        self._rule_combo.addItem("All rules", None)
        self._rule_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._rule_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._toolbar_field("Rule", self._rule_combo, SIZE_FIELD_W), stretch=1)

        self._reviewed_combo = QComboBox()
        self._reviewed_combo.addItem("All review", None)
        self._reviewed_combo.addItem("Unreviewed", 0)
        self._reviewed_combo.addItem("Reviewed", 1)
        self._reviewed_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._reviewed_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._toolbar_field("Review", self._reviewed_combo, SIZE_FIELD_W), stretch=1)

        self._alarm_combo = QComboBox()
        self._alarm_combo.addItem("All levels", None)
        for level in range(1, 6):
            self._alarm_combo.addItem(f"Level {level}+", level)
        self._alarm_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._alarm_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._toolbar_field("Level", self._alarm_combo, SIZE_FIELD_W_SM), stretch=1)

        self._search_edit = QLineEdit()
        self._search_edit.setText(str(self._settings.value("filters/search", "") or ""))
        self._search_edit.setPlaceholderText("Search identity, rule, camera, class, or gender...")
        self._search_edit.setFixedHeight(SIZE_CONTROL_MD)
        self._search_edit.setMinimumWidth(420)
        self._search_edit.setStyleSheet(_FORM_INPUTS)
        self._search_edit.returnPressed.connect(self._refresh)
        fl2.addWidget(self._search_edit, stretch=1)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        apply_btn.setStyleSheet(_PRIMARY_BTN)
        apply_btn.clicked.connect(self._refresh)
        fl2.addWidget(apply_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        clear_btn.setStyleSheet(_SECONDARY_BTN)
        clear_btn.clicked.connect(self._clear_filters)
        fl2.addWidget(clear_btn)

        _fs3 = QWidget()
        _fs3.setFixedSize(SPACE_XXXS, SPACE_XL)
        _fs3.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        fl2.addWidget(_fs3)

        export_btn = QPushButton("Export")
        export_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        export_btn.setStyleSheet(_SECONDARY_BTN)
        export_btn.clicked.connect(self._export_logs)
        fl2.addWidget(export_btn)

        cleanup_btn = QPushButton("Cleanup")
        cleanup_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        cleanup_btn.setStyleSheet(_SECONDARY_BTN)
        cleanup_btn.clicked.connect(self._cleanup_logs)
        fl2.addWidget(cleanup_btn)

        _fs_delete = QWidget()
        _fs_delete.setFixedSize(SPACE_XXXS, SPACE_XL)
        _fs_delete.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        fl2.addWidget(_fs_delete)

        _DANGER_BTN_CONFIRM = f"""
            QPushButton {{
                border: {SPACE_XXXS}px solid {_DANGER_GRAD_START};
                border-radius: {RADIUS_LG}px;
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_DANGER_GRAD_PRESSED_START}, stop:1 {_DANGER_GRAD_PRESSED_END});
                color: {_TEXT_ON_ACCENT};
                font-weight: {FONT_WEIGHT_BOLD};
                font-size: {FONT_SIZE_BODY}px;
                padding: 0 {SPACE_20}px;
                min-height: {SIZE_CONTROL_MD}px;
            }}
            QPushButton:hover {{
                background-color: qlineargradient(spread:pad, x1:0, y1:0, x2:1, y2:0,
                    stop:0 {_DANGER_GRAD_END}, stop:1 {_DANGER_GRAD_DEEP_END});
            }}
        """
        del_toolbar_btn = ConfirmDeleteButton("Delete", "Sure?")
        del_toolbar_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        del_toolbar_btn.set_button_styles(_DANGER_BTN, _DANGER_BTN_CONFIRM)
        del_toolbar_btn.set_confirm_callback(self._delete_selected)
        fl2.addWidget(del_toolbar_btn)

        root.addWidget(filter_bar1)

        content_w = QWidget()
        content_w.setStyleSheet(_BG_BASE_STYLE)
        layout = QVBoxLayout(content_w)
        layout.setContentsMargins(SPACE_20, SPACE_MD, SPACE_20, SPACE_MD)
        layout.setSpacing(SPACE_MD)
        root.addWidget(content_w, stretch=1)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(SPACE_LG)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        table_card = QWidget()
        table_card.setStyleSheet(card_shell_style())
        table_vbox = QVBoxLayout(table_card)
        table_vbox.setContentsMargins(0, 0, 0, 0)
        table_vbox.setSpacing(0)

        tbl_hdr_w = QWidget()
        tbl_hdr_w.setFixedHeight(SIZE_CONTROL_LG)
        tbl_hdr_w.setStyleSheet("background: transparent;")
        tbl_hdr_l = QHBoxLayout(tbl_hdr_w)
        tbl_hdr_l.setContentsMargins(SPACE_LG, 0, SPACE_LG, 0)
        tbl_hdr_l.setSpacing(SPACE_10)
        tbl_title = QLabel("LOG ENTRIES")
        tbl_title.setStyleSheet(section_kicker_style())
        tbl_hdr_l.addWidget(tbl_title)
        tbl_hdr_l.addStretch()
        self._count_label = QLabel("0 logs")
        self._count_label.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL}; background: transparent;"
        )
        tbl_hdr_l.addWidget(self._count_label)

        rows_lbl = QLabel("Rows")
        rows_lbl.setStyleSheet(_FILTER_LABEL_STYLE)
        tbl_hdr_l.addWidget(rows_lbl)
        self._limit_spin = QSpinBox()
        self._limit_spin.setRange(50, 1000)
        self._limit_spin.setSingleStep(50)
        self._limit_spin.setValue(min(1000, int(self._settings.value("filters/limit", 500, type=int) or 500)))
        self._limit_spin.setFixedHeight(SIZE_CONTROL_MD)
        self._limit_spin.setFixedWidth(90)
        self._limit_spin.setStyleSheet(_FORM_INPUTS)
        self._limit_spin.setToolTip("Maximum rows to load")
        tbl_hdr_l.addWidget(self._limit_spin)

        page_lbl = QLabel("Page")
        page_lbl.setStyleSheet(_FILTER_LABEL_STYLE)
        tbl_hdr_l.addWidget(page_lbl)
        self._page_spin = QSpinBox()
        self._page_spin.setRange(1, 9999)
        self._page_spin.setValue(int(self._settings.value("filters/page", 1, type=int) or 1))
        self._page_spin.setFixedHeight(SIZE_CONTROL_MD)
        self._page_spin.setFixedWidth(76)
        self._page_spin.setStyleSheet(_FORM_INPUTS)
        self._page_spin.setToolTip("Result page")
        tbl_hdr_l.addWidget(self._page_spin)

        self._prev_page_btn = QPushButton("Previous")
        self._prev_page_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._prev_page_btn.setStyleSheet(_SECONDARY_BTN)
        self._prev_page_btn.clicked.connect(lambda: self._move_page(-1))
        tbl_hdr_l.addWidget(self._prev_page_btn)
        self._next_page_btn = QPushButton("Next")
        self._next_page_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._next_page_btn.setStyleSheet(_SECONDARY_BTN)
        self._next_page_btn.clicked.connect(lambda: self._move_page(1))
        tbl_hdr_l.addWidget(self._next_page_btn)
        table_vbox.addWidget(tbl_hdr_w)
        tbl_sep = QFrame()
        tbl_sep.setFixedHeight(SPACE_XXXS)
        tbl_sep.setStyleSheet(_TABLE_HEADER_SEP_STYLE)
        table_vbox.addWidget(tbl_sep)

        self._table = QTableWidget()
        self._table.viewport().setAutoFillBackground(False)
        self._table.viewport().setStyleSheet("background: transparent;")
        self._table.setColumnCount(8)
        self._table.setHorizontalHeaderLabels(["Time", "Camera", "Identity", "Gender", "Type", "Level", "Reviewed", "Snapshot"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(5, 90)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(6, 110)
        hdr.setSectionResizeMode(7, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(7, 220)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(SIZE_CONTROL_LG)
        self._table.setShowGrid(True)
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(False)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._table.setStyleSheet(_TABLE_COMPACT_STYLE)
        self._table.currentCellChanged.connect(self._on_row_selected)
        table_vbox.addWidget(self._table)

        self._empty_label = QLabel("No logs match your filters")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_SUBHEAD}px; background: transparent; padding: {SPACE_40}px;"
        )
        self._empty_label.setVisible(False)
        table_vbox.addWidget(self._empty_label)
        splitter.addWidget(table_card)

        detail_card = QWidget()
        detail_card.setStyleSheet(card_shell_style())
        detail_vbox = QVBoxLayout(detail_card)
        detail_vbox.setContentsMargins(0, 0, 0, 0)
        detail_vbox.setSpacing(0)

        det_hdr_w = QWidget()
        det_hdr_w.setFixedHeight(SIZE_CONTROL_LG)
        det_hdr_w.setStyleSheet("background: transparent;")
        det_hdr_l = QHBoxLayout(det_hdr_w)
        det_hdr_l.setContentsMargins(SPACE_LG, 0, SPACE_LG, 0)
        det_hdr_l.setSpacing(SPACE_SM)
        det_title = QLabel("LOG DETAILS")
        det_title.setStyleSheet(section_kicker_style())
        det_hdr_l.addWidget(det_title)
        det_hdr_l.addStretch()
        self._mark_reviewed_btn = QPushButton("Reviewed")
        self._mark_reviewed_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._mark_reviewed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mark_reviewed_btn.setStyleSheet(_DETAIL_ACTION_BTN)
        self._mark_reviewed_btn.clicked.connect(lambda: self._mark_selected_reviewed(True))
        det_hdr_l.addWidget(self._mark_reviewed_btn)

        self._mark_unreviewed_btn = QPushButton("Open")
        self._mark_unreviewed_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._mark_unreviewed_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._mark_unreviewed_btn.setStyleSheet(_DETAIL_ACTION_BTN)
        self._mark_unreviewed_btn.clicked.connect(lambda: self._mark_selected_reviewed(False))
        det_hdr_l.addWidget(self._mark_unreviewed_btn)

        self._open_snapshot_btn = QPushButton("Snapshot")
        self._open_snapshot_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._open_snapshot_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_snapshot_btn.setStyleSheet(_DETAIL_ACTION_BTN)
        self._open_snapshot_btn.clicked.connect(self._open_selected_snapshot)
        det_hdr_l.addWidget(self._open_snapshot_btn)

        self._copy_json_btn = QPushButton("Copy JSON")
        self._copy_json_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._copy_json_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._copy_json_btn.setStyleSheet(_DETAIL_ACTION_BTN)
        self._copy_json_btn.clicked.connect(self._copy_selected_json)
        det_hdr_l.addWidget(self._copy_json_btn)
        detail_vbox.addWidget(det_hdr_w)
        det_sep = QFrame()
        det_sep.setFixedHeight(SPACE_XXXS)
        det_sep.setStyleSheet(_TABLE_HEADER_SEP_STYLE)
        detail_vbox.addWidget(det_sep)

        self._details_tab_buttons: list[QPushButton] = []
        for idx, label in enumerate(("Table", "JSON")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_TAB_BTN_ACTIVE if idx == 0 else _TAB_BTN)
            btn.clicked.connect(lambda _c=False, i=idx: self._set_details_tab(i))
            btn.setFixedHeight(SIZE_CONTROL_MD)
            det_hdr_l.addWidget(btn)
            self._details_tab_buttons.append(btn)

        stack_wrap = QWidget()
        stack_wrap.setObjectName("DetailsStackWrap")
        stack_wrap.setStyleSheet(_DETAIL_TABS_STYLE)
        stack_layout = QVBoxLayout(stack_wrap)
        stack_layout.setContentsMargins(0, 0, 0, 0)
        stack_layout.setSpacing(0)

        self._details_stack = AnimatedStackedWidget()
        stack_layout.addWidget(self._details_stack)

        self._detail_table = QTableWidget()
        self._detail_table.setColumnCount(2)
        self._detail_table.setHorizontalHeaderLabels(["Field", "Value"])
        self._detail_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._detail_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._detail_table.setShowGrid(True)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._detail_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._detail_table.verticalHeader().setVisible(False)
        self._detail_table.verticalHeader().setDefaultSectionSize(SIZE_CONTROL_LG)
        _det_hdr = self._detail_table.horizontalHeader()
        _det_hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        _det_hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self._detail_table.setStyleSheet(_DETAIL_TABLE_STYLE)
        self._details_stack.addWidget(self._detail_table)

        self._detail_text = QPlainTextEdit()
        self._detail_text.setReadOnly(True)
        self._detail_text.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self._detail_text.setStyleSheet(_DETAIL_TEXT_STYLE)
        self._details_stack.addWidget(self._detail_text)
        detail_vbox.addWidget(stack_wrap)
        splitter.addWidget(detail_card)

        _saved = self._settings.value("splitter/sizes")
        if _saved and len(_saved) == 2:
            try:
                splitter.setSizes([int(_saved[0]), int(_saved[1])])
            except (ValueError, TypeError):
                splitter.setSizes([600, 200])
        else:
            splitter.setSizes([600, 200])
        splitter.splitterMoved.connect(lambda _pos, _idx: self._settings.setValue("splitter/sizes", splitter.sizes()))
        layout.addWidget(splitter)

        self._logs_data = []
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._refresh)
        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.timeout.connect(self._refresh)

        saved_tab = int(self._settings.value("details/current_tab", 0, type=int) or 0)
        self._set_details_tab(0 if saved_tab not in (0, 1) else saved_tab)
        self._set_combo_by_data(self._type_combo, self._settings.value("filters/type", None))
        self._set_combo_by_data(self._reviewed_combo, self._settings.value("filters/reviewed", None))
        self._set_combo_by_data(self._alarm_combo, self._settings.value("filters/alarm_level", None))
        self._set_detail_actions_enabled(False)
        self._connect_filter_signals()
        self._filters_ready = True

    @staticmethod
    def _combo_data_key(value):
        if value in (None, "", "None"):
            return None
        text = str(value)
        if text.isdigit():
            return int(text)
        return text

    def _set_combo_by_data(self, combo: QComboBox, value) -> None:
        key = self._combo_data_key(value)
        for idx in range(combo.count()):
            if combo.itemData(idx) == key:
                combo.setCurrentIndex(idx)
                return
        combo.setCurrentIndex(0)

    def _connect_filter_signals(self) -> None:
        for combo in (self._camera_combo, self._type_combo, self._rule_combo, self._reviewed_combo, self._alarm_combo):
            combo.currentIndexChanged.connect(self._on_filter_changed)
        self._date_from.dateChanged.connect(self._on_filter_changed)
        self._date_to.dateChanged.connect(self._on_filter_changed)
        self._limit_spin.valueChanged.connect(self._on_filter_changed)
        self._search_edit.textChanged.connect(self._on_filter_changed)
        self._page_spin.valueChanged.connect(self._refresh)

    def _on_filter_changed(self) -> None:
        if not self._filters_ready:
            return
        with QSignalBlocker(self._page_spin):
            self._page_spin.setValue(1)
        self._filter_timer.start(250)

    def on_activated(self):
        self._is_active = True
        self._refresh_cameras()
        self._refresh_rules()
        if db.get_bool("logs_auto_refresh_enabled", False):
            self._auto_timer.start(3000)
        self._refresh()

    def on_deactivated(self):
        self._is_active = False
        self._auto_timer.stop()

    def _refresh_cameras(self):
        selected = self._camera_combo.currentData()
        if selected is None:
            selected = self._combo_data_key(self._settings.value("filters/camera_id", None))
        with QSignalBlocker(self._camera_combo):
            self._camera_combo.clear()
            self._camera_combo.addItem("All cameras", None)
            for cam in db.get_cameras():
                self._camera_combo.addItem(cam["name"], cam["id"])
            self._set_combo_by_data(self._camera_combo, selected)

    def _refresh_rules(self):
        selected = self._rule_combo.currentData()
        if selected is None:
            selected = self._settings.value("filters/rule_name", None)
        with QSignalBlocker(self._rule_combo):
            self._rule_combo.clear()
            self._rule_combo.addItem("All rules", None)
            for rule in db.get_rules():
                name = str(rule.get("name") or "").strip()
                if name:
                    self._rule_combo.addItem(name, name)
            self._set_combo_by_data(self._rule_combo, selected)

    def _set_details_tab(self, index: int):
        idx = 0 if index not in (0, 1) else index
        self._details_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._details_tab_buttons):
            with QSignalBlocker(btn):
                btn.setChecked(i == idx)
                btn.setStyleSheet(_TAB_BTN_ACTIVE if i == idx else _TAB_BTN)
        self._settings.setValue("details/current_tab", idx)

    def _refresh(self):
        selected_id = self._selected_log_id()
        date_range = normalize_date_range(qdate_to_date(self._date_from.date()), qdate_to_date(self._date_to.date()))
        if date_range.swapped:
            self._date_from.setDate(QDate(date_range.start.year, date_range.start.month, date_range.start.day))
            self._date_to.setDate(QDate(date_range.end.year, date_range.end.month, date_range.end.day))
        date_from = date_range.start.strftime("%Y-%m-%d 00:00:00")
        date_to = date_range.end.strftime("%Y-%m-%d 23:59:59")
        camera_id = self._camera_combo.currentData()
        log_type = self._type_combo.currentData()
        rule_name = self._rule_combo.currentData()
        reviewed = self._reviewed_combo.currentData()
        alarm_level = self._alarm_combo.currentData()
        search = self._search_edit.text().strip()
        limit = self._limit_spin.value()
        page = self._page_spin.value()
        self._settings.setValue("filters/date_from", date_range.start.strftime("%Y-%m-%d"))
        self._settings.setValue("filters/date_to", date_range.end.strftime("%Y-%m-%d"))
        self._settings.setValue("filters/camera_id", "" if camera_id is None else camera_id)
        self._settings.setValue("filters/type", "" if log_type is None else log_type)
        self._settings.setValue("filters/rule_name", "" if rule_name is None else rule_name)
        self._settings.setValue("filters/reviewed", "" if reviewed is None else reviewed)
        self._settings.setValue("filters/alarm_level", "" if alarm_level is None else alarm_level)
        self._settings.setValue("filters/search", search)
        self._settings.setValue("filters/limit", limit)
        self._settings.setValue("filters/page", page)

        result = self._log_service.query_logs(
            camera_id=camera_id,
            date_from=date_from,
            date_to=date_to,
            log_type=log_type,
            search=search,
            rule_name=rule_name,
            alarm_level=alarm_level,
            reviewed=reviewed,
            limit=limit,
            page=page,
        )
        if result.total and page > result.total_pages:
            with QSignalBlocker(self._page_spin):
                self._page_spin.setValue(result.total_pages)
            self._refresh()
            return

        self._last_result = result
        logs = result.rows
        self._logs_data = logs
        with QSignalBlocker(self._page_spin):
            self._page_spin.setRange(1, result.total_pages)
            self._page_spin.setValue(min(page, result.total_pages))
        page = self._page_spin.value()
        self._prev_page_btn.setEnabled(page > 1)
        self._next_page_btn.setEnabled(result.has_next)

        with QSignalBlocker(self._table):
            self._table.setRowCount(len(logs))
            for i, log in enumerate(logs):
                ts = log.get("timestamp", "")
                if "T" in ts:
                    ts = ts.replace("T", "  ").split(".")[0]
                self._table.setItem(i, 0, self._cell(ts))

                cam_name = log.get("camera_name")
                if not cam_name:
                    cam_name = str(log.get("camera_id", ""))
                self._table.setItem(i, 1, self._cell(cam_name))
                self._table.setItem(i, 2, self._cell(log.get("identity") or "-"))
                detections = self._log_service.parse_detections(log)
                gender = str(log.get("gender_norm") or (detections or {}).get("gender") or "unknown").title()
                self._table.setItem(i, 3, self._cell(gender))
                self._table.setItem(i, 4, self._cell(self._display_log_type(log)))

                alarm_value = int(log.get("alarm_level") or 0)
                level_item = QTableWidgetItem(f"Level {alarm_value}" if alarm_value > 0 else "None")
                level_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                level_item.setForeground(QColor(_DANGER if alarm_value > 0 else _TEXT_MUTED))
                self._table.setItem(i, 5, level_item)

                reviewed_item = self._cell("Reviewed" if int(log.get("reviewed") or 0) else "Open")
                reviewed_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                reviewed_item.setForeground(QColor(_TEXT_SEC if int(log.get("reviewed") or 0) else _ACCENT))
                self._table.setItem(i, 6, reviewed_item)

                snap = log.get("snapshot_path", "") or ""
                snap_display = os.path.basename(snap) if snap else "-"
                snap_item = self._cell(snap_display)
                if snap:
                    snap_item.setToolTip(snap)
                self._table.setItem(i, 7, snap_item)

        has_rows = len(logs) > 0
        self._table.setVisible(has_rows)
        self._empty_label.setVisible(not has_rows)

        if result.total:
            first = (page - 1) * limit + 1
            last = first + len(logs) - 1
            self._count_label.setText(f"{first}-{last} of {result.total} logs - page {page}/{result.total_pages}")
        else:
            self._count_label.setText("0 logs")
        if selected_id is not None:
            for idx, log in enumerate(logs):
                if log.get("id") == selected_id:
                    self._table.selectRow(idx)
                    self._on_row_selected(idx, 0, -1, -1)
                    break
            else:
                if logs:
                    self._table.selectRow(0)
                    self._on_row_selected(0, 0, -1, -1)
                else:
                    self._detail_table.setRowCount(0)
                    self._detail_text.clear()
                    self._set_detail_actions_enabled(False)
        elif logs:
            self._table.selectRow(0)
            self._on_row_selected(0, 0, -1, -1)
        else:
            self._detail_table.setRowCount(0)
            self._detail_text.clear()
            self._set_detail_actions_enabled(False)

    def _selected_log_id(self):
        row = self._table.currentRow()
        if 0 <= row < len(self._logs_data):
            return self._logs_data[row].get("id")
        return None

    def _display_log_type(self, log: dict) -> str:
        if (log.get("alarm_level", 0) or 0) > 0:
            return "Violation"
        if self._log_service.matches_type(log, "object"):
            return "Object"
        if self._log_service.matches_type(log, "face"):
            return "Face"
        return "Detection"

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _on_row_selected(self, row, col, _prev_row, _prev_col):
        if row < 0 or row >= len(self._logs_data):
            self._detail_table.setRowCount(0)
            self._detail_text.clear()
            self._set_detail_actions_enabled(False)
            return
        log = self._logs_data[row]
        details = dict(log)
        detections = details.get("detections", "{}")
        if isinstance(detections, str):
            with contextlib.suppress(Exception):
                details["detections"] = json.loads(detections)
        self._populate_detail_table(details)
        self._detail_text.setPlainText(json.dumps(details, indent=2, default=str))
        self._set_detail_actions_enabled(True)

    def _populate_detail_table(self, details: dict):
        rows: list[tuple[str, str]] = []
        detections = details.get("detections") if isinstance(details.get("detections"), dict) else {}
        noisy_tokens = (
            "bbox",
            "box",
            "xyxy",
            "coordinate",
            "landmark",
            "embedding",
            "vector",
            "feature",
            "tensor",
            "raw",
            "mask",
        )

        def _as_text(value) -> str:
            if value is None or value == "":
                return "-"
            if isinstance(value, (dict, list)):
                return json.dumps(value, default=str)
            return str(value)

        def _looks_noisy(name: str) -> bool:
            lower = str(name).strip().lower()
            return any(token in lower for token in noisy_tokens)

        def _summary_for_value(name: str, value):
            if _looks_noisy(name):
                return None
            if isinstance(value, list):
                if not value:
                    return "-"
                if all(isinstance(item, dict) for item in value):
                    labels: list[str] = []
                    for item in value:
                        label = str(item.get("label") or item.get("class") or item.get("name") or "Object")
                        conf = item.get("conf")
                        if isinstance(conf, (int, float)):
                            labels.append(f"{label} ({int(float(conf) * 100)}%)")
                        else:
                            labels.append(label)
                    shown = labels[:3]
                    more = len(labels) - len(shown)
                    text = ", ".join(shown)
                    if more > 0:
                        text = f"{text} +{more} more"
                    return text
                if len(value) > 8:
                    return f"{len(value)} items"
                return ", ".join(str(v) for v in value)
            if isinstance(value, dict):
                simple_parts: list[str] = []
                for k, v in value.items():
                    if _looks_noisy(k):
                        continue
                    if isinstance(v, (str, int, float, bool)):
                        clean_k = str(k).replace("_", " ").strip().title()
                        simple_parts.append(f"{clean_k}: {v}")
                return " | ".join(simple_parts[:4]) if simple_parts else None
            return _as_text(value)

        def _field(label: str, value) -> None:
            summary = _summary_for_value(label, value)
            if summary is None:
                return
            rows.append((label, summary))

        cam_name = str(details.get("camera_name") or details.get("camera_id") or "-")

        _field("Log ID", details.get("id"))
        _field("Time", details.get("timestamp"))
        _field("Camera", cam_name)
        _field("Identity", details.get("identity"))
        _field("Alarm Level", details.get("alarm_level") or 0)
        _field("Reviewed", "Yes" if int(details.get("reviewed") or 0) else "No")
        _field("Rules", details.get("rules_triggered") or "-")
        _field("Violation", "Yes" if (details.get("alarm_level", 0) or 0) > 0 else "No")
        _field("Snapshot", os.path.basename(str(details.get("snapshot_path") or "")) or "-")

        if detections:
            for key, value in detections.items():
                clean = str(key).replace("_", " ").strip().title()
                _field(f"Detection {clean}", value)

        for key, value in details.items():
            if key in {
                "id",
                "timestamp",
                "camera_id",
                "camera_name",
                "identity",
                "alarm_level",
                "reviewed",
                "rules_triggered",
                "snapshot_path",
                "detections",
            }:
                continue
            clean = str(key).replace("_", " ").strip().title()
            _field(clean, value)

        self._detail_table.setRowCount(len(rows))
        for idx, (field, value) in enumerate(rows):
            field_item = self._cell(field)
            value_item = self._cell(value)
            field_item.setForeground(QColor(_TEXT_SEC))
            value_item.setForeground(QColor(_TEXT_PRI))
            self._detail_table.setItem(idx, 0, field_item)
            self._detail_table.setItem(idx, 1, value_item)

    def _selected_logs(self) -> list[dict]:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        return [self._logs_data[row] for row in sorted(rows) if 0 <= row < len(self._logs_data)]

    def _selected_log_ids(self) -> list[int]:
        return [int(log["id"]) for log in self._selected_logs() if log.get("id") is not None]

    def _current_log(self) -> dict | None:
        row = self._table.currentRow()
        if 0 <= row < len(self._logs_data):
            return self._logs_data[row]
        return None

    @staticmethod
    def _set_detail_action_inactive(button: QPushButton, inactive: bool) -> None:
        button.setEnabled(True)
        button.setProperty("inactive", bool(inactive))
        button.style().unpolish(button)
        button.style().polish(button)
        button.update()

    def _set_detail_actions_enabled(self, enabled: bool) -> None:
        for btn in (
            self._mark_reviewed_btn,
            self._mark_unreviewed_btn,
            self._copy_json_btn,
        ):
            self._set_detail_action_inactive(btn, not enabled)
        log = self._current_log() if enabled else None
        snapshot_path = str((log or {}).get("snapshot_path") or "")
        self._set_detail_action_inactive(self._open_snapshot_btn, not bool(snapshot_path and os.path.isfile(snapshot_path)))

    def _mark_selected_reviewed(self, reviewed: bool) -> None:
        ids = self._selected_log_ids()
        if not ids:
            return
        self._log_service.mark_reviewed(ids, reviewed=reviewed)
        self._refresh()

    def _open_selected_snapshot(self) -> None:
        log = self._current_log()
        path = str((log or {}).get("snapshot_path") or "")
        if not path or not os.path.isfile(path):
            QMessageBox.information(self, "Snapshot", "Snapshot file is missing.")
            self._set_detail_actions_enabled(log is not None)
            return
        try:
            self._open_path_with_system(path)
        except Exception as exc:
            QMessageBox.warning(self, "Snapshot", f"Could not open snapshot: {exc}")

    def _copy_selected_json(self) -> None:
        text = self._detail_text.toPlainText().strip()
        if text:
            QApplication.clipboard().setText(text)

    @staticmethod
    def _open_path_with_system(path: str) -> None:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return
        subprocess.Popen(["xdg-open", path])

    def _move_page(self, delta: int) -> None:
        new_page = max(1, self._page_spin.value() + int(delta))
        if self._last_result is not None:
            new_page = min(new_page, self._last_result.total_pages)
        if new_page != self._page_spin.value():
            self._page_spin.setValue(new_page)

    def _clear_filters(self) -> None:
        self._filters_ready = False
        blockers = [
            QSignalBlocker(self._date_from),
            QSignalBlocker(self._date_to),
            QSignalBlocker(self._camera_combo),
            QSignalBlocker(self._type_combo),
            QSignalBlocker(self._rule_combo),
            QSignalBlocker(self._reviewed_combo),
            QSignalBlocker(self._alarm_combo),
            QSignalBlocker(self._search_edit),
            QSignalBlocker(self._page_spin),
        ]
        try:
            self._date_from.setDate(QDate.currentDate().addDays(-7))
            self._date_to.setDate(QDate.currentDate())
            self._camera_combo.setCurrentIndex(0)
            self._type_combo.setCurrentIndex(0)
            self._rule_combo.setCurrentIndex(0)
            self._reviewed_combo.setCurrentIndex(0)
            self._alarm_combo.setCurrentIndex(0)
            self._search_edit.clear()
            self._page_spin.setValue(1)
        finally:
            del blockers
        self._filters_ready = True
        self._refresh()

    def _export_logs(self) -> None:
        date_range = normalize_date_range(qdate_to_date(self._date_from.date()), qdate_to_date(self._date_to.date()))
        default_name = f"smart_eye_logs_{date_range.start.strftime('%Y%m%d')}_{date_range.end.strftime('%Y%m%d')}.csv"
        filepath, _ = QFileDialog.getSaveFileName(
            self,
            "Export Logs",
            default_name,
            "CSV Files (*.csv)",
        )
        if not filepath:
            return
        if not filepath.lower().endswith(".csv"):
            filepath = f"{filepath}.csv"
        count = self._log_service.export_logs_csv(
            filepath,
            camera_id=self._camera_combo.currentData(),
            date_from=date_range.start.strftime("%Y-%m-%d 00:00:00"),
            date_to=date_range.end.strftime("%Y-%m-%d 23:59:59"),
            log_type=self._type_combo.currentData(),
            search=self._search_edit.text().strip(),
            rule_name=self._rule_combo.currentData(),
            reviewed=self._reviewed_combo.currentData(),
            alarm_level=self._alarm_combo.currentData(),
        )
        QMessageBox.information(self, "Export Logs", f"Exported {count} log(s).")

    def _delete_selected(self):
        log_ids = self._selected_log_ids()
        if not log_ids:
            return
        delete_evidence = False
        if any((log.get("snapshot_path") or "") for log in self._selected_logs()):
            choice = QMessageBox.question(
                self,
                "Delete Evidence",
                "Delete linked snapshot files too?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.No,
            )
            if choice == QMessageBox.StandardButton.Cancel:
                return
            delete_evidence = choice == QMessageBox.StandardButton.Yes
        result = self._log_service.delete_logs(log_ids, delete_evidence=delete_evidence)
        if result.get("evidence"):
            QMessageBox.information(self, "Delete Logs", f"Deleted {result['logs']} log(s) and {result['evidence']} snapshot file(s).")
        self._refresh()

    def _cleanup_logs(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Cleanup Old Logs")
        dlg.setMinimumWidth(SIZE_DIALOG_W)
        apply_popup_theme(dlg)
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(SPACE_XL, SPACE_20, SPACE_XL, SPACE_20)
        layout.setSpacing(SPACE_LG)

        desc = QLabel("Delete logs older than:")
        desc.setStyleSheet(_DETAIL_LABEL_STYLE)
        layout.addWidget(desc)

        days_spin = QSpinBox()
        days_spin.setRange(1, 365)
        days_spin.setValue(30)
        days_spin.setSuffix(" days")
        days_spin.setFixedHeight(SIZE_ROW_MD)
        days_spin.setStyleSheet(_FORM_INPUTS)
        layout.addWidget(days_spin)

        evidence_check = QCheckBox("Delete linked snapshot files")
        evidence_check.setStyleSheet(_DETAIL_LABEL_STYLE)
        layout.addWidget(evidence_check)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE_10)
        btn_row.addStretch()

        delete_btn = ConfirmDeleteButton("Delete", "Sure?")
        delete_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)

        def do_delete():
            result = self._log_service.cleanup_older_than_days(
                days_spin.value(),
                delete_evidence=evidence_check.isChecked(),
            )
            message = f"Deleted {result['logs']} old log(s)."
            if result.get("evidence"):
                message += f"\nDeleted {result['evidence']} snapshot file(s)."
            QMessageBox.information(dlg, "Cleanup", message)
            dlg.accept()
            self._refresh()

        delete_btn.set_confirm_callback(do_delete)
        btn_row.addWidget(delete_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        cancel_btn.setStyleSheet(_SECONDARY_BTN)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)
        dlg.exec()
