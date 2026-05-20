import contextlib
import json
import os
from datetime import datetime, timedelta
from PySide6.QtGui import QTextCharFormat, QColor

from PySide6.QtCore import QDate, Qt, QTimer, QSettings, QSignalBlocker
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
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
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.widgets.animated_stack import AnimatedStackedWidget

from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_BG_15,
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
    SIZE_ICON_MD,
    SIZE_ROW_MD,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_28,
    SPACE_40,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
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
_ARROW_STYLE = text_style(_TEXT_MUTED, size=FONT_SIZE_LABEL, extra="background: transparent;")
_BG_BASE_STYLE = f"background: {_BG_BASE};"
_DETAIL_LABEL_STYLE = text_style(_TEXT_PRI, size=FONT_SIZE_SUBHEAD)
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
_DETAIL_TABS_STYLE = f"""
QWidget#DetailsStackWrap {{
    border: none;
    background: transparent;
}}
"""


class LogsViewerPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._settings = QSettings("SmartEye", "LogsViewer")
        self._is_active = False

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
        filter_bar1.setFixedHeight(SIZE_HEADER_H)
        filter_bar1.setStyleSheet(toolbar_style(bg=_BG_SURFACE, border=_BORDER_DIM))
        fl1 = QHBoxLayout(filter_bar1)
        fl1.setContentsMargins(SPACE_20, SPACE_SM, SPACE_20, SPACE_SM)
        fl1.setSpacing(0)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDate(QDate.currentDate().addDays(-7))
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
        fl1.addWidget(self._date_from)

        _arr = QLabel("→")
        _arr.setStyleSheet(_ARROW_STYLE)
        _arr.setFixedWidth(SIZE_ICON_MD)
        _arr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fl1.addWidget(_arr)

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(QDate.currentDate())
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
        fl1.addWidget(self._date_to)

        fl1.addSpacing(SPACE_14)
        _fs1 = QWidget()
        _fs1.setFixedSize(SPACE_XXXS, SPACE_XL)
        _fs1.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        fl1.addWidget(_fs1)
        fl1.addSpacing(SPACE_14)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All cameras", None)
        self._camera_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._camera_combo.setFixedWidth(SIZE_FIELD_W_SM)
        self._camera_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._camera_combo)
        fl1.addSpacing(SPACE_SM)

        self._type_combo = QComboBox()
        self._type_combo.addItems(["All types", "face", "object", "violation"])
        self._type_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._type_combo.setFixedWidth(SIZE_FIELD_W_SM)
        self._type_combo.setStyleSheet(_FORM_COMBO)
        fl1.addWidget(self._type_combo)

        fl1.addSpacing(SPACE_14)
        _fs2 = QWidget()
        _fs2.setFixedSize(SPACE_XXXS, SPACE_XL)
        _fs2.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        fl1.addWidget(_fs2)
        fl1.addSpacing(SPACE_14)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search identity, class, or gender...")
        self._search_edit.setFixedHeight(SIZE_CONTROL_MD)
        self._search_edit.setStyleSheet(_FORM_INPUTS)
        self._search_edit.returnPressed.connect(self._refresh)
        fl1.addWidget(self._search_edit, stretch=1)

        fl1.addSpacing(SPACE_14)
        _fs3 = QWidget()
        _fs3.setFixedSize(SPACE_XXXS, SPACE_XL)
        _fs3.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        fl1.addWidget(_fs3)
        fl1.addSpacing(SPACE_10)

        apply_btn = QPushButton("Apply")
        apply_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        apply_btn.setStyleSheet(_PRIMARY_BTN)
        apply_btn.clicked.connect(self._refresh)
        fl1.addWidget(apply_btn)

        fl1.addSpacing(SPACE_6)
        cleanup_btn = QPushButton("Cleanup")
        cleanup_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        cleanup_btn.setStyleSheet(_SECONDARY_BTN)
        cleanup_btn.clicked.connect(self._cleanup_logs)
        fl1.addWidget(cleanup_btn)

        fl1.addSpacing(SPACE_6)
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
        fl1.addWidget(del_toolbar_btn)

        fl1.addSpacing(SPACE_14)
        _fs4 = QWidget()
        _fs4.setFixedSize(SPACE_XXXS, SPACE_XL)
        _fs4.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        fl1.addWidget(_fs4)
        fl1.addSpacing(SPACE_MD)

        auto_lbl = QLabel("Auto-Refresh")
        auto_lbl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD}; letter-spacing: 0.{SPACE_XS}px;"
        )
        fl1.addWidget(auto_lbl)
        fl1.addSpacing(SPACE_SM)

        self._auto_refresh = ToggleSwitch()
        self._auto_refresh.setToolTip("Auto-refresh every 3 seconds")
        self._auto_refresh.toggled.connect(self._toggle_auto_refresh)
        fl1.addWidget(self._auto_refresh)
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
        table_vbox.addWidget(tbl_hdr_w)
        tbl_sep = QFrame()
        tbl_sep.setFixedHeight(SPACE_XXXS)
        tbl_sep.setStyleSheet(_TABLE_HEADER_SEP_STYLE)
        table_vbox.addWidget(tbl_sep)

        self._table = QTableWidget()
        self._table.viewport().setAutoFillBackground(False)
        self._table.viewport().setStyleSheet("background: transparent;")
        self._table.setColumnCount(7)
        self._table.setHorizontalHeaderLabels(["Time", "Camera", "Identity", "Gender", "Type", "Violation", "Snapshot"])
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(5, 100)
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(6, 240)
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

        saved_auto = bool(self._settings.value("auto_refresh/enabled", False, type=bool))
        with QSignalBlocker(self._auto_refresh):
            self._auto_refresh.setChecked(saved_auto)
        saved_tab = int(self._settings.value("details/current_tab", 0, type=int) or 0)
        self._set_details_tab(0 if saved_tab not in (0, 1) else saved_tab)

    def on_activated(self):
        self._is_active = True
        self._refresh_cameras()
        if self._auto_refresh.isChecked():
            self._auto_timer.start(3000)
        self._refresh()

    def on_deactivated(self):
        self._is_active = False
        self._auto_timer.stop()

    def _refresh_cameras(self):
        self._camera_combo.clear()
        self._camera_combo.addItem("All cameras", None)
        for cam in db.get_cameras():
            self._camera_combo.addItem(cam["name"], cam["id"])

    def _toggle_auto_refresh(self, checked):
        self._settings.setValue("auto_refresh/enabled", bool(checked))
        if checked and self._is_active:
            self._auto_timer.start(3000)
        else:
            self._auto_timer.stop()

    def _set_details_tab(self, index: int):
        idx = 0 if index not in (0, 1) else index
        self._details_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._details_tab_buttons):
            with QSignalBlocker(btn):
                btn.setChecked(i == idx)
                btn.setStyleSheet(_TAB_BTN_ACTIVE if i == idx else _TAB_BTN)
        self._settings.setValue("details/current_tab", idx)

    def _refresh(self):
        date_range = normalize_date_range(qdate_to_date(self._date_from.date()), qdate_to_date(self._date_to.date()))
        if date_range.swapped:
            self._date_from.setDate(QDate(date_range.start.year, date_range.start.month, date_range.start.day))
            self._date_to.setDate(QDate(date_range.end.year, date_range.end.month, date_range.end.day))
        date_from = date_range.start.strftime("%Y-%m-%d 00:00:00")
        date_to = date_range.end.strftime("%Y-%m-%d 23:59:59")
        camera_id = self._camera_combo.currentData()
        log_type = self._type_combo.currentText()
        search = self._search_edit.text().strip()

        logs = db.get_detection_logs(
            camera_id=camera_id,
            date_from=date_from,
            date_to=date_to,
            identity=search if search else None,
            alarm_level=1 if log_type == "violation" else None,
            limit=500,
        )
        self._logs_data = logs
        self._table.setRowCount(len(logs))

        has_rows = len(logs) > 0
        self._table.setVisible(has_rows)
        self._empty_label.setVisible(not has_rows)

        for i, log in enumerate(logs):
            ts = log.get("timestamp", "")
            if "T" in ts:
                ts = ts.replace("T", "  ").split(".")[0]
            self._table.setItem(i, 0, self._cell(ts))

            cam = db.get_camera(log.get("camera_id"))
            self._table.setItem(i, 1, self._cell(cam["name"] if cam else str(log.get("camera_id", ""))))
            self._table.setItem(i, 2, self._cell(log.get("identity", "-")))
            detections = {}
            with contextlib.suppress(Exception):
                detections = json.loads(log.get("detections", "{}"))
            gender = str((detections or {}).get("gender") or "unknown").title()
            self._table.setItem(i, 3, self._cell(gender))
            self._table.setItem(i, 4, self._cell("detection"))

            is_violation = (log.get("alarm_level", 0) or 0) > 0
            viol_item = QTableWidgetItem("● YES" if is_violation else "NO")
            viol_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            viol_item.setForeground(QColor(_DANGER if is_violation else _TEXT_MUTED))
            self._table.setItem(i, 5, viol_item)

            snap = log.get("snapshot_path", "") or ""
            snap_display = os.path.basename(snap) if snap else "-"
            snap_item = self._cell(snap_display)
            if snap:
                snap_item.setToolTip(snap)
            self._table.setItem(i, 6, snap_item)

        self._count_label.setText(f"{len(logs)} log{'s' if len(logs) != 1 else ''}")

    @staticmethod
    def _cell(text: str) -> QTableWidgetItem:
        item = QTableWidgetItem(str(text))
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        return item

    def _on_row_selected(self, row, col, _prev_row, _prev_col):
        if row < 0 or row >= len(self._logs_data):
            self._detail_table.setRowCount(0)
            self._detail_text.clear()
            return
        log = self._logs_data[row]
        details = dict(log)
        detections = details.get("detections", "{}")
        if isinstance(detections, str):
            with contextlib.suppress(Exception):
                details["detections"] = json.loads(detections)
        self._populate_detail_table(details)
        self._detail_text.setPlainText(json.dumps(details, indent=2, default=str))

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

        cam_name = "-"
        with contextlib.suppress(Exception):
            cam = db.get_camera(details.get("camera_id"))
            if cam and cam.get("name"):
                cam_name = str(cam.get("name"))

        _field("Log ID", details.get("id"))
        _field("Time", details.get("timestamp"))
        _field("Camera", cam_name)
        _field("Identity", details.get("identity"))
        _field("Violation", "Yes" if (details.get("alarm_level", 0) or 0) > 0 else "No")
        _field("Snapshot", os.path.basename(str(details.get("snapshot_path") or "")) or "-")

        if detections:
            for key, value in detections.items():
                clean = str(key).replace("_", " ").strip().title()
                _field(f"Detection {clean}", value)

        for key, value in details.items():
            if key in {"id", "timestamp", "camera_id", "identity", "alarm_level", "snapshot_path", "detections"}:
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

    def _delete_selected(self):
        rows = {item.row() for item in self._table.selectedIndexes()}
        if not rows:
            return
        for row in sorted(rows, reverse=True):
            if row < len(self._logs_data):
                log_id = self._logs_data[row].get("id")
                if log_id:
                    db.delete_detection_log(log_id)
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

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE_10)
        btn_row.addStretch()

        delete_btn = ConfirmDeleteButton("Delete", "Sure?")
        delete_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)

        def do_delete():
            cutoff = (datetime.now() - timedelta(days=days_spin.value())).isoformat()
            count = db.cleanup_old_logs(cutoff)
            QMessageBox.information(dlg, "Cleanup", f"Deleted {count} old log(s).")
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
