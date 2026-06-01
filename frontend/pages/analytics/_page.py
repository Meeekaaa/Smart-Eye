import contextlib
import logging
from datetime import datetime, timezone

from PySide6.QtCore import QDate, Qt, QThread, Signal, QSettings
from PySide6.QtGui import QFont, QTextCharFormat, QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QFileDialog,
    QHBoxLayout,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from frontend.widgets.no_wheel_combo import NoWheelComboBox

from backend.repository import db
from frontend.app_theme import page_base_styles, safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.services.analytics_service import AnalyticsService
from frontend.widgets.chart_widget import ChartWidget
from frontend.widgets.heatmap_widget import HeatmapWidget
from frontend.widgets.stat_card_widget import StatCardWidget
from frontend.widgets.base.roster_card_base import apply_roster_card_style, build_roster_card_layout
from frontend.date_utils import normalize_date_range, qdate_to_date
from frontend.widgets.animated_stack import AnimatedStackedWidget


from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_HI_BG_28,
    _ACCENT_HI_BG_55,
    _BG_BASE,
    _BG_SURFACE,
    _BORDER_DIM,
    _DANGER,
    _DANGER_BG_14,
    _DANGER_DIM,
    _PURPLE_DIM,
    _SUCCESS_DIM,
    _WARNING_ALT,
    _WARNING_BG_14,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SOFT,
)
from frontend.styles.page_styles import (
    card_shell_style,
    divider_style,
    header_bar_style,
    muted_label_style,
    section_kicker_style,
    text_style,
    toolbar_style,
    transparent_surface_style,
)
from frontend.styles._calendar_styles import date_popup_styles
from frontend.styles._input_styles import _FORM_COMBO, _FORM_INPUTS
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_LARGE,
    FONT_WEIGHT_BOLD,
    RADIUS_LG,
    RADIUS_SM,
    SPACE_10,
    SPACE_20,
    SPACE_LG,
    SPACE_MD,
    SPACE_28,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
    SPACE_XL,
    SIZE_BADGE_H,
    SIZE_BTN_W_LG,
    SIZE_CONTROL_LG,
    SIZE_CONTROL_MD,
    SIZE_FIELD_W,
    SIZE_FIELD_W_LG,
    SIZE_HEADER_H,
    SIZE_ICON_LG,
)
from frontend.styles._btn_styles import (
    _PRIMARY_BTN,
    _SECONDARY_BTN,
    _TAB_BTN as _A_TAB_BTN,
    _TAB_BTN_ACTIVE as _A_TAB_BTN_ACTIVE,
)

_STYLESHEET = (
    page_base_styles(FONT_SIZE_BODY)
    + f"""
QScrollBar:vertical {{ border: none; background: transparent; width: {SPACE_SM}px; margin: {SPACE_XXS}px {SPACE_XXXS}px; }}
QScrollBar::handle:vertical {{
    background: {_ACCENT_HI_BG_28}; min-height: {SPACE_28}px; border-radius: {RADIUS_SM}px;
}}
QScrollBar::handle:vertical:hover {{ background: {_ACCENT_HI_BG_55}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
{date_popup_styles()}
"""
)

logger = logging.getLogger(__name__)
_RETIRED_ANALYTICS_WORKERS: set[QThread] = set()
_RETIRED_PDF_WORKERS: set[QThread] = set()
_TITLE_STYLE = text_style(_TEXT_PRI, extra="border: none; padding: 0;")
_BG_BASE_STYLE = f"background: {_BG_BASE};"
_FILTER_LABEL_STYLE = text_style(
    _TEXT_MUTED,
    size=FONT_SIZE_CAPTION,
    weight=FONT_WEIGHT_BOLD,
    extra="background: transparent;",
)
_DEBUG_BANNER_STYLE = (
    f"color: {_WARNING_ALT}; background-color: {_WARNING_BG_14}; border: none; "
    f"padding: {SPACE_SM}px {SPACE_20}px; font-weight: {FONT_WEIGHT_BOLD};"
)


class _AnalyticsLoadWorker(QThread):
    finished_load = Signal(int, bool, object, str)

    def __init__(self, request_id: int, options: dict, parent=None):
        super().__init__(parent)
        self._request_id = int(request_id)
        self._options = dict(options)

    def run(self):
        try:
            model = AnalyticsService().load_view_model(**self._options)
            self.finished_load.emit(self._request_id, True, model, "")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            logger.exception("Analytics refresh failed")
            self.finished_load.emit(self._request_id, False, None, str(exc))


class _PdfExportWorker(QThread):
    finished_export = Signal(bool, str)

    def __init__(self, path: str, options: dict, parent=None):
        super().__init__(parent)
        self._path = path
        self._options = options

    def run(self):
        try:
            AnalyticsService().export_pdf(self._path, **self._options)
            self.finished_export.emit(True, self._path)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            logger.exception("PDF export failed")
            self.finished_export.emit(False, str(exc))


class AnalyticsPage(QWidget):
    @staticmethod
    def _filter_field(label: str, widget: QWidget, width: int | None = None) -> QWidget:
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
        self._load_worker = None
        self._pdf_worker = None
        self._refresh_seq = 0
        self._pending_refresh = False
        self._settings = QSettings("SmartEye", "Analytics")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header_w = QWidget()
        header_w.setFixedHeight(SIZE_HEADER_H)
        header_w.setObjectName("analytics_header")
        header_w.setStyleSheet(header_bar_style(widget_id="analytics_header", bg=_BG_BASE, border=_BORDER_DIM))
        hl = QHBoxLayout(header_w)
        hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        hl.setSpacing(SPACE_MD)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(SIZE_ICON_LG, SIZE_ICON_LG)
        _pix = themed_icon_pixmap("frontend/assets/icons/analytics.png", SIZE_ICON_LG, SIZE_ICON_LG)
        if not _pix.isNull():
            icon_lbl.setPixmap(_pix)
        hl.addWidget(icon_lbl)

        title = QLabel("Analytics")
        title_font = QFont()
        safe_set_point_size(title_font, FONT_SIZE_LARGE)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(_TITLE_STYLE)
        hl.addWidget(title)
        hl.addStretch()
        root.addWidget(header_w)

        today = QDate.currentDate()
        filter_bar = QWidget()
        filter_bar.setFixedHeight(SIZE_HEADER_H + SPACE_SM)
        filter_bar.setStyleSheet(toolbar_style(bg=_BG_SURFACE, border=_BORDER_DIM))
        fl = QHBoxLayout(filter_bar)
        fl.setContentsMargins(SPACE_20, SPACE_XS, SPACE_20, SPACE_XS)
        fl.setSpacing(SPACE_SM)

        self._alarm_combo = QComboBox()
        self._alarm_combo.addItem("All severity", None)
        self._alarm_combo.addItem(">= 1", 1)
        self._alarm_combo.addItem(">= 2", 2)
        self._alarm_combo.addItem(">= 3", 3)
        self._alarm_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._alarm_combo.setMinimumWidth(SIZE_FIELD_W_LG)
        self._alarm_combo.setStyleSheet(_FORM_COMBO)

        self._gender_combo = NoWheelComboBox()
        self._gender_combo.addItem("All genders", None)
        self._gender_combo.addItem("Male", "male")
        self._gender_combo.addItem("Female", "female")
        self._gender_combo.addItem("Unknown", "unknown")
        self._gender_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._gender_combo.setMinimumWidth(SIZE_FIELD_W_LG)
        self._gender_combo.setStyleSheet(_FORM_COMBO)

        self._time_combo = QComboBox()
        self._time_combo.addItem("Local", "Local")
        self._time_combo.addItem("UTC", "UTC")
        self._time_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._time_combo.setMinimumWidth(SIZE_FIELD_W)
        self._time_combo.setStyleSheet(_FORM_COMBO)

        self._camera_combo = QComboBox()
        self._camera_combo.addItem("All cameras", None)
        self._camera_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._camera_combo.setMinimumWidth(SIZE_FIELD_W_LG)
        self._camera_combo.setStyleSheet(_FORM_COMBO)

        self._rule_combo = QComboBox()
        self._rule_combo.addItem("All rules", None)
        self._rule_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._rule_combo.setMinimumWidth(SIZE_FIELD_W_LG)
        self._rule_combo.setStyleSheet(_FORM_COMBO)

        self._date_from = QDateEdit()
        self._date_from.setCalendarPopup(True)
        self._date_from.setDisplayFormat("yyyy-MM-dd")
        self._date_from.setDate(today.addDays(-30))
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

        self._date_to = QDateEdit()
        self._date_to.setCalendarPopup(True)
        self._date_to.setDate(today)
        self._date_to.setDisplayFormat("yyyy-MM-dd")
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

        fl.addWidget(self._filter_field("From", self._date_from, SIZE_FIELD_W), stretch=1)
        fl.addWidget(self._filter_field("To", self._date_to, SIZE_FIELD_W), stretch=1)
        fl.addWidget(self._filter_field("Camera", self._camera_combo, SIZE_FIELD_W_LG), stretch=1)
        fl.addWidget(self._filter_field("Rule", self._rule_combo, SIZE_FIELD_W_LG), stretch=1)
        fl.addWidget(self._filter_field("Severity", self._alarm_combo, SIZE_FIELD_W_LG), stretch=1)
        fl.addWidget(self._filter_field("Gender", self._gender_combo, SIZE_FIELD_W_LG), stretch=1)
        fl.addWidget(self._filter_field("Time", self._time_combo, SIZE_FIELD_W), stretch=1)
        fl.addStretch()

        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._apply_btn.setStyleSheet(_PRIMARY_BTN)
        self._apply_btn.clicked.connect(self._refresh)
        fl.addWidget(self._apply_btn)

        self._pdf_btn = QPushButton("Export PDF")
        self._pdf_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        self._pdf_btn.setStyleSheet(_SECONDARY_BTN)
        self._pdf_btn.clicked.connect(self._export_pdf)
        fl.addWidget(self._pdf_btn)
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_LABEL) + " background: transparent;")
        fl.addWidget(self._status_lbl)
        self._camera_combo.currentIndexChanged.connect(self._refresh_rules)
        self._time_combo.currentIndexChanged.connect(self._update_time_info)
        self._update_time_info()
        root.addWidget(filter_bar)

        self._debug_banner = QLabel("Synthetic debug analytics data is enabled.")
        self._debug_banner.setStyleSheet(_DEBUG_BANNER_STYLE)
        self._debug_banner.setVisible(False)
        root.addWidget(self._debug_banner)

        content_w = QWidget()
        content_w.setStyleSheet(_BG_BASE_STYLE)
        layout = QVBoxLayout(content_w)
        layout.setContentsMargins(SPACE_20, SPACE_LG, SPACE_20, SPACE_LG)
        layout.setSpacing(SPACE_LG)
        root.addWidget(content_w, stretch=1)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(SPACE_10)
        self._stat_total = StatCardWidget("Total Events", "0", "detections", _ACCENT)
        self._stat_violations = StatCardWidget("Violations", "0", "total", _DANGER_DIM)
        self._stat_compliance = StatCardWidget("Compliance", "100%", "rate", _SUCCESS_DIM)
        self._stat_faces = StatCardWidget("Identified", "0", "faces", _PURPLE_DIM)
        self._stat_gendered = StatCardWidget("Gendered Violations", "0", "gender", _ACCENT)
        stats_row.addWidget(self._stat_total)
        stats_row.addWidget(self._stat_violations)
        stats_row.addWidget(self._stat_compliance)
        stats_row.addWidget(self._stat_faces)
        stats_row.addWidget(self._stat_gendered)
        layout.addLayout(stats_row)

        tab_card = QWidget()
        tab_card.setStyleSheet(card_shell_style())
        tab_card_vbox = QVBoxLayout(tab_card)
        tab_card_vbox.setContentsMargins(0, 0, 0, 0)
        tab_card_vbox.setSpacing(0)

        tab_bar_w = QWidget()
        tab_bar_w.setFixedHeight(SIZE_CONTROL_LG)
        tab_bar_w.setStyleSheet(transparent_surface_style())
        tb = QHBoxLayout(tab_bar_w)
        tb.setContentsMargins(SPACE_SM, 0, SPACE_SM, 0)
        tb.setSpacing(0)
        self._a_tab_btns: list[QPushButton] = []
        for i, label in enumerate(["Compliance Trend", "Hourly Violations", "Camera Activity", "Heatmap", "Top Violators"]):
            btn = QPushButton(label)
            btn.setStyleSheet(_A_TAB_BTN)
            btn.clicked.connect(lambda _, idx=i: self._switch_analytics_tab(idx))
            tb.addWidget(btn)
            self._a_tab_btns.append(btn)
        tb.addStretch()
        tab_card_vbox.addWidget(tab_bar_w)

        _tab_sep = QWidget()
        _tab_sep.setFixedHeight(SPACE_XXXS)
        _tab_sep.setStyleSheet(divider_style(_BORDER_DIM))
        tab_card_vbox.addWidget(_tab_sep)

        self._a_stack = AnimatedStackedWidget()
        self._a_stack.setStyleSheet(transparent_surface_style())

        self._compliance_chart = ChartWidget("Compliance Trend")
        _cc_wrap = QWidget()
        _cc_wrap.setStyleSheet(transparent_surface_style())
        _cc_wl = QVBoxLayout(_cc_wrap)
        _cc_wl.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        _cc_wl.setSpacing(0)
        _cc_wl.addWidget(self._compliance_chart)
        self._a_stack.addWidget(_cc_wrap)

        self._violation_chart = ChartWidget("Hourly Violations")
        _vc_wrap = QWidget()
        _vc_wrap.setStyleSheet(transparent_surface_style())
        _vc_wl = QVBoxLayout(_vc_wrap)
        _vc_wl.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        _vc_wl.setSpacing(0)
        _vc_wl.addWidget(self._violation_chart)
        self._a_stack.addWidget(_vc_wrap)

        self._camera_chart = ChartWidget("Camera Activity")
        _cam_wrap = QWidget()
        _cam_wrap.setStyleSheet(transparent_surface_style())
        _cam_wl = QVBoxLayout(_cam_wrap)
        _cam_wl.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        _cam_wl.setSpacing(0)
        _cam_wl.addWidget(self._camera_chart)
        self._a_stack.addWidget(_cam_wrap)

        self._heatmap_widget = HeatmapWidget()
        heatmap_container = QWidget()
        heatmap_container.setStyleSheet(transparent_surface_style())
        heatmap_layout = QVBoxLayout(heatmap_container)
        heatmap_layout.setContentsMargins(0, 0, 0, 0)
        heatmap_layout.setSpacing(0)
        hm_hdr_w = QWidget()
        hm_hdr_w.setFixedHeight(SIZE_CONTROL_LG)
        hm_hdr_w.setStyleSheet(transparent_surface_style())
        hm_hdr_l = QHBoxLayout(hm_hdr_w)
        hm_hdr_l.setContentsMargins(SPACE_LG, 0, SPACE_LG, 0)
        hm_hdr_l.setSpacing(SPACE_10)
        hm_title_lbl = QLabel("DETECTION HEATMAP")
        hm_title_lbl.setStyleSheet(section_kicker_style())
        hm_hdr_l.addWidget(hm_title_lbl)
        hm_hdr_l.addStretch()
        _hm_sep = QWidget()
        _hm_sep.setFixedHeight(SPACE_XXXS)
        _hm_sep.setStyleSheet(divider_style(_BORDER_DIM))
        heatmap_layout.addWidget(hm_hdr_w)
        heatmap_layout.addWidget(_hm_sep)
        heatmap_layout.addWidget(self._heatmap_widget, stretch=1)
        self._a_stack.addWidget(heatmap_container)

        top_violators_widget = QWidget()
        top_violators_widget.setStyleSheet(transparent_surface_style())
        tv_layout = QVBoxLayout(top_violators_widget)
        tv_layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        tv_layout.setSpacing(SPACE_SM)
        self._top_violators_area = QScrollArea()
        self._top_violators_area.setWidgetResizable(True)
        self._top_violators_area.setStyleSheet("border: none; background: transparent;")
        self._gender_breakdown_lbl = QLabel("")
        self._gender_breakdown_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_LABEL) + " background: transparent;")
        tv_layout.addWidget(self._gender_breakdown_lbl)
        self._tv_container = QWidget()
        self._tv_container.setStyleSheet(transparent_surface_style())
        self._tv_layout = QVBoxLayout(self._tv_container)
        self._tv_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._tv_layout.setSpacing(SPACE_SM)
        self._top_violators_area.setWidget(self._tv_container)
        tv_layout.addWidget(self._top_violators_area)
        self._a_stack.addWidget(top_violators_widget)

        tab_card_vbox.addWidget(self._a_stack, stretch=1)
        layout.addWidget(tab_card, stretch=1)
        saved_tab = int(self._settings.value("tabs/current", 0, type=int) or 0)
        self._switch_analytics_tab(saved_tab if 0 <= saved_tab < len(self._a_tab_btns) else 0)

    def _switch_analytics_tab(self, idx: int) -> None:
        self._a_stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._a_tab_btns):
            btn.setStyleSheet(_A_TAB_BTN_ACTIVE if i == idx else _A_TAB_BTN)
        self._settings.setValue("tabs/current", idx)

    def on_activated(self):
        self._refresh_cameras()
        self._load_filters()
        self._refresh_rules()
        self._refresh()

    def on_unload(self) -> None:
        self._cleanup_load_worker()
        self._cleanup_pdf_worker()

    def _cleanup_load_worker(self) -> None:
        worker = self._load_worker
        self._load_worker = None
        if worker is None:
            return
        with contextlib.suppress(Exception):
            worker.finished_load.disconnect()
        with contextlib.suppress(Exception):
            worker.finished.disconnect()
        if worker.isRunning():
            worker.setParent(None)
            _RETIRED_ANALYTICS_WORKERS.add(worker)

            def _cleanup(w=worker):
                _RETIRED_ANALYTICS_WORKERS.discard(w)
                with contextlib.suppress(Exception):
                    w.deleteLater()

            worker.finished.connect(_cleanup)
        else:
            with contextlib.suppress(Exception):
                worker.deleteLater()

    def _cleanup_pdf_worker(self) -> None:
        worker = self._pdf_worker
        self._pdf_worker = None
        if worker is None:
            return
        with contextlib.suppress(Exception):
            worker.finished_export.disconnect()
        with contextlib.suppress(Exception):
            worker.finished.disconnect()
        if worker.isRunning():
            worker.setParent(None)
            _RETIRED_PDF_WORKERS.add(worker)

            def _cleanup(w=worker):
                _RETIRED_PDF_WORKERS.discard(w)
                with contextlib.suppress(Exception):
                    w.deleteLater()

            worker.finished.connect(_cleanup)
        else:
            with contextlib.suppress(Exception):
                worker.deleteLater()

    def _refresh_cameras(self):
        self._camera_combo.clear()
        self._camera_combo.addItem("All cameras", None)
        cameras = db.get_cameras()
        for cam in cameras:
            self._camera_combo.addItem(cam["name"], cam["id"])
        self._refresh_rules()

    def _refresh_rules(self):
        current = self._rule_combo.currentData()
        self._rule_combo.clear()
        self._rule_combo.addItem("All rules", None)
        cam_id = self._camera_combo.currentData()
        rules = db.get_rules(enabled_only=True, camera_id=cam_id)
        seen = set()
        for rule in rules:
            name = rule.get("name")
            if not name or name in seen:
                continue
            seen.add(name)
            self._rule_combo.addItem(name, name)
        if current:
            idx = self._rule_combo.findData(current)
            if idx >= 0:
                self._rule_combo.setCurrentIndex(idx)

    @staticmethod
    def _set_combo_data(combo: QComboBox, value) -> None:
        idx = combo.findData(value)
        combo.setCurrentIndex(idx if idx >= 0 else 0)

    def _load_filters(self) -> None:
        self._set_combo_data(self._alarm_combo, self._settings.value("filters/alarm_level", None))
        self._set_combo_data(self._gender_combo, self._settings.value("filters/gender", None))
        self._set_combo_data(self._time_combo, self._settings.value("filters/time_basis", "Local"))
        cam_value = self._settings.value("filters/camera_id", None)
        try:
            cam_value = int(cam_value) if cam_value not in (None, "", "None") else None
        except (TypeError, ValueError):
            cam_value = None
        self._set_combo_data(self._camera_combo, cam_value)
        self._refresh_rules()
        self._set_combo_data(self._rule_combo, self._settings.value("filters/rule_name", None))
        for key, widget in (("filters/date_from", self._date_from), ("filters/date_to", self._date_to)):
            saved = str(self._settings.value(key, "") or "")
            qdate = QDate.fromString(saved, "yyyy-MM-dd")
            if qdate.isValid():
                widget.setDate(qdate)

    def _save_filters(self) -> None:
        self._settings.setValue("filters/alarm_level", self._alarm_combo.currentData())
        self._settings.setValue("filters/gender", self._gender_combo.currentData())
        self._settings.setValue("filters/time_basis", self._time_combo.currentData())
        self._settings.setValue("filters/camera_id", self._camera_combo.currentData())
        self._settings.setValue("filters/rule_name", self._rule_combo.currentData())
        self._settings.setValue("filters/date_from", self._date_from.date().toString("yyyy-MM-dd"))
        self._settings.setValue("filters/date_to", self._date_to.date().toString("yyyy-MM-dd"))

    def _update_time_info(self):
        basis = self._time_combo.currentData() or self._time_combo.currentText()
        self._time_combo.setToolTip(f"Times shown in {basis}")

    def _get_time_bounds(self):
        basis = self._time_combo.currentData() or "Local"
        d_from = qdate_to_date(self._date_from.date())
        d_to = qdate_to_date(self._date_to.date())
        date_range = normalize_date_range(d_from, d_to)
        if date_range.swapped:
            self._date_from.setDate(QDate(date_range.start.year, date_range.start.month, date_range.start.day))
            self._date_to.setDate(QDate(date_range.end.year, date_range.end.month, date_range.end.day))
        d_from = date_range.start
        d_to = date_range.end
        if basis == "UTC":
            tz = timezone.utc
        else:
            tz = datetime.now().astimezone().tzinfo or timezone.utc
        start_local = datetime(d_from.year, d_from.month, d_from.day, 0, 0, 0, tzinfo=tz)
        end_local = datetime(d_to.year, d_to.month, d_to.day, 23, 59, 59, tzinfo=tz)
        if basis == "UTC":
            start_utc = start_local
            end_utc = end_local
        else:
            start_utc = start_local.astimezone(timezone.utc)
            end_utc = end_local.astimezone(timezone.utc)
        return (
            start_utc.strftime("%Y-%m-%d %H:%M:%S"),
            end_utc.strftime("%Y-%m-%d %H:%M:%S"),
            basis,
        )

    def _refresh(self):
        self._save_filters()
        date_from, date_to, _basis = self._get_time_bounds()
        options = {
            "date_from": date_from,
            "date_to": date_to,
            "time_basis": _basis,
            "camera_id": self._camera_combo.currentData(),
            "rule_name": self._rule_combo.currentData(),
            "min_alarm_level": self._alarm_combo.currentData(),
            "gender": self._gender_combo.currentData(),
        }
        if self._load_worker is not None and self._load_worker.isRunning():
            self._pending_refresh = True
            self._status_lbl.setText("Refresh queued")
            return
        self._refresh_seq += 1
        request_id = self._refresh_seq
        self._set_loading_state(True)
        worker = _AnalyticsLoadWorker(request_id, options, self)
        self._load_worker = worker
        worker.finished_load.connect(self._on_analytics_loaded)
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _set_loading_state(self, loading: bool) -> None:
        self._apply_btn.setEnabled(not loading)
        if loading:
            self._status_lbl.setText("Loading")
            self._debug_banner.setVisible(False)
            self._stat_total.set_value("...")
            self._stat_violations.set_value("...")
            self._stat_compliance.set_value("...")
            self._stat_faces.set_value("...")
            self._stat_gendered.set_value("...")
            self._compliance_chart.set_empty_state("Loading analytics...")
            self._violation_chart.set_empty_state("Loading analytics...")
            self._camera_chart.set_empty_state("Loading analytics...")
            self._heatmap_widget.set_placeholder("Loading heatmap...")
            self._clear_top_violators("Loading analytics...")
        else:
            self._status_lbl.setText("")

    def _on_analytics_loaded(self, request_id: int, ok: bool, model: object, message: str) -> None:
        worker = self._load_worker
        self._load_worker = None
        if worker is not None:
            with contextlib.suppress(Exception):
                worker.finished_load.disconnect(self._on_analytics_loaded)
        if request_id != self._refresh_seq:
            return
        self._set_loading_state(False)
        if ok and isinstance(model, dict):
            self._apply_model(model)
        else:
            self._show_load_error(message)
        if self._pending_refresh:
            self._pending_refresh = False
            self._refresh()

    def _clear_top_violators(self, message: str | None = None) -> None:
        while self._tv_layout.count():
            item = self._tv_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if message:
            empty_lbl = QLabel(message)
            empty_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_BODY) + " background: transparent;")
            self._tv_layout.addWidget(empty_lbl)

    def _show_load_error(self, message: str) -> None:
        text = str(message or "Analytics refresh failed")
        self._status_lbl.setText("Refresh failed")
        self._debug_banner.setVisible(False)
        self._compliance_chart.set_empty_state(text)
        self._violation_chart.set_empty_state(text)
        self._camera_chart.set_empty_state(text)
        self._heatmap_widget.set_placeholder(text)
        self._clear_top_violators(text)

    def _apply_model(self, model: dict) -> None:
        stats = model["stats"]
        total = stats["total"]
        violations = stats["violations"]
        rate = stats["compliance_rate"]
        identified = stats["identified"]
        self._stat_total.set_value(str(total))
        self._stat_violations.set_value(str(violations))
        self._stat_compliance.set_value(f"{rate:.0f}%")
        self._stat_faces.set_value(str(identified))
        gender_counts = stats["gender_counts"]
        self._stat_gendered.set_value(str(stats["gendered"]))
        self._gender_breakdown_lbl.setText(
            f"Gender split: Male {gender_counts.get('male', 0)} | Female {gender_counts.get('female', 0)} | Unknown {gender_counts.get('unknown', 0)}"
        )
        self._debug_banner.setVisible(bool(model.get("is_dummy")))
        self._compliance_chart.clear_data()
        trend = model["trend"]
        if trend:
            x_idx = list(range(len(trend)))
            values = [float(t["rate"]) for t in trend]
            self._compliance_chart.set_line_data(x_idx, values, "Compliance %", color=_SUCCESS_DIM)
            self._compliance_chart.set_x_ticks([t["date"] for t in trend])
        else:
            self._compliance_chart.set_empty_state("No compliance data")

        self._violation_chart.clear_data()
        hourly = model["hourly"]
        if hourly:
            x_idx = list(range(len(hourly)))
            counts = [float(h["count"]) for h in hourly]
            if sum(counts) > 0:
                self._violation_chart.set_bar_data(x_idx, counts, color=_DANGER_DIM)
                self._violation_chart.set_x_ticks([f"{int(h['hour']):02d}:00" for h in hourly])
            else:
                self._violation_chart.set_empty_state("No violations in this range")
        else:
            self._violation_chart.set_empty_state("No violations in this range")

        self._camera_chart.clear_data()
        cam_data = model["camera_activity"]
        if cam_data:
            cam_idx = list(range(len(cam_data)))
            cam_counts = [float(c["count"]) for c in cam_data]
            self._camera_chart.set_bar_data(cam_idx, cam_counts, color=_ACCENT)
            self._camera_chart.set_x_ticks([c["camera_name"] for c in cam_data])
        else:
            self._camera_chart.set_empty_state("No camera activity")

        if model["heatmap"] is not None:
            self._heatmap_widget.set_heatmap(model["heatmap"])
        else:
            self._heatmap_widget.set_placeholder(model["heatmap_placeholder"])
        self._clear_top_violators()
        top = model["top_violators"]
        if not top:
            self._clear_top_violators("No violators in this range.")
            return
        for rank, person in enumerate(top, 1):
            card = QFrame()
            apply_roster_card_style(card, "ViolatorCard", is_active=False)
            left_layout, info_col, pills_row, right_row = build_roster_card_layout(card)

            left_cell = card.findChild(QFrame, "RosterLeft")
            if left_cell:
                left_cell.setVisible(False)
            for child in card.findChildren(QFrame):
                if child.frameShape() == QFrame.Shape.VLine:
                    child.setVisible(False)

            name_label = QLabel(person.get("identity", "Unknown"))
            name_label.setStyleSheet(text_style(_TEXT_PRI, size=FONT_SIZE_CAPTION, weight=FONT_WEIGHT_BOLD))
            info_col.addWidget(name_label)

            rank_label = QLabel(f"Rank #{rank}")
            rank_label.setStyleSheet(muted_label_style())
            info_col.addWidget(rank_label)
            gender_label = QLabel(f"Gender: {(person.get('gender') or 'unknown').title()}")
            gender_label.setStyleSheet(muted_label_style(size=FONT_SIZE_CAPTION))
            info_col.addWidget(gender_label)

            count = int(person.get("count", 0) or 0)
            count_pill = QLabel(f"{count} violations")
            count_pill.setFixedHeight(SIZE_BADGE_H)
            count_pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            count_pill.setStyleSheet(
                f"""
                color: {_DANGER};
                background-color: {_DANGER_BG_14};
                border: none;
                border-radius: {RADIUS_LG}px;
                padding: 0 {SPACE_10}px;
                font-weight: {FONT_WEIGHT_BOLD};
                """
            )
            right_row.addWidget(count_pill)

            self._tv_layout.addWidget(card)

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export PDF Report", "report.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"
        date_from, date_to, basis = self._get_time_bounds()
        camera_id = self._camera_combo.currentData()
        rule_name = self._rule_combo.currentData()
        min_alarm_level = self._alarm_combo.currentData()
        gender = self._gender_combo.currentData()
        if self._pdf_worker is not None and self._pdf_worker.isRunning():
            QMessageBox.information(self, "PDF Export", "A PDF export is already running.")
            return
        options = {
            "date_from": date_from,
            "date_to": date_to,
            "camera_id": camera_id,
            "rule_name": rule_name,
            "min_alarm_level": min_alarm_level,
            "time_basis": basis,
            "gender": gender,
        }
        self._pdf_btn.setEnabled(False)
        self._pdf_btn.setText("Exporting...")
        self._pdf_worker = _PdfExportWorker(path, options, self)

        def _done(ok: bool, message: str):
            self._pdf_worker = None
            self._pdf_btn.setEnabled(True)
            self._pdf_btn.setText("Export PDF")
            if ok:
                QMessageBox.information(self, "PDF Exported", f"Report saved to {message}")
            else:
                QMessageBox.warning(self, "Error", f"Failed to export PDF:\n{message}")

        self._pdf_worker.finished_export.connect(_done)
        self._pdf_worker.finished.connect(self._pdf_worker.deleteLater)
        self._pdf_worker.start()

