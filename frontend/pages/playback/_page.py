from __future__ import annotations

import logging
import os
import subprocess
import sys
import sqlite3
import contextlib
import json
import ast
import time

import cv2
from PySide6.QtCore import Qt, QSize, QSettings, QTimer, QEvent, QDate, QThread, Signal
from PySide6.QtGui import QFont, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSlider,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QDateEdit,
    QCheckBox,
    QScrollArea,
    QWidget,
)

from backend.camera.playback_thread import PlaybackThread
from backend.repository import db
from frontend.app_theme import page_base_styles, safe_set_point_size
from frontend.widgets.animated_stack import AnimatedStackedWidget
from frontend.icon_theme import themed_icon_pixmap
from frontend.dialogs import apply_popup_theme
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.widgets.video_widget import VideoWidget


from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_BG_18,
    _ACCENT_HI,
    _ACCENT_HI_BG_07,
    _BG_BASE,
    _BG_OVERLAY,
    _BG_SURFACE,
    _BLACK,
    _BORDER_DIM,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.styles._input_styles import _FORM_INPUTS, _FORM_COMBO
from frontend.styles._btn_styles import _ICON_BTN, _ICON_BTN_DANGER, _SECONDARY_BTN, _TAB_BTN, _TAB_BTN_ACTIVE
from frontend.styles._calendar_styles import date_popup_styles
from frontend.styles.page_styles import (
    card_shell_style,
    divider_style,
    filter_tool_button_style,
    header_bar_style,
    muted_label_style,
    saved_clips_scrollbar_style,
    section_kicker_style,
    text_style,
    toolbar_style,
    transparent_surface_style,
)
from frontend.pages.playback._widgets import ClipRowWidget, SnapshotRowWidget
from frontend.date_utils import day_timestamp_bounds, normalize_date_range, qdate_to_date
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_HEADING,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_BOLD,
    RADIUS_6,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_XS,
    SIZE_CONTROL_LG,
    SIZE_CONTROL_MD,
    SIZE_CONTROL_SM,
    SIZE_DIALOG_W,
    SIZE_FIELD_W_XS,
    SIZE_HEADER_H,
    SIZE_ICON_10,
    SIZE_PILL_H,
    SIZE_ROW_XL,
    SIZE_SECTION_H,
    SPACE_10,
    SPACE_14,
    SPACE_20,
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
    page_base_styles()
    + f"""
{date_popup_styles()}
QSlider::groove:horizontal {{
    height: {SPACE_XS}px; background: {_BG_OVERLAY}; border-radius: {RADIUS_XS}px;
}}
QSlider::handle:horizontal {{
    background: {_ACCENT_HI};
    width: {SPACE_14}px; height: {SPACE_14}px;
    margin: -{SPACE_5}px 0;
    border: none;
    border-radius: 999px;
}}
QSlider#timeline_slider::handle:horizontal {{
    background: {_ACCENT_HI};
    width: {SPACE_14}px; height: {SPACE_14}px;
    margin: -{SPACE_5}px 0;
    border: none;
    border-radius: 999px;
    image: none;
}}
QSlider::sub-page:horizontal {{ background: {_ACCENT}; border-radius: {RADIUS_XS}px; }}
QListWidget {{ background: transparent; border: none; outline: none; }}
QListWidget::item {{
    padding: {SPACE_10}px {SPACE_14}px; color: {_TEXT_SEC}; border-radius: {RADIUS_6}px; background: transparent;
}}
QListWidget::item:selected {{ background: {_ACCENT_BG_18}; color: {_TEXT_PRI}; }}
QListWidget::item:hover:!selected {{ background: {_ACCENT_HI_BG_07}; color: {_TEXT_PRI}; }}
QListWidget#clips_list {{ background: {_BG_BASE}; }}
QListWidget#clips_list::item {{ padding: 0; color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; }}
QListWidget#clips_list::item:selected {{ background: transparent; color: {_TEXT_PRI}; }}
QListWidget#clips_list::item:hover:!selected {{ background: transparent; }}
QListWidget#clips_list {{ padding-bottom: {SPACE_SM}px; }}
QPushButton#clip_delete {{
    background: transparent;
    border: none;
    padding: 0;
}}
QPushButton#clip_delete:hover {{
    background: transparent;
}}
{saved_clips_scrollbar_style()}
"""
)

logger = logging.getLogger(__name__)
_PLAYBACK_TITLE_STYLE = text_style(_TEXT_PRI)
_TIME_LABEL_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_LABEL, extra=f"padding-left: {SPACE_LG}px;")
_BG_BASE_STYLE = f"background: {_BG_BASE};"
_VIDEO_CARD_STYLE = f"background: {_BLACK}; border-radius: {RADIUS_LG}px;"
_SPEED_LABEL_STYLE = text_style(_TEXT_MUTED, size=FONT_SIZE_CAPTION, weight=FONT_WEIGHT_BOLD)


_RETIRED_PLAYBACK_THREADS: list[PlaybackThread] = []
_RETIRED_CLIP_INDEX_WORKERS: set[QThread] = set()


def _parse_clip_filename_parts(name: str) -> tuple[int | None, int | None, str]:
    if name.startswith("clip_cam") and "_" in name:
        try:
            rest = name.replace("clip_cam", "", 1)
            cam_part, ts_part = rest.split("_", 1)
            cam_id = int(cam_part)
            ts = int(ts_part.split(".", 1)[0])
            return cam_id, ts, "live"
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            return None, None, "live"
    if name.startswith("clip_"):
        try:
            ts = int(name.replace("clip_", "", 1).split(".", 1)[0])
            return None, ts, "playback"
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            return None, None, "playback"
    return None, None, "playback"


class _ClipIndexWorker(QThread):
    finished_index = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self) -> None:
        try:
            existing = set(db.get_clip_paths(limit=1000) or [])
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.warning("Failed to read existing clips index", exc_info=True)
            existing = set()
        for folder in ("data/clips_live", "data/clips"):
            if self._cancel_requested:
                break
            if not os.path.isdir(folder):
                continue
            try:
                names = sorted(
                    os.listdir(folder),
                    key=lambda n, f=folder: os.path.getmtime(os.path.join(f, n)),
                    reverse=True,
                )[:1000]
            except OSError:
                names = []
            for name in names:
                if self._cancel_requested:
                    break
                if not name.lower().endswith((".mp4", ".avi", ".mkv", ".mov", ".wmv")):
                    continue
                path = os.path.join(folder, name)
                if path in existing:
                    continue
                cam_id, ts, source = _parse_clip_filename_parts(name)
                if ts is None:
                    try:
                        ts = int(os.path.getmtime(path))
                    except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                        ts = None
                try:
                    db.add_clip(path, source, cam_id, ts, None, [], [])
                except (sqlite3.Error, OSError, TypeError, ValueError):
                    logger.warning("Failed to index clip path=%s", path, exc_info=True)
        self.finished_index.emit()


def _icon_btn(icon_path: str, size: int = 36, danger: bool = False) -> QPushButton:
    btn = QPushButton()
    btn.setFixedSize(size, size)
    btn.setStyleSheet(_ICON_BTN_DANGER if danger else _ICON_BTN)
    pix = QPixmap(icon_path)
    if not pix.isNull():
        btn.setIcon(QIcon(pix))
        btn.setIconSize(QSize(int(size * 0.52), int(size * 0.52)))
    return btn


def _set_list_active(list_widget: QListWidget, item: QListWidgetItem, activate_cb) -> None:
    if list_widget and item:
        list_widget.setCurrentItem(item)
    if activate_cb:
        activate_cb(item)


class PlaybackPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._playback_thread: PlaybackThread | None = None
        self._total_frames = 0
        self._current_frame = 0
        self._video_fps = 30.0
        self._user_seeking = False
        self._seek_was_playing = False
        self._seek_pending: int | None = None
        self._last_ui_refresh_ms: int = 0
        self._seek_timer = QTimer(self)
        self._seek_timer.setInterval(40)
        self._seek_timer.setSingleShot(True)
        self._seek_timer.timeout.connect(self._flush_seek)
        self._clip_cards: list[tuple[QListWidgetItem, ClipRowWidget]] = []
        self._snapshot_cards: list[tuple[QListWidgetItem, SnapshotRowWidget]] = []
        self._filters_ready = False
        self._clip_filter_camera = None
        self._clip_filter_rule = None
        self._clip_filter_object = None
        self._clip_filter_face = None
        self._clip_filter_from = None
        self._clip_filter_to = None
        self._clip_filters_dialog: QDialog | None = None
        self._filters_btn: QToolButton | None = None
        self._face_detect_toggle: ToggleSwitch | None = None
        self._class_filters_btn: QPushButton | None = None
        self._class_filter_dialog: QDialog | None = None
        self._class_filter_checks: dict[str, QCheckBox] = {}
        self._disabled_playback_classes: set[str] = set()
        self._media_stack: AnimatedStackedWidget | None = None
        self._media_tab_btns: dict[str, QPushButton] = {}
        self._media_open_folder_btn: QPushButton | None = None
        self._snapshots_list: QListWidget | None = None
        self._active_media_tab: str = "clips"
        self._snapshots_loaded: bool = False
        self._snapshots_dirty: bool = True
        self._snapshot_pending_rows: list[tuple[str, int, str, str]] = []
        self._snapshot_load_timer = QTimer(self)
        self._snapshot_load_timer.setSingleShot(True)
        self._snapshot_load_timer.timeout.connect(self._consume_snapshot_rows)
        self._clip_index_worker: _ClipIndexWorker | None = None
        self._clip_index_dirty = True
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header_w = QWidget()
        header_w.setFixedHeight(SIZE_HEADER_H)
        header_w.setObjectName("pb_header")
        header_w.setStyleSheet(header_bar_style(widget_id="pb_header", bg=_BG_BASE, border=_BORDER_DIM))
        hl = QHBoxLayout(header_w)
        hl.setContentsMargins(SPACE_XL, 0, SPACE_XL, 0)
        hl.setSpacing(SPACE_10)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(SIZE_CONTROL_SM, SIZE_CONTROL_SM)
        pix = themed_icon_pixmap("frontend/assets/icons/playback.png", SIZE_CONTROL_SM, SIZE_CONTROL_SM)
        if not pix.isNull():
            icon_lbl.setPixmap(pix)
        hl.addWidget(icon_lbl)

        title = QLabel("Playback & Review")
        tf = QFont()
        safe_set_point_size(tf, FONT_SIZE_HEADING)
        tf.setBold(True)
        title.setFont(tf)
        title.setStyleSheet(_PLAYBACK_TITLE_STYLE)
        hl.addWidget(title)
        hl.addStretch()

        self._fps_label = QLabel("FPS: —")
        self._fps_label.setStyleSheet(muted_label_style(size=FONT_SIZE_LABEL))
        hl.addWidget(self._fps_label)

        self._time_label = QLabel("00:00:00 / 00:00:00")
        self._time_label.setStyleSheet(_TIME_LABEL_STYLE)
        hl.addWidget(self._time_label)
        root.addWidget(header_w)

        toolbar = QWidget()
        toolbar.setFixedHeight(SIZE_HEADER_H)
        toolbar.setStyleSheet(toolbar_style(bg=_BG_SURFACE, border=_BORDER_DIM))
        tl = QHBoxLayout(toolbar)
        tl.setContentsMargins(SPACE_XL, SPACE_SM, SPACE_XL, SPACE_SM)
        tl.setSpacing(SPACE_MD)

        self._path_edit = QLineEdit()
        self._path_edit.setPlaceholderText("Select a video file to begin…")
        self._path_edit.setReadOnly(True)
        self._path_edit.setFixedHeight(SIZE_CONTROL_MD)
        self._path_edit.setStyleSheet(_FORM_INPUTS)
        _folder_act = self._path_edit.addAction(
            QIcon("frontend/assets/icons/folder.png"),
            QLineEdit.ActionPosition.TrailingPosition,
        )
        _folder_act.triggered.connect(self._open_file)
        tl.addWidget(self._path_edit, stretch=1)

        self._class_filters_btn = QPushButton("Object Classes")
        self._class_filters_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._class_filters_btn.setStyleSheet(_SECONDARY_BTN)
        self._class_filters_btn.setToolTip("Choose plugin/object classes to exclude during playback")
        self._class_filters_btn.clicked.connect(self._open_class_filters_dialog)
        tl.addWidget(self._class_filters_btn)

        _sep1 = QWidget()
        _sep1.setFixedSize(SPACE_XXXS, SPACE_XL)
        _sep1.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        tl.addWidget(_sep1)

        plugins_lbl = QLabel("Plugins")
        plugins_lbl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD}; letter-spacing: 0.{SPACE_XS}px;"
        )
        tl.addWidget(plugins_lbl)
        self._detect_toggle = ToggleSwitch()
        self._detect_toggle.setToolTip("Enable plugin/object detection during playback")
        self._detect_toggle.toggled.connect(self._on_plugins_toggled)
        tl.addWidget(self._detect_toggle)

        _sep2 = QWidget()
        _sep2.setFixedSize(SPACE_XXXS, SPACE_XL)
        _sep2.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        tl.addWidget(_sep2)

        face_lbl = QLabel("Face Recognition")
        face_lbl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD}; letter-spacing: 0.{SPACE_XS}px;"
        )
        tl.addWidget(face_lbl)
        self._face_detect_toggle = ToggleSwitch()
        self._face_detect_toggle.setToolTip("Enable face recognition during playback detection")
        self._face_detect_toggle.toggled.connect(self._on_face_detection_toggled)
        tl.addWidget(self._face_detect_toggle)

        _sep3 = QWidget()
        _sep3.setFixedSize(SPACE_XXXS, SPACE_XL)
        _sep3.setStyleSheet(divider_style(_BORDER_DIM, SPACE_XL))
        tl.addWidget(_sep3)

        rec_lbl = QLabel("Auto-Clip")
        rec_lbl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; font-weight: {FONT_WEIGHT_BOLD}; letter-spacing: 0.{SPACE_XS}px;"
        )
        tl.addWidget(rec_lbl)
        self._record_toggle = ToggleSwitch()
        self._record_toggle.setToolTip("Saves a clip to data/clips/ when a rule fires. Requires Face or Plugins ON.")
        self._record_toggle.toggled.connect(self._on_record_toggled)
        tl.addWidget(self._record_toggle)
        self._load_playback_toggle_settings()
        root.addWidget(toolbar)

        content = QWidget()
        content.setStyleSheet(_BG_BASE_STYLE)
        cl = QVBoxLayout(content)
        cl.setContentsMargins(SPACE_20, SPACE_LG, SPACE_20, SPACE_LG)
        cl.setSpacing(SPACE_MD)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(SPACE_SM)
        splitter.setStyleSheet("QSplitter::handle { background: transparent; }")

        left = QWidget()
        left.setStyleSheet(transparent_surface_style())
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(SPACE_10)

        self._video_widget = VideoWidget()
        self._video_widget.setMinimumSize(480, 280)
        self._video_widget.setStyleSheet(_VIDEO_CARD_STYLE)
        ll.addWidget(self._video_widget, stretch=1)

        ctrl_card = QWidget()
        ctrl_card.setStyleSheet(card_shell_style())
        cc = QVBoxLayout(ctrl_card)
        cc.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        cc.setSpacing(SPACE_10)

        self._timeline_slider = QSlider(Qt.Orientation.Horizontal)
        self._timeline_slider.setObjectName("timeline_slider")
        self._timeline_slider.setRange(0, 100)
        self._timeline_slider.setValue(0)
        self._timeline_slider.setStyleSheet(
            f"""
QSlider::groove:horizontal {{
    height: {SPACE_XS}px; background: {_BG_OVERLAY}; border-radius: {RADIUS_XS}px;
}}
QSlider::sub-page:horizontal {{
    background: {_ACCENT}; border-radius: {RADIUS_XS}px;
}}
QSlider::handle:horizontal {{
    background: {_ACCENT_HI};
    width: {SPACE_14}px; height: {SPACE_14}px;
    margin: -{SPACE_5}px 0;
    border: none;
    border-radius: {SPACE_14 // 2}px;
    image: none;
}}
"""
        )
        self._timeline_slider.sliderPressed.connect(self._on_seek_pressed)
        self._timeline_slider.sliderMoved.connect(self._on_seek_moved)
        self._timeline_slider.sliderReleased.connect(self._on_seek)
        cc.addWidget(self._timeline_slider)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(SPACE_6)

        self._play_btn = _icon_btn("frontend/assets/icons/play.png", SIZE_SECTION_H)
        self._play_btn.setToolTip("Play / Pause")
        self._play_btn.clicked.connect(self._toggle_play)
        ctrl_row.addWidget(self._play_btn)

        self._stop_btn = _icon_btn("frontend/assets/icons/stop.png", SIZE_SECTION_H, danger=True)
        self._stop_btn.setToolTip("Stop")
        self._stop_btn.clicked.connect(self._stop)
        ctrl_row.addWidget(self._stop_btn)

        _div = QWidget()
        _div.setFixedSize(SPACE_XXXS, SIZE_PILL_H)
        _div.setStyleSheet(divider_style(_BORDER_DIM, SIZE_PILL_H))
        ctrl_row.addSpacing(SPACE_6)
        ctrl_row.addWidget(_div)
        ctrl_row.addSpacing(SPACE_6)

        speed_lbl = QLabel("Speed")
        speed_lbl.setStyleSheet(_SPEED_LABEL_STYLE)
        ctrl_row.addWidget(speed_lbl)

        self._speed_combo = QComboBox()
        self._speed_combo.addItems(["0.25×", "0.5×", "1×", "2×", "4×"])
        self._speed_combo.setCurrentIndex(2)
        self._speed_combo.setFixedWidth(SIZE_FIELD_W_XS)
        self._speed_combo.setFixedHeight(SIZE_CONTROL_MD)
        self._speed_combo.setStyleSheet(_FORM_COMBO)
        self._speed_combo.currentIndexChanged.connect(self._change_speed)
        ctrl_row.addWidget(self._speed_combo)

        ctrl_row.addStretch()

        cc.addLayout(ctrl_row)
        ll.addWidget(ctrl_card)
        splitter.addWidget(left)

        right = QWidget()
        right.setMinimumWidth(200)
        right.setMaximumWidth(SIZE_DIALOG_W)
        right.setStyleSheet(transparent_surface_style())
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)

        media_card = QWidget()
        media_card.setStyleSheet(card_shell_style())
        media_l = QVBoxLayout(media_card)
        media_l.setContentsMargins(0, 0, 0, SPACE_MD)
        media_l.setSpacing(0)

        media_tab_bar = QWidget()
        media_tab_bar.setFixedHeight(SIZE_CONTROL_LG)
        media_tab_bar.setStyleSheet("background: transparent;")
        media_tab_l = QHBoxLayout(media_tab_bar)
        media_tab_l.setContentsMargins(SPACE_LG, 0, SPACE_MD, 0)
        media_tab_l.setSpacing(SPACE_SM)
        for key, label in (("clips", "Saved Clips"), ("snapshots", "Snapshots")):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setStyleSheet(_TAB_BTN_ACTIVE if key == "clips" else _TAB_BTN)
            btn.setFixedHeight(SIZE_CONTROL_MD)
            btn.setMinimumWidth(112)
            btn.clicked.connect(lambda _checked=False, k=key: self._switch_media_tab(k))
            media_tab_l.addWidget(btn)
            self._media_tab_btns[key] = btn
        media_tab_l.addStretch()

        self._media_open_folder_btn = QPushButton()
        self._media_open_folder_btn.setFixedSize(SIZE_CONTROL_MD, SIZE_CONTROL_MD)
        self._media_open_folder_btn.setStyleSheet(
            "QPushButton{border:none;background:transparent;padding:0;}"
            f"QPushButton:hover{{background:{_ACCENT_HI_BG_07};border-radius:{RADIUS_MD}px;}}"
            "QPushButton:pressed{background:transparent;}"
        )
        folder_pix = themed_icon_pixmap("frontend/assets/icons/folder.png", SIZE_ICON_10 + SPACE_6, SIZE_ICON_10 + SPACE_6)
        if not folder_pix.isNull():
            self._media_open_folder_btn.setIcon(QIcon(folder_pix))
        else:
            self._media_open_folder_btn.setIcon(QIcon("frontend/assets/icons/folder.png"))
        self._media_open_folder_btn.setIconSize(QSize(SIZE_ICON_10 + SPACE_6, SIZE_ICON_10 + SPACE_6))
        self._media_open_folder_btn.clicked.connect(self._open_active_media_folder)
        media_tab_l.addWidget(self._media_open_folder_btn)
        media_l.addWidget(media_tab_bar)

        self._media_stack = AnimatedStackedWidget()

        clips_tab = QWidget()
        ccv = QVBoxLayout(clips_tab)
        ccv.setContentsMargins(0, 0, 0, 0)
        ccv.setSpacing(0)

        clips_hdr_w = QWidget()
        clips_hdr_w.setFixedHeight(SIZE_CONTROL_LG)
        clips_hdr_w.setStyleSheet(transparent_surface_style())
        clips_hdr_l = QHBoxLayout(clips_hdr_w)
        clips_hdr_l.setContentsMargins(SPACE_LG, 0, SPACE_MD, 0)
        clips_hdr_l.setSpacing(SPACE_SM)

        clips_title = QLabel("SAVED CLIPS")
        clips_title.setStyleSheet(section_kicker_style())
        clips_hdr_l.addWidget(clips_title)
        clips_hdr_l.addStretch()

        self._filters_btn = QToolButton()
        self._filters_btn.setText("Filters")
        _flt = themed_icon_pixmap("frontend/assets/icons/arrow_down.png", SIZE_ICON_10, SIZE_ICON_10)
        self._filters_btn.setIcon(QIcon(_flt) if not _flt.isNull() else QIcon("frontend/assets/icons/arrow_down.png"))
        self._filters_btn.setIconSize(QSize(SIZE_ICON_10, SIZE_ICON_10))
        self._filters_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._filters_btn.setStyleSheet(filter_tool_button_style())
        self._filters_btn.clicked.connect(self._open_clip_filters_dialog)
        clips_hdr_l.addWidget(self._filters_btn)
        ccv.addWidget(clips_hdr_w)

        self._ensure_clip_filters_dialog()
        self._load_clip_filters()

        self._clips_list = QListWidget()
        self._clips_list.setObjectName("clips_list")
        self._clips_list.setAlternatingRowColors(False)
        self._clips_list.viewport().setAutoFillBackground(False)
        self._clips_list.viewport().setStyleSheet("background: transparent;")
        self._clips_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._clips_list.setSpacing(SPACE_XXS)
        self._clips_list.setUniformItemSizes(True)
        self._clips_list.setViewportMargins(0, 0, 0, SPACE_SM)
        self._clips_list.currentItemChanged.connect(self._sync_clip_card_selection)
        self._clips_list.viewport().installEventFilter(self)
        ccv.addWidget(self._clips_list, stretch=1)
        self._filters_ready = True

        self._clip_status = QLabel("")
        self._clip_status.setStyleSheet(
            f"{muted_label_style(size=FONT_SIZE_MICRO)} padding: 0 {SPACE_LG}px {SPACE_SM}px {SPACE_LG}px;"
        )
        self._clip_status.setWordWrap(True)
        ccv.addWidget(self._clip_status)

        snapshots_tab = QWidget()
        sv = QVBoxLayout(snapshots_tab)
        sv.setContentsMargins(0, 0, 0, SPACE_MD)
        sv.setSpacing(0)

        snaps_hdr_w = QWidget()
        snaps_hdr_w.setFixedHeight(SIZE_CONTROL_LG)
        snaps_hdr_w.setStyleSheet(transparent_surface_style())
        snaps_hdr_l = QHBoxLayout(snaps_hdr_w)
        snaps_hdr_l.setContentsMargins(SPACE_LG, 0, SPACE_MD, 0)
        snaps_hdr_l.setSpacing(SPACE_SM)
        snaps_title = QLabel("SNAPSHOTS")
        snaps_title.setStyleSheet(section_kicker_style())
        snaps_hdr_l.addWidget(snaps_title)
        snaps_hdr_l.addStretch()
        sv.addWidget(snaps_hdr_w)

        self._snapshots_list = QListWidget()
        self._snapshots_list.setObjectName("clips_list")
        self._snapshots_list.setAlternatingRowColors(False)
        self._snapshots_list.viewport().setAutoFillBackground(False)
        self._snapshots_list.viewport().setStyleSheet("background: transparent;")
        self._snapshots_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._snapshots_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._snapshots_list.setSpacing(SPACE_XXS)
        self._snapshots_list.setUniformItemSizes(True)
        self._snapshots_list.setViewportMargins(0, 0, 0, SPACE_SM)
        self._snapshots_list.itemClicked.connect(self._on_snapshot_item_activated)
        self._snapshots_list.currentItemChanged.connect(self._sync_snapshot_card_selection)
        self._snapshots_list.viewport().installEventFilter(self)
        sv.addWidget(self._snapshots_list, stretch=1)

        self._media_stack.addWidget(clips_tab)
        self._media_stack.addWidget(snapshots_tab)
        media_l.addWidget(self._media_stack, stretch=1)
        rl.addWidget(media_card)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        _qs = QSettings("SmartEye", "Playback")
        _saved = _qs.value("splitter/sizes")
        if _saved and len(_saved) == 2:
            try:
                splitter.setSizes([int(_saved[0]), int(_saved[1])])
            except (ValueError, TypeError):
                splitter.setSizes([900, 300])
        else:
            splitter.setSizes([900, 300])
        splitter.splitterMoved.connect(lambda _pos, _idx: _qs.setValue("splitter/sizes", splitter.sizes()))
        cl.addWidget(splitter, stretch=1)
        root.addWidget(content, stretch=1)
        self._switch_media_tab("clips")

    def on_activated(self) -> None:
        self._clip_index_dirty = True
        self._refresh_clips_list()
        self._snapshots_dirty = True
        if self._active_media_tab == "snapshots":
            self._refresh_snapshots_gallery()

    def on_deactivated(self) -> None:
        self._seek_timer.stop()
        self._snapshot_load_timer.stop()
        self._stop(wait_ms=1500)

    def on_unload(self) -> None:
        self._seek_timer.stop()
        self._snapshot_load_timer.stop()
        self._cleanup_clip_index_worker()
        self._stop(wait_ms=5000)

    def _open_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Video",
            os.path.dirname(self._path_edit.text()) or "",
            "Video Files (*.mp4 *.avi *.mkv *.mov *.wmv)",
        )
        if not path:
            return
        self._start_playback(path)

    def eventFilter(self, obj, event):
        if obj is self._clips_list.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            if self._clips_list.itemAt(event.pos()) is None:
                self._clips_list.clearSelection()
                self._sync_clip_card_selection(None, None)
        if self._snapshots_list and obj is self._snapshots_list.viewport() and event.type() == QEvent.Type.MouseButtonPress:
            if self._snapshots_list.itemAt(event.pos()) is None:
                self._snapshots_list.clearSelection()
                self._sync_snapshot_card_selection(None, None)
        return super().eventFilter(obj, event)

    def _on_frame(self, camera_id, frame, state) -> None:
        frame_idx = state.get("frame_index", 0)
        self._current_frame = frame_idx
        self._video_widget.update_frame(frame, state)
        now_ms = int(time.time() * 1000)
        if not self._user_seeking and (now_ms - self._last_ui_refresh_ms >= 33):
            self._timeline_slider.blockSignals(True)
            self._timeline_slider.setValue(frame_idx)
            self._timeline_slider.blockSignals(False)
            if self._total_frames > 0:
                cur_sec = frame_idx / self._video_fps
                total_sec = self._total_frames / self._video_fps
                self._time_label.setText(f"{self._format_time(cur_sec)} / {self._format_time(total_sec)}")
            self._last_ui_refresh_ms = now_ms

    def _switch_media_tab(self, key: str) -> None:
        if not self._media_stack:
            return
        self._active_media_tab = key
        idx = 0 if key == "clips" else 1
        self._media_stack.setCurrentIndex(idx)
        for k, btn in self._media_tab_btns.items():
            active = k == key
            btn.setChecked(active)
            btn.setStyleSheet(_TAB_BTN_ACTIVE if active else _TAB_BTN)
        if key == "snapshots" and (self._snapshots_dirty or not self._snapshots_loaded):
            if self._is_playback_running():
                self._refresh_snapshots_gallery_quick()
            else:
                QTimer.singleShot(0, self._refresh_snapshots_gallery)
        if self._media_open_folder_btn:
            self._media_open_folder_btn.setToolTip(
                "Open Saved Clips Folder" if key == "clips" else "Open Snapshots Folder"
            )

    def _is_playback_running(self) -> bool:
        return bool(self._playback_thread and self._playback_thread.isRunning())

    def _open_active_media_folder(self) -> None:
        key = "clips"
        if self._media_stack and self._media_stack.currentIndex() == 1:
            key = "snapshots"

        target = os.path.join("data", "snapshots") if key == "snapshots" else self._resolve_saved_clips_folder()
        try:
            os.makedirs(target, exist_ok=True)
            self._open_path_with_system(os.path.abspath(target))
            self._clip_status.setText(f"Opened folder: {target}")
        except Exception:
            logger.warning("Could not open media folder path=%s", target, exc_info=True)
            self._clip_status.setText("Could not open folder")

    @staticmethod
    def _open_path_with_system(path: str) -> None:
        if sys.platform.startswith("win") and hasattr(os, "startfile"):
            os.startfile(path)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.Popen(["open", path])
            return
        subprocess.Popen(["xdg-open", path])

    def _resolve_saved_clips_folder(self) -> str:
        # Prefer the selected clip so folder navigation matches what the user is viewing.
        if self._clips_list and self._clips_list.currentItem() is not None:
            selected_path = self._clips_list.currentItem().data(Qt.ItemDataRole.UserRole)
            if isinstance(selected_path, str) and os.path.isfile(selected_path):
                return os.path.dirname(os.path.abspath(selected_path))

        # Fall back to indexed clips (ordered by newest ts in DB).
        try:
            for row in db.get_clips(limit=25) or []:
                clip_path = str(row.get("path") or "")
                if clip_path and os.path.isfile(clip_path):
                    return os.path.dirname(os.path.abspath(clip_path))
        except (sqlite3.Error, OSError, ValueError, TypeError):
            logger.warning("Could not resolve saved clips folder from DB", exc_info=True)

        # Last-resort fallback if the index is empty.
        for folder in ("data/clips_live", "data/clips"):
            if os.path.isdir(folder):
                try:
                    if any(
                        entry.is_file() and entry.name.lower().endswith((".mp4", ".avi", ".mkv", ".mov", ".wmv"))
                        for entry in os.scandir(folder)
                    ):
                        return os.path.abspath(folder)
                except OSError:
                    logger.debug("Could not scan clips folder=%s", folder, exc_info=True)

        return os.path.abspath(os.path.join("data", "clips_live"))

    def _open_snapshot_path(self, path: str) -> None:
        if not path or not os.path.exists(path):
            return
        try:
            self._open_path_with_system(path)
        except Exception:
            logger.debug("Could not open snapshot with default viewer path=%s", path, exc_info=True)

    def _on_snapshot_item_activated(self, item) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        self._open_snapshot_path(path)

    def _sync_snapshot_card_selection(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        for it, card in self._snapshot_cards:
            card.set_active(it is current)

    def _delete_snapshot(self, path: str) -> None:
        deleted = False
        try:
            if path and os.path.exists(path):
                os.remove(path)
                deleted = True
        except OSError as e:
            self._clip_status.setText(f"Delete failed: {e}")
            return

        if self._snapshots_list:
            removed_row = -1
            removed_pair = None
            for item, card in self._snapshot_cards:
                item_path = item.data(Qt.ItemDataRole.UserRole)
                if item_path == path:
                    removed_row = self._snapshots_list.row(item)
                    removed_pair = (item, card)
                    break
            if removed_row >= 0:
                taken = self._snapshots_list.takeItem(removed_row)
                if taken is not None:
                    del taken
                if removed_pair is not None:
                    self._snapshot_cards.remove(removed_pair)

        # Mark stale so a future snapshots-tab visit can fully reconcile with DB records.
        self._snapshots_dirty = True
        if not deleted:
            logger.debug("Snapshot file already missing path=%s", path)

    def _refresh_snapshots_gallery(self) -> None:
        self._start_snapshot_gallery_refresh(include_db=True, limit=150)

    def _refresh_snapshots_gallery_quick(self) -> None:
        self._start_snapshot_gallery_refresh(include_db=False, limit=80)

    def _start_snapshot_gallery_refresh(self, include_db: bool, limit: int) -> None:
        if not self._snapshots_list:
            return
        self._snapshot_load_timer.stop()
        self._snapshot_pending_rows.clear()
        self._snapshots_list.clear()
        self._snapshot_cards.clear()
        self._snapshots_loaded = True
        self._snapshots_dirty = False

        rows: dict[str, tuple[int, str, str]] = {}
        if include_db:
            try:
                for row in db.get_detection_logs(limit=max(10, int(limit))):
                    p = str(row.get("snapshot_path") or "").strip()
                    if p and os.path.exists(p):
                        ts = int(row.get("timestamp") or os.path.getmtime(p) or 0)
                        camera_name = str(row.get("camera_name") or f"Camera {row.get('camera_id') or '-'}")
                        rules_raw = row.get("rules_triggered")
                        rule_text = "No rule context"
                        if isinstance(rules_raw, str) and rules_raw.strip():
                            rule_text = rules_raw
                        rows[p] = (ts, camera_name, rule_text)
            except (sqlite3.Error, OSError, ValueError, TypeError):
                logger.warning("Failed to load snapshot records", exc_info=True)

        if os.path.isdir("data/snapshots"):
            try:
                for name in os.listdir("data/snapshots"):
                    p = os.path.join("data/snapshots", name)
                    if os.path.isfile(p) and name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                        if p not in rows:
                            rows[p] = (int(os.path.getmtime(p) or 0), "Snapshot", "No rule context")
            except OSError:
                logger.debug("Failed filesystem snapshot listing", exc_info=True)

        if not rows:
            return

        ordered = sorted(rows.items(), key=lambda kv: kv[1][0], reverse=True)[: max(10, int(limit))]
        self._snapshot_pending_rows = [(p, ts, cam, rule) for p, (ts, cam, rule) in ordered]
        self._snapshot_load_timer.start(0)

    def _consume_snapshot_rows(self) -> None:
        if not self._snapshots_list or not self._snapshot_pending_rows:
            return
        batch = 6 if self._is_playback_running() else 20
        count = min(batch, len(self._snapshot_pending_rows))
        for _ in range(count):
            path, ts, camera_name, rule_text = self._snapshot_pending_rows.pop(0)
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            row_w = SnapshotRowWidget(path, ts, camera_name=camera_name, rule_text=rule_text)
            item.setSizeHint(QSize(0, row_w.height()))
            row_w.selected.connect(lambda lw=self._snapshots_list, it=item: lw.setCurrentItem(it))
            row_w.delete_requested.connect(lambda p=path: self._delete_snapshot(p))
            self._snapshots_list.addItem(item)
            self._snapshots_list.setItemWidget(item, row_w)
            self._snapshot_cards.append((item, row_w))

        if self._snapshots_list.currentItem() is None and self._snapshots_list.count() > 0:
            self._snapshots_list.setCurrentRow(0)
            self._sync_snapshot_card_selection(self._snapshots_list.currentItem(), None)

        if self._snapshot_pending_rows:
            self._snapshot_load_timer.start(0)

    def _on_clip_saved(self, path: str) -> None:
        self._clip_index_dirty = True
        self._refresh_clips_list()
        self._clip_status.setText(f"Saved: {os.path.basename(path)}")

    def _on_clip_failed(self, message: str) -> None:
        self._clip_status.setText(message)

    def _on_plugins_toggled(self, state: bool) -> None:
        try:
            db.set_setting("playback_plugins_enabled", bool(state))
        except (sqlite3.Error, OSError, ValueError):
            logger.warning("Failed to persist playback plugins setting", exc_info=True)
        if self._playback_thread:
            self._playback_thread.set_plugins_enabled(state)
            self._playback_thread.set_record_enabled(self._record_toggle.isChecked())
            self._apply_playback_detection_filters()
        self._sync_record_enabled()

    def _on_face_detection_toggled(self, state: bool) -> None:
        try:
            db.set_setting("playback_face_detection_enabled", bool(state))
        except (sqlite3.Error, OSError, ValueError):
            logger.warning("Failed to persist playback face detection setting", exc_info=True)
        if self._playback_thread:
            self._playback_thread.set_face_detection_enabled(state)
        self._sync_record_enabled()

    @staticmethod
    def _normalize_class_name(value: str) -> str:
        return str(value or "").strip().lower()

    def _current_disabled_object_classes(self) -> set[str]:
        out = set()
        for cls_name, cb in self._class_filter_checks.items():
            if not cb.isChecked():
                norm = self._normalize_class_name(cls_name)
                if norm:
                    out.add(norm)
        return out

    def _persist_class_filter_settings(self) -> None:
        self._disabled_playback_classes = self._current_disabled_object_classes()
        self._sanitize_disabled_playback_classes()
        try:
            db.set_setting("playback_disabled_object_classes", json.dumps(sorted(self._disabled_playback_classes)))
        except (sqlite3.Error, OSError, ValueError):
            logger.warning("Failed to persist playback class filters", exc_info=True)

    def _sanitize_disabled_playback_classes(self) -> None:
        # Preserve explicit user choices, including "disable all".
        # Only remove stale class names that are no longer present.
        if not self._disabled_playback_classes:
            return
        try:
            active_classes = {
                self._normalize_class_name(row.get("class_name"))
                for row in (db.get_plugin_classes(enabled_only=True) or [])
                if self._normalize_class_name(row.get("class_name"))
            }
        except (sqlite3.Error, OSError, ValueError, TypeError):
            logger.warning("Failed to load plugin classes for playback filter validation", exc_info=True)
            return
        if active_classes:
            self._disabled_playback_classes = {
                c for c in self._disabled_playback_classes if c in active_classes
            }

    def _apply_playback_detection_filters(self) -> None:
        if not self._playback_thread:
            return
        self._playback_thread.set_plugins_enabled(self._detect_toggle.isChecked())
        self._playback_thread.set_face_detection_enabled(self._face_detect_toggle.isChecked() if self._face_detect_toggle else True)
        self._playback_thread.set_disabled_object_classes(self._disabled_playback_classes)

    def _on_record_toggled(self, state: bool) -> None:
        if state and not self._is_record_allowed():
            self._record_toggle.blockSignals(True)
            self._record_toggle.setChecked(False)
            self._record_toggle.blockSignals(False)
            self._clip_status.setText("Auto-Clip requires Face or Plugins to be enabled.")
            with contextlib.suppress(sqlite3.Error, OSError, ValueError):
                db.set_setting("playback_record_enabled", False)
            return
        try:
            db.set_setting("playback_record_enabled", bool(state))
        except (sqlite3.Error, OSError, ValueError):
            logger.warning("Failed to persist playback record setting", exc_info=True)
        if self._playback_thread:
            self._playback_thread.set_record_enabled(state)

    def _is_record_allowed(self) -> bool:
        return bool(self._detect_toggle.isChecked() or (self._face_detect_toggle and self._face_detect_toggle.isChecked()))

    def _sync_record_enabled(self) -> None:
        allowed = self._is_record_allowed()
        self._record_toggle.setEnabled(allowed)
        self._record_toggle.setToolTip(
            "Saves a clip when a rule fires." if allowed else "Enable Face or Plugins before Auto-Clip."
        )
        if not allowed and self._record_toggle.isChecked():
            self._record_toggle.blockSignals(True)
            self._record_toggle.setChecked(False)
            self._record_toggle.blockSignals(False)
            with contextlib.suppress(sqlite3.Error, OSError, ValueError):
                db.set_setting("playback_record_enabled", False)
            if self._playback_thread:
                self._playback_thread.set_record_enabled(False)

    def _load_playback_toggle_settings(self) -> None:
        try:
            plugins = db.get_bool("playback_plugins_enabled", db.get_bool("playback_detection_enabled", False))
            rec = db.get_bool("playback_record_enabled", False)
            face = db.get_bool("playback_face_detection_enabled", True)
            raw_disabled = db.get_setting("playback_disabled_object_classes", [])
            if isinstance(raw_disabled, str):
                try:
                    raw_disabled = json.loads(raw_disabled or "[]")
                except (TypeError, ValueError, json.JSONDecodeError):
                    raw_disabled = ast.literal_eval(raw_disabled) if raw_disabled else []
            self._disabled_playback_classes = {
                self._normalize_class_name(v) for v in (raw_disabled or []) if self._normalize_class_name(v)
            }
            self._sanitize_disabled_playback_classes()
            try:
                db.set_setting("playback_disabled_object_classes", json.dumps(sorted(self._disabled_playback_classes)))
            except (sqlite3.Error, OSError, ValueError):
                logger.warning("Failed to normalize playback class filters", exc_info=True)
            self._detect_toggle.setChecked(bool(plugins))
            if self._face_detect_toggle:
                self._face_detect_toggle.setChecked(bool(face))
            self._record_toggle.setChecked(bool(rec and (plugins or face)))
            self._sync_record_enabled()
        except (sqlite3.Error, OSError, ValueError):
            logger.warning("Failed to load playback toggle settings", exc_info=True)
            self._detect_toggle.setChecked(False)
            self._record_toggle.setChecked(False)
            if self._face_detect_toggle:
                self._face_detect_toggle.setChecked(True)
            self._sync_record_enabled()

    def _on_finished(self, camera_id=None) -> None:
        self._sync_play_button(paused=True)
        if self._active_media_tab == "snapshots" and self._snapshots_dirty:
            QTimer.singleShot(0, self._refresh_snapshots_gallery)

    def _toggle_play(self) -> None:
        if self._playback_thread is None:
            if self._path_edit.text():
                self._start_playback(self._path_edit.text())
            return
        if not self._playback_thread.isRunning():
            if self._path_edit.text():
                self._start_playback(self._path_edit.text())
            return
        if self._playback_thread.is_paused:
            self._playback_thread.resume()
            self._sync_play_button(paused=False)
        else:
            self._playback_thread.pause()
            self._sync_play_button(paused=True)

    def _stop(self, wait_ms: int = 1500) -> None:
        thread = self._playback_thread
        self._playback_thread = None
        if thread:
            self._detach_playback_thread_signals(thread)
            thread.stop()
            if thread.isRunning() and not thread.wait(max(250, int(wait_ms))):
                logger.warning("Playback thread is still running; deferring destruction until finished")
                self._retain_playback_thread_until_finished(thread)
            else:
                thread.deleteLater()
        self._video_widget.show_placeholder("No video loaded")
        self._timeline_slider.setValue(0)
        self._fps_label.setText("FPS: —")
        self._time_label.setText("00:00:00 / 00:00:00")
        self._sync_play_button(paused=True)

    def _detach_playback_thread_signals(self, thread: PlaybackThread) -> None:
        with contextlib.suppress(Exception):
            thread.frame_ready.disconnect(self._on_frame)
        with contextlib.suppress(Exception):
            thread.playback_finished.disconnect(self._on_finished)
        with contextlib.suppress(Exception):
            thread.clip_saved.disconnect(self._on_clip_saved)
        with contextlib.suppress(Exception):
            thread.clip_failed.disconnect(self._on_clip_failed)

    def _retain_playback_thread_until_finished(self, thread: PlaybackThread) -> None:
        if thread in _RETIRED_PLAYBACK_THREADS:
            return
        _RETIRED_PLAYBACK_THREADS.append(thread)

        def _cleanup() -> None:
            with contextlib.suppress(Exception):
                if thread in _RETIRED_PLAYBACK_THREADS:
                    _RETIRED_PLAYBACK_THREADS.remove(thread)
            with contextlib.suppress(Exception):
                thread.deleteLater()

        with contextlib.suppress(Exception):
            thread.finished.connect(_cleanup)

    def _on_seek_pressed(self) -> None:
        self._user_seeking = True
        self._seek_was_playing = False
        if self._playback_thread and self._playback_thread.isRunning():
            self._seek_was_playing = not self._playback_thread.is_paused
            self._playback_thread.pause()
            self._sync_play_button(paused=True)

    def _on_seek_moved(self, value: int) -> None:
        if self._total_frames > 0:
            cur_sec = value / self._video_fps
            total_sec = self._total_frames / self._video_fps
            self._time_label.setText(f"{self._format_time(cur_sec)} / {self._format_time(total_sec)}")
        self._seek_pending = value
        if not self._seek_timer.isActive():
            self._seek_timer.start()

    def _on_seek(self) -> None:
        if self._playback_thread:
            self._playback_thread.seek(self._timeline_slider.value())
            if self._seek_was_playing:
                self._playback_thread.resume()
                self._sync_play_button(paused=False)
        self._user_seeking = False
        self._seek_was_playing = False
        self._seek_pending = None

    def _flush_seek(self) -> None:
        if self._seek_pending is None:
            return
        if self._playback_thread:
            self._playback_thread.seek(self._seek_pending)

    def _change_speed(self, idx: int) -> None:
        self._apply_speed()

    def _apply_speed(self) -> None:
        speeds = [0.25, 0.5, 1.0, 2.0, 4.0]
        idx = self._speed_combo.currentIndex()
        if self._playback_thread and idx < len(speeds):
            base_fps = self._video_fps or 30.0
            self._playback_thread.set_fps_limit(max(0.25, base_fps * speeds[idx]))

    def _ensure_class_filter_dialog(self) -> None:
        if self._class_filter_dialog is not None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Plugin Object Classes")
        apply_popup_theme(dlg)
        dlg.setModal(False)
        dlg.setFixedWidth(420)

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        layout.setSpacing(SPACE_SM)

        hint = QLabel("Uncheck classes to disable them during plugin detection in playback.")
        hint.setWordWrap(True)
        hint.setStyleSheet(muted_label_style(size=FONT_SIZE_CAPTION))
        layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, 0)
        body_l.setSpacing(SPACE_XXS)
        body_l.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, stretch=1)

        row = QHBoxLayout()
        row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(SIZE_CONTROL_MD)
        close_btn.setStyleSheet(_SECONDARY_BTN)
        close_btn.clicked.connect(dlg.close)
        row.addWidget(close_btn)
        layout.addLayout(row)

        self._class_filter_dialog = dlg
        self._class_filter_checks = {}
        self._class_filter_body_layout = body_l

    def _load_playback_class_filters(self) -> None:
        self._ensure_class_filter_dialog()
        if self._class_filter_dialog is None:
            return
        lay = self._class_filter_body_layout
        while lay.count() > 1:
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._class_filter_checks.clear()

        classes = []
        try:
            classes = db.get_plugin_classes(enabled_only=True) or []
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            classes = []

        names = sorted({str(c.get("class_name") or "").strip() for c in classes if str(c.get("class_name") or "").strip()})
        if not names:
            empty = QLabel("No detection classes available.")
            empty.setStyleSheet(muted_label_style(size=FONT_SIZE_LABEL))
            lay.insertWidget(0, empty)
            return

        for name in names:
            cb = QCheckBox(name)
            cb.setChecked(self._normalize_class_name(name) not in self._disabled_playback_classes)
            cb.toggled.connect(self._on_class_filter_toggled)
            lay.insertWidget(lay.count() - 1, cb)
            self._class_filter_checks[name] = cb

    def _on_class_filter_toggled(self, _checked: bool) -> None:
        self._persist_class_filter_settings()
        self._apply_playback_detection_filters()

    def _open_class_filters_dialog(self) -> None:
        self._load_playback_class_filters()
        if not self._class_filter_dialog:
            return
        if self._class_filter_dialog.isVisible():
            self._class_filter_dialog.raise_()
            self._class_filter_dialog.activateWindow()
            return
        btn = self._class_filters_btn
        if btn:
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            self._class_filter_dialog.move(pos.x(), pos.y() + SPACE_6)
        self._class_filter_dialog.show()

    def _ensure_clip_filters_dialog(self) -> None:
        if self._clip_filters_dialog is not None:
            return
        dlg = QDialog(self)
        dlg.setWindowTitle("Clip Filters")
        apply_popup_theme(dlg)
        dlg.setModal(False)
        dlg.setFixedWidth(420)

        fl = QVBoxLayout(dlg)
        fl.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        fl.setSpacing(SPACE_SM)

        hint = QLabel("Use one or more filters to narrow saved clips.")
        hint.setWordWrap(True)
        hint.setStyleSheet(muted_label_style(size=FONT_SIZE_CAPTION))
        fl.addWidget(hint)

        self._clip_filter_camera = QComboBox()
        self._clip_filter_camera.setFixedHeight(SIZE_CONTROL_MD)
        self._clip_filter_camera.setStyleSheet(_FORM_COMBO)
        fl.addWidget(self._clip_filter_camera)

        self._clip_filter_rule = QComboBox()
        self._clip_filter_rule.setFixedHeight(SIZE_CONTROL_MD)
        self._clip_filter_rule.setStyleSheet(_FORM_COMBO)
        fl.addWidget(self._clip_filter_rule)

        self._clip_filter_object = QComboBox()
        self._clip_filter_object.setFixedHeight(SIZE_CONTROL_MD)
        self._clip_filter_object.setStyleSheet(_FORM_COMBO)
        fl.addWidget(self._clip_filter_object)

        self._clip_filter_face = QLineEdit()
        self._clip_filter_face.setPlaceholderText("Face label")
        self._clip_filter_face.setFixedHeight(SIZE_CONTROL_MD)
        self._clip_filter_face.setStyleSheet(_FORM_INPUTS)
        fl.addWidget(self._clip_filter_face)

        date_row = QHBoxLayout()
        date_row.setSpacing(SPACE_SM)

        self._clip_filter_from = QDateEdit()
        self._clip_filter_from.setCalendarPopup(True)
        self._clip_filter_from.setDisplayFormat("yyyy-MM-dd")
        self._clip_filter_from.setMinimumDate(QDate(1970, 1, 1))
        self._clip_filter_from.setSpecialValueText("From")
        self._clip_filter_from.setDate(self._clip_filter_from.minimumDate())
        self._clip_filter_from.setFixedHeight(SIZE_CONTROL_MD)
        self._clip_filter_from.setStyleSheet(_FORM_INPUTS)
        date_row.addWidget(self._clip_filter_from)

        self._clip_filter_to = QDateEdit()
        self._clip_filter_to.setCalendarPopup(True)
        self._clip_filter_to.setDisplayFormat("yyyy-MM-dd")
        self._clip_filter_to.setMinimumDate(QDate(1970, 1, 1))
        self._clip_filter_to.setSpecialValueText("To")
        self._clip_filter_to.setDate(self._clip_filter_to.minimumDate())
        self._clip_filter_to.setFixedHeight(SIZE_CONTROL_MD)
        self._clip_filter_to.setStyleSheet(_FORM_INPUTS)
        date_row.addWidget(self._clip_filter_to)
        fl.addLayout(date_row)

        row2 = QHBoxLayout()
        row2.addStretch()
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedHeight(SIZE_CONTROL_MD)
        clear_btn.setStyleSheet(_SECONDARY_BTN)
        row2.addWidget(clear_btn)
        fl.addLayout(row2)

        action_row = QHBoxLayout()
        action_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(SIZE_CONTROL_MD)
        close_btn.setStyleSheet(_SECONDARY_BTN)
        close_btn.clicked.connect(dlg.close)
        action_row.addWidget(close_btn)
        fl.addLayout(action_row)

        self._clip_filter_face.textChanged.connect(self._on_clip_filters_changed)
        self._clip_filter_camera.currentIndexChanged.connect(self._on_clip_filters_changed)
        self._clip_filter_rule.currentIndexChanged.connect(self._on_clip_filters_changed)
        self._clip_filter_object.currentIndexChanged.connect(self._on_clip_filters_changed)
        self._clip_filter_from.dateChanged.connect(self._on_clip_filters_changed)
        self._clip_filter_to.dateChanged.connect(self._on_clip_filters_changed)
        clear_btn.clicked.connect(self._clear_clip_filters)

        self._clip_filters_dialog = dlg

    def _open_clip_filters_dialog(self) -> None:
        self._ensure_clip_filters_dialog()
        if not self._clip_filters_dialog:
            return
        if self._clip_filters_dialog.isVisible():
            self._clip_filters_dialog.raise_()
            self._clip_filters_dialog.activateWindow()
            return
        btn = self._filters_btn
        if btn:
            pos = btn.mapToGlobal(btn.rect().bottomLeft())
            dialog_w = self._clip_filters_dialog.width()
            x = pos.x() - dialog_w + btn.width()
            y = pos.y() + SPACE_6
            self._clip_filters_dialog.move(x, y)
        self._clip_filters_dialog.show()

    def _load_clip_filters(self) -> None:
        if not self._clip_filter_camera:
            return
        self._clip_filter_camera.clear()
        self._clip_filter_camera.addItem("All Cameras", -1)
        try:
            for cam in db.get_cameras(enabled_only=False) or []:
                self._clip_filter_camera.addItem(cam.get("name", f"Camera {cam.get('id')}"), int(cam.get("id")))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass

        self._clip_filter_rule.clear()
        self._clip_filter_rule.addItem("Any Rule", "")
        try:
            for rule in db.get_rules(enabled_only=False) or []:
                self._clip_filter_rule.addItem(rule.get("name", "Rule"), rule.get("name", ""))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass

        self._clip_filter_object.clear()
        self._clip_filter_object.addItem("Any Object", "")
        try:
            classes = db.get_plugin_classes(enabled_only=True) or []
            seen = set()
            for cls in classes:
                name = cls.get("class_name")
                if name and name not in seen:
                    seen.add(name)
                    self._clip_filter_object.addItem(name, name)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass

    def _on_clip_filters_changed(self, _value=None) -> None:
        if not self._filters_ready or not hasattr(self, "_clips_list"):
            return
        self._refresh_clips_list()

    def _clear_clip_filters(self) -> None:
        self._clip_filter_face.setText("")
        self._clip_filter_camera.setCurrentIndex(0)
        self._clip_filter_rule.setCurrentIndex(0)
        self._clip_filter_object.setCurrentIndex(0)
        self._clip_filter_from.setDate(self._clip_filter_from.minimumDate())
        self._clip_filter_to.setDate(self._clip_filter_to.minimumDate())
        self._refresh_clips_list()

    def _get_clip_filter_values(self) -> dict:
        camera_id = self._clip_filter_camera.currentData()
        face_label = self._clip_filter_face.text().strip()
        rule_name = self._clip_filter_rule.currentData()
        object_type = self._clip_filter_object.currentData()

        ts_from = None
        ts_to = None
        min_date = self._clip_filter_from.minimumDate()
        has_from = self._clip_filter_from.date() != min_date
        has_to = self._clip_filter_to.date() != min_date
        if has_from and has_to:
            start = qdate_to_date(self._clip_filter_from.date())
            end = qdate_to_date(self._clip_filter_to.date())
            date_range = normalize_date_range(start, end)
            if date_range.swapped:
                self._clip_filter_from.setDate(QDate(date_range.start.year, date_range.start.month, date_range.start.day))
                self._clip_filter_to.setDate(QDate(date_range.end.year, date_range.end.month, date_range.end.day))
            ts_from, ts_to = day_timestamp_bounds(date_range.start, date_range.end)
        elif has_from:
            start = qdate_to_date(self._clip_filter_from.date())
            ts_from, _ = day_timestamp_bounds(start, start)
        elif has_to:
            end = qdate_to_date(self._clip_filter_to.date())
            _, ts_to = day_timestamp_bounds(end, end)

        return {
            "camera_id": camera_id,
            "face_label": face_label or None,
            "rule_triggered": rule_name or None,
            "object_type": object_type or None,
            "ts_from": ts_from,
            "ts_to": ts_to,
        }

    @staticmethod
    def _parse_clip_filename(name: str) -> tuple[int | None, int | None, str]:
        return _parse_clip_filename_parts(name)

    def _sync_clips_index(self) -> None:
        self._ensure_clips_index_async()

    def _ensure_clips_index_async(self) -> None:
        if not self._clip_index_dirty:
            return
        if self._clip_index_worker is not None and self._clip_index_worker.isRunning():
            return
        self._clip_index_dirty = False
        worker = _ClipIndexWorker(self)
        self._clip_index_worker = worker

        def _done():
            self._clip_index_worker = None
            worker.deleteLater()
            self._refresh_clips_list()

        worker.finished.connect(_done)
        worker.start()

    def _cleanup_clip_index_worker(self) -> None:
        worker = self._clip_index_worker
        self._clip_index_worker = None
        if worker is None:
            return
        with contextlib.suppress(Exception):
            worker.finished_index.disconnect()
        with contextlib.suppress(Exception):
            worker.finished.disconnect()
        with contextlib.suppress(Exception):
            worker.cancel()
        if worker.isRunning():
            worker.setParent(None)
            _RETIRED_CLIP_INDEX_WORKERS.add(worker)

            def _cleanup(w=worker):
                _RETIRED_CLIP_INDEX_WORKERS.discard(w)
                with contextlib.suppress(Exception):
                    w.deleteLater()

            worker.finished.connect(_cleanup)
        else:
            with contextlib.suppress(Exception):
                worker.deleteLater()

    def _refresh_clips_list(self) -> None:
        selected_path = None
        cur = self._clips_list.currentItem()
        if cur:
            selected_path = cur.data(Qt.ItemDataRole.UserRole)
        self._clips_list.clear()
        self._clip_cards.clear()
        self._ensure_clips_index_async()
        filters = self._get_clip_filter_values()
        try:
            rows = db.get_clips(
                camera_id=filters["camera_id"],
                ts_from=filters["ts_from"],
                ts_to=filters["ts_to"],
                face_label=filters["face_label"],
                object_type=filters["object_type"],
                rule_triggered=filters["rule_triggered"],
                limit=500,
            )
        except (sqlite3.Error, OSError, TypeError, ValueError):
            logger.warning("Failed to load filtered clips", exc_info=True)
            rows = []

        if not rows:
            self._clip_status.setText("No clips saved yet")
            return
        selected_item = None
        seen_paths: set[str] = set()
        seen_names: set[str] = set()
        for row in rows:
            path = row.get("path")
            if not path or not os.path.exists(path):
                continue
            norm_path = os.path.normcase(os.path.abspath(path))
            name = os.path.splitext(os.path.basename(path))[0]
            norm_name = name.strip().lower()
            if norm_path in seen_paths or norm_name in seen_names:
                continue
            ts = row.get("ts")
            if not ts:
                try:
                    ts = int(os.path.getmtime(path))
                except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                    ts = 0
            source = row.get("source") or "playback"
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setSizeHint(QSize(0, SIZE_ROW_XL))
            row_w = ClipRowWidget(name, source, ts, path)
            row_w.clicked.connect(lambda _=False, lw=self._clips_list, it=item: _set_list_active(lw, it, self._on_clip_item_activated))
            row_w.set_delete_callback(lambda p=path: self._delete_clip(p))
            self._clips_list.addItem(item)
            self._clips_list.setItemWidget(item, row_w)
            self._clip_cards.append((item, row_w))
            seen_paths.add(norm_path)
            seen_names.add(norm_name)
            if selected_path and path == selected_path:
                selected_item = item
        if selected_item:
            self._clips_list.setCurrentItem(selected_item)
        self._sync_clip_card_selection(self._clips_list.currentItem(), None)

    def _on_clip_item_activated(self, item) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path or not os.path.exists(path):
            return
        try:
            current_path = self._path_edit.text().strip()
            if (
                current_path
                and os.path.abspath(current_path) == os.path.abspath(path)
                and self._playback_thread
                and self._playback_thread.isRunning()
            ):
                return
        except OSError:
            pass
        self._start_playback(path)

    def _sync_clip_card_selection(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        for it, card in self._clip_cards:
            card.set_active(it is current)

    def _delete_clip(self, path: str) -> None:
        try:
            if path and os.path.exists(path):
                os.remove(path)
            try:
                db.delete_clip(path)
            except (sqlite3.Error, OSError, ValueError):
                logger.warning("Failed to delete clip from database path=%s", path, exc_info=True)
            self._clip_status.setText(f"Deleted: {os.path.basename(path)}")
        except OSError as e:
            self._clip_status.setText(f"Delete failed: {e}")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as e:
            logger.exception("Unexpected clip deletion failure path=%s", path)
            self._clip_status.setText(f"Delete failed: {e}")
        self._clip_index_dirty = True
        self._refresh_clips_list()

    def _start_playback(self, path: str) -> None:
        self._stop(wait_ms=120)
        self._path_edit.setText(path)
        self._playback_thread = PlaybackThread(path, virtual_camera_id=-1)
        self._playback_thread.set_plugins_enabled(self._detect_toggle.isChecked())
        self._playback_thread.set_record_enabled(self._record_toggle.isChecked())
        self._apply_playback_detection_filters()
        self._playback_thread.frame_ready.connect(self._on_frame)
        self._playback_thread.playback_finished.connect(self._on_finished)
        self._playback_thread.clip_saved.connect(self._on_clip_saved)
        self._playback_thread.clip_failed.connect(self._on_clip_failed)
        cap = cv2.VideoCapture(path)
        if cap.isOpened():
            self._total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            self._video_fps = fps
            self._fps_label.setText(f"FPS: {fps:.0f}")
            total_sec = self._total_frames / fps
            self._time_label.setText(f"00:00:00 / {self._format_time(total_sec)}")
            self._timeline_slider.setRange(0, max(0, self._total_frames - 1))
            cap.release()
        self._clip_status.setText("")
        self._playback_thread.start()
        self._sync_play_button(paused=False)
        self._apply_speed()

    def _sync_play_button(self, paused: bool) -> None:
        icon_path = "frontend/assets/icons/play.png" if paused else "frontend/assets/icons/pause.png"
        pix = themed_icon_pixmap(icon_path, int(SIZE_SECTION_H * 0.52), int(SIZE_SECTION_H * 0.52))
        if not pix.isNull():
            self._play_btn.setIcon(QIcon(pix))
            self._play_btn.setIconSize(QSize(int(SIZE_SECTION_H * 0.52), int(SIZE_SECTION_H * 0.52)))

    @staticmethod
    def _format_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

