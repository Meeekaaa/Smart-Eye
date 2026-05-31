import contextlib
import logging
import time
import warnings
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt, QTimer, QSettings
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from backend.camera.camera_manager import get_camera_manager
from backend.repository import db
from backend.models import model_loader
from frontend.app_theme import page_base_styles, safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.widgets.alarm_badge_widget import AlarmBadgeWidget
from frontend.widgets.multi_feed_widget import MultiFeedWidget
from frontend.widgets.performance_widget import PerformanceWidget
from frontend.widgets.stat_card_widget import StatCardWidget
from utils.system_monitor import get_monitor
from frontend.styles._colors import (
    _BG_BASE,
    _BG_RAISED,
    _BG_OVERLAY,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED,
    _ACCENT,
    _ACCENT_HI,
    _DANGER_BG_18,
    _DANGER_BORDER_40_ALT,
    _SUCCESS,
    _SUCCESS_DIM,
    _DANGER,
    _DANGER_DIM,
    _WARNING,
)
from frontend.styles._btn_styles import _PRIMARY_BTN, _DANGER_BTN
from frontend.styles._input_styles import _FORM_COMBO
from frontend.styles.page_styles import header_bar_style
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_LARGE,
    FONT_SIZE_XXL,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_XL,
    SIZE_BTN_W_135,
    SIZE_CONTROL_18,
    SIZE_CONTROL_MD,
    SIZE_CONTROL_XS,
    SIZE_HEADER_H,
    SIZE_ICON_LG,
    SIZE_PANEL_MIN,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_5,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XXXS,
)


warnings.filterwarnings("ignore", category=RuntimeWarning, message=".*disconnect.*")

logger = logging.getLogger(__name__)


class DashboardPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            page_base_styles(FONT_SIZE_BODY)
            + f"""
            QScrollArea {{ border: none; background-color: transparent; }}
            {_FORM_COMBO}
        """
        )

        self._alarm_badges = {}
        self._state_labels = {}
        self._camera_plugin_names = {}
        self._last_hud_counts_refresh = 0.0
        self._last_render_ts: dict[int, float] = {}
        try:
            render_fps = float(db.get_float("ui_live_render_fps", 15.0) or 15.0)
        except Exception:
            render_fps = 15.0
        self._render_interval_sec = 1.0 / max(1.0, min(60.0, render_fps))

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        _header_w = QWidget()
        _header_w.setFixedHeight(SIZE_HEADER_H)
        _header_w.setObjectName("dash_header")
        _header_w.setStyleSheet(header_bar_style(widget_id="dash_header", bg=_BG_BASE, border=_BORDER_DIM))
        _hl = QHBoxLayout(_header_w)
        _hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        _hl.setSpacing(SPACE_MD)

        _icon_lbl = QLabel()
        _icon_lbl.setFixedSize(SIZE_ICON_LG, SIZE_ICON_LG)
        _icon_pix = themed_icon_pixmap("frontend/assets/icons/dashboard.png", SIZE_ICON_LG, SIZE_ICON_LG)
        if not _icon_pix.isNull():
            _icon_lbl.setPixmap(_icon_pix)
        _hl.addWidget(_icon_lbl)

        _title = QLabel("Live Dashboard")
        _title_font = QFont()
        safe_set_point_size(_title_font, FONT_SIZE_LARGE)
        _title_font.setBold(True)
        _title.setFont(_title_font)
        _title.setStyleSheet("background: transparent;")
        _hl.addWidget(_title)
        _hl.addStretch()

        reload_btn = QPushButton("Reload Plugins")
        reload_btn.setFixedHeight(SIZE_CONTROL_MD)
        reload_btn.setMinimumWidth(SIZE_BTN_W_135)
        reload_btn.setStyleSheet(_PRIMARY_BTN)
        reload_btn.setToolTip("Reload all detection models without stopping cameras")
        reload_btn.clicked.connect(self._reload_plugins)
        _hl.addWidget(reload_btn)

        self._start_btn = QPushButton("Start All")
        self._start_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._start_btn.setMinimumWidth(SIZE_BTN_W_135)
        self._start_btn.setStyleSheet(_PRIMARY_BTN)
        self._start_btn.clicked.connect(self._start_all)
        _hl.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop All")
        self._stop_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._stop_btn.setMinimumWidth(SIZE_BTN_W_135)
        self._stop_btn.setStyleSheet(_DANGER_BTN)
        self._stop_btn.clicked.connect(self._stop_all)
        _hl.addWidget(self._stop_btn)

        root.addWidget(_header_w)

        self._splitter = QSplitter(Qt.Orientation.Horizontal)
        self._splitter.setChildrenCollapsible(False)
        self._splitter.setHandleWidth(8)
        self._splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        left_widget = QWidget()
        left_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        left_panel = QVBoxLayout(left_widget)
        left_panel.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_MD, SPACE_XL)
        left_panel.setSpacing(SPACE_LG)

        self._multi_feed = MultiFeedWidget()
        self._multi_feed.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._multi_feed.count_changed.connect(lambda _: self._update_hud_counts())
        left_panel.addWidget(self._multi_feed, stretch=1)

        self._hud_timer = QTimer(self)
        self._hud_timer.setInterval(1500)
        self._hud_timer.timeout.connect(self._sync_feeds)
        self._hud_timer.start()

        self._hud_frame = QFrame()
        self._hud_frame.setFixedHeight(SIZE_CONTROL_MD)
        self._hud_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        self._hud_frame.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        hud_layout = QHBoxLayout(self._hud_frame)
        hud_layout.setContentsMargins(0, 0, 0, 0)
        hud_layout.setSpacing(SPACE_SM)

        icon_path = Path(__file__).resolve().parents[2] / "assets" / "icons" / "cameras.png"
        self._hud_icon = QLabel()
        if icon_path.exists():
            pm = QPixmap(str(icon_path)).scaled(
                SIZE_CONTROL_18, SIZE_CONTROL_18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        self._hud_icon.setPixmap(pm)
        self._hud_icon.setFixedSize(SIZE_CONTROL_18, SIZE_CONTROL_18)
        self._hud_icon.setStyleSheet("background: transparent;")
        hud_layout.addWidget(self._hud_icon)

        self._hud_online = QLabel("Online 0")
        self._hud_online.setStyleSheet(
            f"color: {_ACCENT_HI}; font-weight: {FONT_WEIGHT_BOLD}; font-size: {FONT_SIZE_CAPTION}px;"
            f" letter-spacing: 0.{SPACE_5}px; background: transparent;"
            f" padding: 0 {SPACE_6}px;"
        )
        hud_layout.addWidget(self._hud_online)

        sep = QLabel("|")
        sep.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; background: transparent;")
        hud_layout.addWidget(sep)

        self._hud_offline = QLabel("Offline 0")
        self._hud_offline.setStyleSheet(
            f"color: {_DANGER}; font-weight: {FONT_WEIGHT_BOLD}; font-size: {FONT_SIZE_CAPTION}px;"
            f" letter-spacing: 0.{SPACE_5}px; background: transparent;"
            f" padding: 0 {SPACE_6}px;"
        )
        hud_layout.addWidget(self._hud_offline)

        self._hud_status = QLabel("")
        self._hud_status.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_LABEL}px; background: transparent;")
        hud_layout.addWidget(self._hud_status)
        hud_layout.addStretch()

        left_panel.addWidget(self._hud_frame)
        self._splitter.addWidget(left_widget)

        right_widget = QWidget()
        right_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        right_widget.setMinimumWidth(SIZE_PANEL_MIN)
        right_panel = QVBoxLayout(right_widget)
        right_panel.setContentsMargins(SPACE_MD, SPACE_LG, SPACE_XL, SPACE_XL)
        right_panel.setSpacing(SPACE_LG)

        alarms_header = QHBoxLayout()
        alarms_header.setSpacing(SPACE_SM)
        alarms_title = QLabel("Active Alarms")
        alarms_font = QFont()
        safe_set_point_size(alarms_font, FONT_SIZE_BODY)
        alarms_font.setBold(True)
        alarms_title.setFont(alarms_font)
        alarms_title.setStyleSheet(f"background: transparent; color: {_TEXT_PRI};")
        alarms_header.addWidget(alarms_title)

        self._alarm_count_badge = QLabel("0")
        self._alarm_count_badge.setFixedHeight(SIZE_CONTROL_XS)
        self._alarm_count_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._alarm_count_badge.setStyleSheet(f"""
            background: {_BG_OVERLAY}; color: {_TEXT_SEC};
            border: {SPACE_XXXS}px solid {_BORDER_DIM}; border-radius: {RADIUS_MD}px;
            font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD};
            padding: 0 {SPACE_SM}px; min-width: {SPACE_20}px;
        """)
        alarms_header.addWidget(self._alarm_count_badge)
        alarms_header.addStretch()
        right_panel.addLayout(alarms_header)

        alarms_card = QFrame()
        alarms_card.setObjectName("AlarmsCard")
        alarms_card.setStyleSheet(f"""
            QFrame#AlarmsCard {{
                background-color: {_BG_RAISED};
                border: {SPACE_XXXS}px solid {_BORDER};
                border-radius: {RADIUS_MD}px;
            }}
        """)
        alarms_vbox = QVBoxLayout(alarms_card)
        alarms_vbox.setContentsMargins(SPACE_MD, SPACE_MD, SPACE_MD, SPACE_MD)
        alarms_vbox.setSpacing(0)

        self._alarms_area = QScrollArea()
        self._alarms_area.setWidgetResizable(True)
        self._alarms_area.setStyleSheet("border: none; background: transparent;")
        self._alarms_container = QWidget()
        self._alarms_container.setStyleSheet("background: transparent;")
        self._alarms_layout = QVBoxLayout(self._alarms_container)
        self._alarms_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._alarms_layout.setSpacing(SPACE_SM)
        self._alarms_layout.setContentsMargins(0, 0, 0, 0)

        self._no_alarm_label = QLabel("No active alarms")
        self._no_alarm_label.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_SEMIBOLD}; "
            f"padding: {SPACE_XL}px {SPACE_LG}px; background: transparent;"
        )
        self._no_alarm_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._no_alarm_label.setText("No active alarms\nSystem is currently within configured rules")
        self._alarms_layout.addWidget(self._no_alarm_label)
        self._alarms_area.setWidget(self._alarms_container)
        alarms_vbox.addWidget(self._alarms_area)
        right_panel.addWidget(alarms_card, stretch=1)

        self._perf_widget = PerformanceWidget()
        right_panel.addWidget(self._perf_widget)
        self._providers_timer = QTimer(self)
        self._providers_timer.setInterval(4000)
        self._providers_timer.timeout.connect(self._update_providers)
        self._providers_timer.start()

        stats_row = QHBoxLayout()
        stats_row.setSpacing(SPACE_10)
        self._stat_total = StatCardWidget("Detections", "0", "Today", _ACCENT)
        self._stat_violations = StatCardWidget("Violations", "0", "Today", _DANGER_DIM)
        self._stat_compliance = StatCardWidget("Compliance", "100%", "Rate", _SUCCESS_DIM)
        stats_row.addWidget(self._stat_total)
        stats_row.addWidget(self._stat_violations)
        stats_row.addWidget(self._stat_compliance)
        right_panel.addLayout(stats_row)

        self._splitter.addWidget(right_widget)
        self._splitter.setStretchFactor(0, 3)
        self._splitter.setStretchFactor(1, 1)

        saved = db.get_setting("dashboard_splitter_state", "")
        if saved:
            self._splitter.restoreState(QByteArray.fromHex(saved.encode()))
        self._splitter.splitterMoved.connect(self._save_splitter)

        _qs = QSettings("SmartEye", "Dashboard")
        _saved = _qs.value("splitter/sizes")
        if _saved and len(_saved) == 2:
            try:
                self._splitter.setSizes([int(_saved[0]), int(_saved[1])])
            except (ValueError, TypeError):
                self._splitter.setSizes([700, 300])
        else:
            self._splitter.setSizes([700, 300])
        self._splitter.splitterMoved.connect(lambda _pos, _idx: _qs.setValue("splitter/sizes", self._splitter.sizes()))

        root.addWidget(self._splitter, stretch=1)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_stats)
        self._refresh_timer.start(5000)

    def on_activated(self):
        self._refresh_timer.start(5000)
        self._hud_timer.start(1500)
        if hasattr(self, "_perf_widget"):
            with contextlib.suppress(Exception):
                self._perf_widget.resume()
        self._refresh_stats()
        self._sync_feeds()

    def on_deactivated(self):
        self._refresh_timer.stop()
        self._hud_timer.stop()
        with contextlib.suppress(Exception):
            self._perf_widget.pause()
        self._disconnect_all_camera_signals()

    def on_unload(self):
        self._disconnect_all_camera_signals()
        with contextlib.suppress(Exception):
            self._multi_feed.clear_all()
        with contextlib.suppress(Exception):
            self._clear_alarms()

    def _save_splitter(self):
        db.set_setting("dashboard_splitter_state", bytes(self._splitter.saveState().toHex()).decode())

    def _auto_set_grid(self, online: int):
        if online <= 1:
            size = 1
        elif online <= 4:
            size = 2
        else:
            size = 3

        if getattr(self, "_last_auto_grid", None) != size:
            self._last_auto_grid = size
            self._multi_feed.set_grid_size(size)

    def _reload_plugins(self):
        from backend.pipeline.detector_manager import notify_plugins_changed

        try:
            notify_plugins_changed()
            # Refresh live feeds and provider badges so any plugin/provider change is visible.
            self._sync_feeds()
            self._update_providers()
            self._set_hud("Plugins reloaded", _SUCCESS)
        except Exception:
            logger.exception("Dashboard plugin reload failed")
            self._set_hud("Plugin reload failed -- check logs", _DANGER)

    def _start_all(self):
        mgr = get_camera_manager()
        mgr.start_all_enabled()
        cameras = db.get_cameras(enabled_only=True)
        if not cameras:
            self._set_hud("No enabled cameras -- add cameras in Cameras", _WARNING)
            return
        for cam in cameras:
            cid = cam["id"]
            self._multi_feed.add_feed(cid, cam["name"])
            thread = mgr.get_thread(cid)
            if thread:
                with contextlib.suppress(Exception):
                    thread.frame_ready.disconnect(self._on_frame)
                with contextlib.suppress(Exception):
                    thread.fps_updated.disconnect(self._on_fps)
                with contextlib.suppress(Exception):
                    thread.error_occurred.disconnect(self._on_error)
                thread.frame_ready.connect(self._on_frame)
                thread.fps_updated.connect(self._on_fps)
                thread.error_occurred.connect(self._on_error)
        self._set_hud(f"Starting {len(cameras)} camera(s)...", _TEXT_SEC)
        self._update_hud_counts()

    def _stop_all(self):
        get_camera_manager().stop_all()
        self._multi_feed.clear_all()
        self._clear_alarms()
        self._set_hud("Cameras stopped", _TEXT_MUTED)
        self._update_hud_counts()

    def _set_hud(self, text: str, color: str):
        self._hud_status.setText(text)
        self._hud_status.setStyleSheet(f"color: {color}; font-size: {FONT_SIZE_LABEL}px; background: transparent;")

    def _update_hud_counts(self):
        cams = db.get_cameras()
        total = len(cams)
        online = 0
        try:
            mgr = get_camera_manager()
            online = sum(1 for c in cams if (t := mgr.get_thread(c["id"])) is not None and getattr(t, "isRunning", lambda: False)())
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        offline = max(0, total - online)
        self._hud_online.setText(f"Online {online}")
        self._hud_offline.setText(f"Offline {offline}")
        self._auto_set_grid(online)

    def _disconnect_all_camera_signals(self):
        try:
            mgr = get_camera_manager()
            active_ids = mgr.get_active_ids()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            active_ids = []
        for cid in active_ids:
            thread = None
            with contextlib.suppress(Exception):
                thread = mgr.get_thread(cid)
            if not thread:
                continue
            with contextlib.suppress(Exception):
                thread.frame_ready.disconnect(self._on_frame)
            with contextlib.suppress(Exception):
                thread.fps_updated.disconnect(self._on_fps)
            with contextlib.suppress(Exception):
                thread.error_occurred.disconnect(self._on_error)
    def _on_frame(self, camera_id, frame, state):
        now = time.monotonic()
        last_render = self._last_render_ts.get(camera_id, 0.0)
        if now - last_render >= self._render_interval_sec:
            self._last_render_ts[camera_id] = now
            self._multi_feed.update_frame(camera_id, frame, state)
        self._update_hud(camera_id, state)
        self._update_alarms(state)
        self._perf_widget.update_inference(
            state.get("face_time_ms", 0),
            state.get("object_time_ms", 0),
        )

    def _on_fps(self, camera_id, fps):

        widget = self._multi_feed.get_widget(camera_id)
        if widget:
            widget.set_fps(fps)

    def _on_error(self, camera_id, msg):
        widget = self._multi_feed.get_widget(camera_id)
        if widget:
            widget.show_placeholder(f"Error: {msg}")

    def _update_hud(self, camera_id, state):
        err = state.get("error")
        if err:
            self._set_hud(err, _DANGER)
            return
        self._update_hud_counts_throttled()

    def _update_hud_counts_throttled(self, interval_sec: float = 1.0):
        import time

        now = time.monotonic()
        if (now - self._last_hud_counts_refresh) < interval_sec:
            return
        self._last_hud_counts_refresh = now
        self._update_hud_counts()

    def _update_alarms(self, state):
        violations = state.get("active_violations", [])
        if not violations:
            self._clear_alarms()
            return
        self._no_alarm_label.hide()
        current_ids = set()
        for v in violations:
            rid = v["rule_id"]
            current_ids.add(rid)
            if rid not in self._alarm_badges:
                badge = AlarmBadgeWidget(v["rule_name"], v["level"])
                self._alarms_layout.addWidget(badge)
                self._alarm_badges[rid] = badge
            else:
                self._alarm_badges[rid].set_level(v["level"])
                self._alarm_badges[rid].set_text(f"{v['rule_name']} ({int(v['duration'])}s)")
        for rid in list(self._alarm_badges.keys()):
            if rid not in current_ids:
                badge = self._alarm_badges.pop(rid)
                badge.stop()
                self._alarms_layout.removeWidget(badge)
                badge.deleteLater()
        self._refresh_alarm_badge()

    def _update_providers(self):
        try:
            items = model_loader.get_provider_summary()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            items = []
        try:
            mon = get_monitor()
            gpu_name = mon.gpu_name
            cpu_name = mon.cpu_name
            cpu_name_long = mon.cpu_name_long
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            gpu_name = ""
            cpu_name = ""
            cpu_name_long = ""
        with contextlib.suppress(Exception):
            self._perf_widget.update_providers(items, gpu_name, cpu_name, cpu_name_long)
        if not self._alarm_badges:
            self._no_alarm_label.show()

    def _sync_feeds(self):
        try:
            mgr = get_camera_manager()
            cams = db.get_cameras(enabled_only=True)
            active_ids = set()
            for cam in cams:
                cid = cam["id"]
                thread = mgr.get_thread(cid)
                if thread and thread.isRunning():
                    active_ids.add(cid)
                    if not self._multi_feed.get_widget(cid):
                        self._multi_feed.add_feed(cid, cam.get("name", f"Cam {cid}"))
                    with contextlib.suppress(Exception):
                        thread.frame_ready.disconnect(self._on_frame)
                    with contextlib.suppress(Exception):
                        thread.fps_updated.disconnect(self._on_fps)
                    with contextlib.suppress(Exception):
                        thread.error_occurred.disconnect(self._on_error)
                    thread.frame_ready.connect(self._on_frame)
                    thread.fps_updated.connect(self._on_fps)
                    thread.error_occurred.connect(self._on_error)
            for wid in list(self._multi_feed.get_ids()):
                if wid not in active_ids:
                    self._multi_feed.remove_feed(wid)
            self._update_hud_counts()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.debug("Failed to sync feeds", exc_info=True)

    def _refresh_alarm_badge(self):
        count = len(self._alarm_badges)
        self._alarm_count_badge.setText(str(count))
        if count > 0:
            self._alarm_count_badge.setStyleSheet(f"""
                background: {_DANGER_BG_18};
                color: {_DANGER};
                border: {SPACE_XXXS}px solid {_DANGER_BORDER_40_ALT};
                border-radius: {RADIUS_MD}px;
                font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD};
                padding: 0 {SPACE_SM}px; min-width: {SPACE_20}px;
            """)
        else:
            self._alarm_count_badge.setStyleSheet(f"""
                background: {_BG_OVERLAY};
                color: {_TEXT_SEC};
                border: {SPACE_XXXS}px solid {_BORDER_DIM};
                border-radius: {RADIUS_MD}px;
                font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD};
                padding: 0 {SPACE_SM}px; min-width: {SPACE_20}px;
            """)

    def _clear_alarms(self):
        for badge in self._alarm_badges.values():
            badge.stop()
            self._alarms_layout.removeWidget(badge)
            badge.deleteLater()
        self._alarm_badges.clear()
        self._no_alarm_label.show()
        self._refresh_alarm_badge()

    def _refresh_stats(self):
        from datetime import date

        today = date.today().isoformat()
        stats = db.get_detection_stats(date_from=today)
        total = stats.get("total", 0) or 0
        violations = stats.get("violations", 0) or 0
        compliant = total - violations
        rate = (compliant / total * 100) if total > 0 else 100.0
        self._stat_total.set_value(str(total))
        self._stat_violations.set_value(str(violations))
        self._stat_compliance.set_value(f"{rate:.0f}%")

