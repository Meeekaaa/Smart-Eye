from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from backend.camera.camera_manager import get_camera_manager
from backend.repository import db
from backend.pipeline.detector_manager import notify_plugins_changed
from frontend.app_theme import safe_set_point_size
from frontend.icon_theme import themed_icon_pixmap
from frontend.services.camera_service import CameraService
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton
from frontend.widgets.action_feedback import make_manager_footer_layout
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_BG_12,
    _ACCENT_BG_15,
    _ACCENT_HI,
    _ACCENT_HI_BG_20,
    _BG_RAISED,
    _BG_SURFACE,
    _BORDER,
    _BORDER_DIM,
    _BORDER_DIM_00,
    _BORDER_DIM_55,
    _SUCCESS,
    _SUCCESS_BG_14,
    _MUTED_BG_10,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.styles._banner_styles import make_edit_banner
from frontend.styles.page_styles import divider_style, muted_label_style, section_kicker_style, text_style
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_9,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_SUBHEAD,
    FONT_WEIGHT_BOLD,
    RADIUS_5,
    RADIUS_MD,
    SPACE_6,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
    SIZE_BADGE_H,
    SIZE_BTN_W_80,
    SIZE_BTN_W_MD,
    SIZE_BTN_W_SM,
    SIZE_CONTROL_18,
    SIZE_CONTROL_MD,
    SIZE_ITEM_SM,
    SIZE_LABEL_MIN,
    SIZE_LABEL_W,
    SIZE_PREVIEW_H,
    SIZE_PREVIEW_H_INNER,
    SIZE_PREVIEW_W,
    SIZE_PREVIEW_W_INNER,
    SIZE_ROW_48,
    SIZE_ROW_MD,
    SIZE_SECTION_H,
    SIZE_TABLE_COL_SM,
    SPACE_XXL,
)

from ._constants import (
    _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST,
    _TEXT_BTN_RED,
    _TEXT_BTN_RED_CONFIRM,
    _combo_ss,
    _input_ss,
    _make_sdiv,
    _pill,
    _spin_ss,
    _srow,
)

logger = logging.getLogger(__name__)
_EMPTY_TITLE_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_BODY, weight=FONT_WEIGHT_BOLD)
_EMPTY_SUB_STYLE = muted_label_style(size=FONT_SIZE_CAPTION)
_HERO_STYLE = "QFrame{{background:{bg};border:none;}}".format(bg=_BG_RAISED)
_NAME_LABEL_STYLE = text_style(_TEXT_PRI)
_SOURCE_LABEL_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_CAPTION)
_ROW_LABEL_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_LABEL, extra=f"min-width:{SIZE_LABEL_MIN}px;")
_PLUGIN_NAME_STYLE = text_style(_TEXT_PRI, size=FONT_SIZE_BODY)
_NO_PLUGIN_STYLE = muted_label_style(size=FONT_SIZE_LABEL) + f" font-style:italic; padding:{SPACE_XS}px 0;"
_SEPARATOR_STYLE = divider_style(_BORDER_DIM)
_SOFT_SEPARATOR_STYLE = divider_style(_BORDER_DIM_55)
_CLASS_EDITOR_TITLE_STYLE = text_style(_TEXT_PRI)
_CLASS_EDITOR_SUB_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_LABEL)
_CLASS_ROW_LABEL_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_LABEL)
_CLASS_EMPTY_STYLE = muted_label_style(size=FONT_SIZE_LABEL) + f" padding:{SPACE_LG}px;"


class CameraDetailPanel(QWidget):
    delete_requested = Signal(int)
    saved = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cam_id: int | None = None
        self._cam: dict | None = None
        self._build_empty()

    def load_camera(self, cam: dict):
        self._cam_id = cam["id"]
        self._cam = cam
        self._show_view(cam)

    def clear(self):
        self._cam_id = None
        self._cam = None
        self._build_empty()

    def _clear(self):
        def _drain_layout(lay):
            while lay.count():
                item = lay.takeAt(0)
                w = item.widget()
                if w is not None:
                    try:
                        w.hide()
                    except (RuntimeError, TypeError):
                        logger.debug("Failed to hide widget during detail clear", exc_info=True)
                    w.deleteLater()
                else:
                    child_lay = item.layout()
                    if child_lay:
                        _drain_layout(child_lay)
                        try:
                            from shiboken6 import delete as _del

                            _del(child_lay)
                        except (ImportError, RuntimeError):
                            logger.debug("Failed to delete nested layout in detail clear", exc_info=True)

        old = self.layout()
        if old is not None:
            _drain_layout(old)
            try:
                from shiboken6 import delete

                delete(old)
            except (ImportError, RuntimeError):
                logger.debug("Failed to delete old layout in detail panel clear", exc_info=True)

    def _build_empty(self):
        self._clear()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)

        wrap = QWidget()
        wrap.setStyleSheet("background:transparent;border:none;")
        wl = QVBoxLayout(wrap)
        wl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        wl.setSpacing(SPACE_10)
        wl.setContentsMargins(SPACE_XXL, SPACE_XXL, SPACE_XXL, SPACE_XXL)

        icon_lbl = QLabel()
        icon_lbl.setFixedSize(SIZE_ROW_48, SIZE_ROW_48)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet("background:transparent;border:none;")
        pix = QPixmap("frontend/assets/icons/camera.png")
        if not pix.isNull():
            icon_lbl.setPixmap(
                pix.scaled(SIZE_ROW_MD, SIZE_ROW_MD, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        wl.addWidget(icon_lbl, alignment=Qt.AlignmentFlag.AlignCenter)

        t = QLabel("No camera selected")
        t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        t.setStyleSheet(_EMPTY_TITLE_STYLE)
        wl.addWidget(t)

        s = QLabel("Select a camera from the list, or add a new one.")
        s.setWordWrap(True)
        s.setAlignment(Qt.AlignmentFlag.AlignCenter)
        s.setStyleSheet(_EMPTY_SUB_STYLE)
        wl.addWidget(s)
        lay.addWidget(wrap)

    def _show_view(self, cam: dict):
        self._clear()
        enabled = bool(cam.get("enabled"))
        face_on = bool(cam.get("face_recognition"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        hero = QFrame()
        hero.setStyleSheet(_HERO_STYLE)
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(SPACE_20, SPACE_14, SPACE_20, SPACE_14)
        hl.setSpacing(SPACE_14)
        hl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        import cv2 as _cv2
        import numpy as _np_arr

        preview_lbl = QLabel()
        preview_lbl.setFixedSize(SIZE_PREVIEW_W, SIZE_PREVIEW_H)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_lbl.setStyleSheet(
            f"background:{_BG_RAISED}; border:{SPACE_XXXS}px solid {_BORDER};"
            f"border-radius:{RADIUS_MD}px; color:{_TEXT_MUTED}; font-size:{FONT_SIZE_9}px;"
        )
        preview_lbl.setText("no signal")

        _last_frame: list = [None]

        def _on_frame(cid: int, frame: _np_arr.ndarray, _res: dict):
            if cid == cam.get("id"):
                _last_frame[0] = frame

        def _tick():
            f = _last_frame[0]
            if f is None:
                return
            try:
                rgb = _cv2.cvtColor(f, _cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                qi = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                scaled = QPixmap.fromImage(qi).scaled(
                    SIZE_PREVIEW_W_INNER,
                    SIZE_PREVIEW_H_INNER,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                preview_lbl.setPixmap(scaled)
                preview_lbl.setText("")
            except (RuntimeError, ValueError, TypeError):
                logger.debug("Failed to render camera preview frame cam_id=%s", cam.get("id"), exc_info=True)

        try:
            _cm = get_camera_manager()
            _thread = _cm.get_thread(cam["id"])
            if _thread and _thread.isRunning():
                _thread.frame_ready.connect(_on_frame)
                _ptimer = QTimer(preview_lbl)
                _ptimer.setInterval(500)
                _ptimer.timeout.connect(_tick)
                _ptimer.start()

                def _cleanup(_obj=None, _t=_thread, _fn=_on_frame, _tm=_ptimer):
                    try:
                        _tm.stop()
                    except Exception:
                        pass
                    try:
                        if hasattr(_t, "frame_ready"):
                            _t.frame_ready.disconnect(_fn)
                    except (RuntimeError, TypeError, AttributeError):
                        logger.debug("Failed to disconnect preview frame signal cam_id=%s", cam.get("id"), exc_info=True)

                preview_lbl.destroyed.connect(_cleanup)
        except (ImportError, RuntimeError, OSError):
            logger.warning("Failed to initialize camera preview stream cam_id=%s", cam.get("id"), exc_info=True)

        hl.addWidget(preview_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(SPACE_XS)

        nf = QFont()
        safe_set_point_size(nf, FONT_SIZE_SUBHEAD)
        nf.setBold(True)
        nlbl = QLabel(cam.get("name", ""))
        nlbl.setFont(nf)
        nlbl.setStyleSheet(_NAME_LABEL_STYLE)
        col.addWidget(nlbl)

        if cam.get("source"):
            src_lbl = QLabel(cam["source"])
            src_lbl.setStyleSheet(_SOURCE_LABEL_STYLE)
            src_lbl.setWordWrap(True)
            col.addWidget(src_lbl)

        col.addSpacing(SPACE_XS)

        chips = QHBoxLayout()
        chips.setSpacing(SPACE_6)
        sc = _SUCCESS if enabled else _TEXT_MUTED
        sbg = _SUCCESS_BG_14 if enabled else _MUTED_BG_10
        chips.addWidget(_pill("ENABLED" if enabled else "DISABLED", sc, sbg))
        chips.addWidget(
            _pill(
                "FACE ON" if face_on else "FACE OFF",
                _ACCENT_HI if face_on else _TEXT_MUTED,
                _ACCENT_BG_12 if face_on else _MUTED_BG_10,
            )
        )
        try:
            plugins = db.get_camera_plugins(cam["id"])
            if plugins:
                chips.addWidget(
                    _pill(
                        f"{len(plugins)} plugin{'s' if len(plugins) != 1 else ''}",
                        _ACCENT_HI,
                        _ACCENT_BG_12,
                    )
                )
        except (sqlite3.Error, OSError, ValueError):
            plugins = []
        chips.addStretch()
        col.addLayout(chips)
        hl.addLayout(col, stretch=1)
        lay.addWidget(hero)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("border:none; background:transparent;")
        sb = QWidget()
        bl = QVBoxLayout(sb)
        bl.setContentsMargins(SPACE_XL, SPACE_LG, SPACE_XL, SPACE_LG)
        bl.setSpacing(SPACE_XXS)
        scroll.setWidget(sb)
        lay.addWidget(scroll, stretch=1)

        def _info_row(label: str, value: str):
            w = QWidget()
            w.setStyleSheet("background:transparent; border:none;")
            r = QHBoxLayout(w)
            r.setContentsMargins(0, SPACE_XS, 0, SPACE_XS)
            r.setSpacing(SPACE_10)
            lb = QLabel(f"{label}:")
            lb.setFixedWidth(SIZE_LABEL_W)
            lb.setStyleSheet(_ROW_LABEL_STYLE)
            r.addWidget(lb)
            vl = QLabel(value if value else "\u2014")
            vl.setStyleSheet(
                f"color:{_TEXT_PRI}; font-size:{FONT_SIZE_BODY}px;"
                if value
                else f"color:{_TEXT_MUTED}; font-size:{FONT_SIZE_CAPTION}px; font-style:italic;"
            )
            vl.setWordWrap(True)
            r.addWidget(vl, stretch=1)
            return w

        def _div():
            d = QFrame()
            d.setFrameShape(QFrame.Shape.HLine)
            d.setStyleSheet(_SOFT_SEPARATOR_STYLE)
            return d

        def _section(title: str):
            c = QWidget()
            c.setStyleSheet("background:transparent; border:none;")
            r = QHBoxLayout(c)
            r.setContentsMargins(0, SPACE_SM, 0, SPACE_XXS)
            r.setSpacing(SPACE_SM)
            lb = QLabel(title.upper())
            lb.setStyleSheet(section_kicker_style())
            r.addWidget(lb)
            ln = QFrame()
            ln.setFrameShape(QFrame.Shape.HLine)
            ln.setStyleSheet(
                "background:qlineargradient(spread:pad,x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {_ACCENT_HI_BG_20},stop:1 {_BORDER_DIM_00}); "
                f"border:none; max-height:{SPACE_XXXS}px;"
            )
            r.addWidget(ln, stretch=1)
            return c

        bl.addWidget(_section("General"))
        for lbl, val in [
            ("Source", cam.get("source") or ""),
            ("Location", cam.get("location") or ""),
            ("Resolution", cam.get("resolution") or "1280x720"),
            ("FPS Limit", str(cam.get("fps_limit") or 30)),
            ("Status", "Enabled" if enabled else "Disabled"),
        ]:
            bl.addWidget(_info_row(lbl, val))
            bl.addWidget(_div())

        bl.addSpacing(SPACE_10)
        bl.addWidget(_section("Face Recognition"))
        face_thresh = cam.get("face_similarity_threshold")
        if face_thresh is None:
            try:
                face_thresh = db.get_setting("face_similarity_threshold", 0.45)
            except (sqlite3.Error, OSError, ValueError):
                face_thresh = 0.45
        try:
            thresh_display = f"{int(float(face_thresh) * 100)}%"
        except (TypeError, ValueError):
            thresh_display = "45%"
        try:
            max_faces = db.get_setting(f"camera_{cam['id']}_max_faces", None)
            if max_faces is None:
                max_faces = db.get_setting("max_faces_per_frame", 16) or 16
        except (sqlite3.Error, OSError, ValueError):
            max_faces = 16
        try:
            min_face_size = db.get_setting(f"camera_{cam['id']}_min_face_size", None)
            if min_face_size is None:
                min_face_size = db.get_setting("min_face_size", 24) or 24
        except (sqlite3.Error, OSError, ValueError):
            min_face_size = 24
        for lbl, val in [
            ("Face Recognition", "Enabled" if face_on else "Disabled"),
            ("Match Threshold", thresh_display),
            ("Max Faces / Frame", str(int(max_faces))),
            ("Min Face Size", f"{int(min_face_size)} px"),
        ]:
            bl.addWidget(_info_row(lbl, val))
            bl.addWidget(_div())

        bl.addSpacing(SPACE_10)
        bl.addWidget(_section("Plugins"))
        try:
            assigned = db.get_camera_plugins(cam["id"])
        except (sqlite3.Error, OSError, ValueError):
            assigned = []
        if assigned:
            for p in assigned:
                pw = QWidget()
                pw.setStyleSheet("background:transparent; border:none;")
                pr = QHBoxLayout(pw)
                pr.setContentsMargins(0, SPACE_XS, 0, SPACE_XS)
                pr.setSpacing(SPACE_10)
                pl = QLabel(p["name"])
                pl.setStyleSheet(_PLUGIN_NAME_STYLE)
                pr.addWidget(pl, stretch=1)
                bl.addWidget(pw)
                bl.addWidget(_div())
        else:
            no_lbl = QLabel("No plugins assigned")
            no_lbl.setStyleSheet(_NO_PLUGIN_STYLE)
            bl.addWidget(no_lbl)

        bl.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(_SEPARATOR_STYLE)
        lay.addWidget(sep)

        del_btn = ConfirmDeleteButton("Delete", "Sure?")
        del_btn.setFixedHeight(SIZE_CONTROL_MD)
        del_btn.setFixedWidth(SIZE_BTN_W_MD)
        del_btn.set_button_styles(_TEXT_BTN_RED, _TEXT_BTN_RED_CONFIRM)

        def _do_delete():
            try:
                logger.info("camera_manager.delete requested id=%s name=%s", self._cam_id, cam.get("name"))
            except (TypeError, ValueError):
                logger.debug("Failed to log camera delete request id=%s", self._cam_id, exc_info=True)
            self.delete_requested.emit(self._cam_id)

        del_btn.set_confirm_callback(_do_delete)

        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(SIZE_CONTROL_MD)
        close_btn.setFixedWidth(SIZE_BTN_W_80)
        close_btn.setStyleSheet(_TEXT_BTN_GHOST)
        close_btn.clicked.connect(lambda: self.close_requested.emit())

        edit_btn = QPushButton("Edit")
        edit_btn.setFixedHeight(SIZE_CONTROL_MD)
        edit_btn.setFixedWidth(SIZE_BTN_W_80)
        edit_btn.setStyleSheet(_TEXT_BTN_BLUE)
        edit_btn.clicked.connect(self._open_edit)
        lay.addLayout(
            make_manager_footer_layout(
                left_widget=del_btn,
                right_widgets=[close_btn, edit_btn],
                margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
                spacing=SPACE_SM,
            )
        )

    def _make_hero(self, cam: dict, enabled: bool, face_on: bool) -> QFrame:
        hero = QFrame()
        hero.setStyleSheet(_HERO_STYLE)
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(SPACE_20, SPACE_14, SPACE_20, SPACE_14)
        hl.setSpacing(SPACE_14)
        hl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        import cv2 as _cv2
        import numpy as _np_arr

        preview_lbl = QLabel()
        preview_lbl.setFixedSize(SIZE_PREVIEW_W, SIZE_PREVIEW_H)
        preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_lbl.setStyleSheet(
            f"background:{_BG_RAISED}; border:{SPACE_XXXS}px solid {_BORDER};"
            f"border-radius:{RADIUS_MD}px; color:{_TEXT_MUTED}; font-size:{FONT_SIZE_9}px;"
        )
        preview_lbl.setText("no signal")

        _last_frame: list = [None]

        def _on_frame(cid: int, frame: _np_arr.ndarray, _res: dict):
            if cid == cam.get("id"):
                _last_frame[0] = frame

        def _tick():
            f = _last_frame[0]
            if f is None:
                return
            try:
                rgb = _cv2.cvtColor(f, _cv2.COLOR_BGR2RGB)
                h, w = rgb.shape[:2]
                qi = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                scaled = QPixmap.fromImage(qi).scaled(
                    SIZE_PREVIEW_W_INNER,
                    SIZE_PREVIEW_H_INNER,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                preview_lbl.setPixmap(scaled)
                preview_lbl.setText("")
            except (RuntimeError, ValueError, TypeError):
                logger.debug("Failed to render preview frame in edit mode cam_id=%s", cam.get("id"), exc_info=True)

        try:
            _cm = get_camera_manager()
            _thread = _cm.get_thread(cam["id"])
            if _thread and _thread.isRunning():
                _thread.frame_ready.connect(_on_frame)
                _ptimer = QTimer(preview_lbl)
                _ptimer.setInterval(500)
                _ptimer.timeout.connect(_tick)
                _ptimer.start()

                def _cleanup(_obj=None, _t=_thread, _fn=_on_frame, _tm=_ptimer):
                    try:
                        _tm.stop()
                    except Exception:
                        pass
                    try:
                        if hasattr(_t, "frame_ready"):
                            _t.frame_ready.disconnect(_fn)
                    except (RuntimeError, TypeError, AttributeError):
                        logger.debug("Failed to disconnect edit preview frame signal cam_id=%s", cam.get("id"), exc_info=True)

                preview_lbl.destroyed.connect(_cleanup)
        except (ImportError, RuntimeError, OSError):
            logger.warning("Failed to initialize edit preview stream cam_id=%s", cam.get("id"), exc_info=True)

        hl.addWidget(preview_lbl, alignment=Qt.AlignmentFlag.AlignVCenter)

        col = QVBoxLayout()
        col.setSpacing(SPACE_XS)

        nf = QFont()
        safe_set_point_size(nf, FONT_SIZE_SUBHEAD)
        nf.setBold(True)
        nlbl = QLabel(cam.get("name", ""))
        nlbl.setFont(nf)
        nlbl.setStyleSheet(_NAME_LABEL_STYLE)
        col.addWidget(nlbl)

        if cam.get("source"):
            src_lbl = QLabel(cam["source"])
            src_lbl.setStyleSheet(_SOURCE_LABEL_STYLE)
            src_lbl.setWordWrap(True)
            col.addWidget(src_lbl)

        col.addSpacing(SPACE_XS)

        chips = QHBoxLayout()
        chips.setSpacing(SPACE_6)
        sc = _SUCCESS if enabled else _TEXT_MUTED
        sbg = _SUCCESS_BG_14 if enabled else _MUTED_BG_10
        chips.addWidget(_pill("ENABLED" if enabled else "DISABLED", sc, sbg))
        chips.addWidget(
            _pill(
                "FACE ON" if face_on else "FACE OFF",
                _ACCENT_HI if face_on else _TEXT_MUTED,
                _ACCENT_BG_12 if face_on else _MUTED_BG_10,
            )
        )
        try:
            plugins = db.get_camera_plugins(cam["id"])
            if plugins:
                chips.addWidget(
                    _pill(
                        f"{len(plugins)} plugin{'s' if len(plugins) != 1 else ''}",
                        _ACCENT_HI,
                        _ACCENT_BG_12,
                    )
                )
        except (sqlite3.Error, OSError, ValueError):
            logger.debug("Failed to load plugin pills for camera id=%s", cam.get("id"), exc_info=True)
        chips.addStretch()
        col.addLayout(chips)

        hl.addLayout(col, stretch=1)
        return hero

    def _show_edit(self, cam: dict):
        self._clear()
        cam_id = cam["id"]

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        enabled = bool(cam.get("enabled"))
        face_on = bool(cam.get("face_recognition"))
        lay.addWidget(self._make_hero(cam, enabled, face_on))

        name = cam.get("name", "")
        lay.addWidget(make_edit_banner(f"Editing — {name}" if name else "Editing — Camera", self))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("border:none;background:{bg};".format(bg=_BG_SURFACE))
        body = QWidget()
        body.setStyleSheet("background:{bg};".format(bg=_BG_SURFACE))
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, SPACE_XL)
        body_l.setSpacing(0)
        body_l.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

        e_name = QLineEdit(cam.get("name", ""))
        e_name.setFixedHeight(SIZE_SECTION_H)
        e_name.setStyleSheet(_input_ss())
        body_l.addWidget(_srow("Name *", e_name))

        e_source = QLineEdit(cam.get("source", ""))
        e_source.setFixedHeight(SIZE_SECTION_H)
        e_source.setStyleSheet(_input_ss())
        body_l.addWidget(_srow("Source *", e_source))

        e_location = QLineEdit(cam.get("location") or "")
        e_location.setFixedHeight(SIZE_SECTION_H)
        e_location.setStyleSheet(_input_ss())
        body_l.addWidget(_srow("Location", e_location))

        fps_spin = QSpinBox()
        fps_spin.setRange(1, 60)
        fps_spin.setValue(int(cam.get("fps_limit", 30)))
        fps_spin.setStyleSheet(_spin_ss())
        body_l.addWidget(_srow("FPS Limit", fps_spin))

        res_combo = QComboBox()
        res_combo.setFixedHeight(SIZE_SECTION_H)
        res_combo.setStyleSheet(_combo_ss())
        for _r in ["640x480", "1280x720", "1920x1080", "2560x1440", "3840x2160"]:
            res_combo.addItem(_r)
        _cur_res = cam.get("resolution") or "1280x720"
        _ri = res_combo.findText(_cur_res)
        if _ri >= 0:
            res_combo.setCurrentIndex(_ri)
        else:
            res_combo.addItem(_cur_res)
            res_combo.setCurrentIndex(res_combo.count() - 1)
        body_l.addWidget(_srow("Resolution", res_combo))

        def _left(toggle: ToggleSwitch) -> QWidget:
            c = QWidget()
            c.setStyleSheet("background:transparent; border:none;")
            h = QHBoxLayout(c)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            h.addWidget(toggle)
            h.addStretch()
            return c

        enabled_toggle = ToggleSwitch()
        enabled_toggle.setChecked(bool(cam.get("enabled")))
        body_l.addWidget(_srow("Enabled", _left(enabled_toggle)))

        body_l.addSpacing(SPACE_XS)
        body_l.addWidget(_make_sdiv("Face Recognition"))

        try:
            raw_thresh = cam.get("face_similarity_threshold")
            if raw_thresh is None:
                raw_thresh = db.get_setting("face_similarity_threshold", 0.45)
        except (sqlite3.Error, OSError, ValueError):
            raw_thresh = 0.45
        thresh_spin = QSpinBox()
        thresh_spin.setRange(1, 100)
        thresh_spin.setSuffix("%")
        try:
            thresh_spin.setValue(int(float(raw_thresh) * 100))
        except (TypeError, ValueError):
            thresh_spin.setValue(45)
        thresh_spin.setStyleSheet(_spin_ss())
        body_l.addWidget(_srow("Match Threshold", thresh_spin))

        try:
            cur_max = db.get_setting(f"camera_{cam_id}_max_faces", None)
            if cur_max is None:
                cur_max = db.get_setting("max_faces_per_frame", 16) or 16
        except (sqlite3.Error, OSError, ValueError):
            cur_max = 16
        max_faces_spin = QSpinBox()
        max_faces_spin.setRange(1, 256)
        max_faces_spin.setValue(int(cur_max))
        max_faces_spin.setStyleSheet(_spin_ss())
        body_l.addWidget(_srow("Max Faces / Frame", max_faces_spin))

        try:
            cur_min_face = db.get_setting(f"camera_{cam_id}_min_face_size", None)
            if cur_min_face is None:
                cur_min_face = db.get_setting("min_face_size", 24) or 24
        except (sqlite3.Error, OSError, ValueError):
            cur_min_face = 24
        min_face_size_spin = QSpinBox()
        min_face_size_spin.setRange(10, 500)
        min_face_size_spin.setValue(int(cur_min_face))
        min_face_size_spin.setSuffix(" px")
        min_face_size_spin.setStyleSheet(_spin_ss())
        body_l.addWidget(_srow("Min Face Size", min_face_size_spin))

        face_toggle = ToggleSwitch()
        face_toggle.setChecked(bool(cam.get("face_recognition")))
        body_l.addWidget(_srow("Face Recognition", _left(face_toggle)))

        body_l.addSpacing(SPACE_XS)
        body_l.addWidget(_make_sdiv("Plugins"))

        try:
            all_plugins = db.get_plugins()
            assigned_ids = {p["id"] for p in db.get_camera_plugins(cam_id)}
        except (sqlite3.Error, OSError, ValueError):
            all_plugins = []
            assigned_ids = set()

        _down_pix = themed_icon_pixmap("frontend/assets/icons/arrow_down.png", 12, 12)
        _up_pix = themed_icon_pixmap("frontend/assets/icons/arrow_up.png", 12, 12)

        def _expand_icon(is_up: bool) -> QIcon:
            pix = _up_pix if is_up else _down_pix
            if pix.isNull():
                return QIcon()
            return QIcon(pix)

        plugin_class_widgets: dict[int, tuple[dict, list, float]] = {}

        def _persist_plugin_class_overrides(plugin_id: int) -> None:
            if plugin_id not in plugin_class_widgets:
                return
            cw, classes, def_conf = plugin_class_widgets[plugin_id]
            for ci, (cls_d, en_sw, sp_w) in cw.items():
                pcls_id = next((c.get("id") for c in classes if int(c.get("class_index", -1)) == ci), None)
                if pcls_id is None:
                    continue
                u_en = bool(en_sw.isChecked())
                u_c = float(sp_w.value()) / 100.0
                g_en = cls_d.get("enabled") not in (0, "0", False)
                gc = cls_d.get("confidence")
                try:
                    gc = float(gc) if gc is not None else def_conf
                    if gc > 1.0:
                        gc /= 100.0
                except (TypeError, ValueError):
                    gc = def_conf
                try:
                    if u_en == g_en and abs(u_c - gc) < 1e-4:
                        CameraService().remove_class_override(cam_id, pcls_id)
                    else:
                        CameraService().assign_class_override(cam_id, pcls_id, u_en, u_c)
                except (sqlite3.Error, OSError, ValueError):
                    logger.exception("Failed to save class idx %s", ci)

        def _build_classes_panel(plugin_id: int) -> tuple:
            wrap = QWidget()
            wrap.setStyleSheet("background:{bg}; border:none;".format(bg=_BG_RAISED))
            wl = QVBoxLayout(wrap)
            wl.setContentsMargins(0, 0, 0, SPACE_6)
            wl.setSpacing(0)

            try:
                classes = db.get_plugin_classes(plugin_id)
                if not classes:
                    try:
                        from backend.models import model_loader

                        mdl = model_loader.get_loaded_plugins().get(plugin_id)
                        class_map = getattr(mdl, "class_names", {}) if mdl else {}
                        if isinstance(class_map, dict) and class_map:
                            for class_idx, class_name in class_map.items():
                                try:
                                    idx_val = int(class_idx)
                                except (TypeError, ValueError):
                                    continue
                                name_txt = str(class_name).strip() or str(idx_val)
                                db.add_plugin_class(plugin_id, idx_val, name_txt, name_txt)
                            classes = db.get_plugin_classes(plugin_id)
                    except (ImportError, RuntimeError, OSError, ValueError):
                        logger.debug("Failed to hydrate plugin classes for plugin id=%s", plugin_id, exc_info=True)
                overrides = {c["class_index"]: c for c in db.get_camera_plugin_classes(cam_id, plugin_id)}
                pd_row = db.get_plugin(plugin_id)
                def_conf = float(pd_row.get("confidence", 0.5)) if pd_row else 0.5
            except (sqlite3.Error, OSError, ValueError, TypeError):
                classes = []
                overrides = {}
                def_conf = 0.5

            cw: dict[int, tuple] = {}

            if not classes:
                _nl = QLabel("No classes found for this plugin.")
                _nl.setStyleSheet(
                    f"color:{_TEXT_MUTED}; font-size:{FONT_SIZE_CAPTION}px; font-style:italic; padding:{SPACE_SM}px {SPACE_20}px;"
                )
                wl.addWidget(_nl)
            else:
                tbl = QTableWidget(len(classes), 3)
                tbl.setHorizontalHeaderLabels(["", "Class Name", "Conf %"])
                tbl.verticalHeader().setVisible(False)
                tbl.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
                tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                tbl.setFocusPolicy(Qt.FocusPolicy.NoFocus)
                tbl.setAlternatingRowColors(False)
                tbl.setShowGrid(False)
                tbl.setStyleSheet(
                    """
                    QTableWidget {{
                        background: {bg};
                        border: none;
                        color: {text_sec};
                        font-size: {fs_label}px;
                        outline: none;
                    }}
                    QTableWidget::item {{
                        padding: 0 {pad}px;
                        border: none;
                        background: transparent;
                    }}
                    QHeaderView::section {{
                        background: {bg};
                        color: {text_muted};
                        font-size: {fs_caption}px;
                        padding: {pad_y}px {pad}px;
                        border: none;
                    }}
                    """.format(
                        bg=_BG_RAISED,
                        text_sec=_TEXT_SEC,
                        fs_label=FONT_SIZE_LABEL,
                        pad=SPACE_6,
                        text_muted=_TEXT_MUTED,
                        fs_caption=FONT_SIZE_CAPTION,
                        pad_y=SPACE_XS,
                    )
                )
                hdr = tbl.horizontalHeader()
                hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
                hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
                hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
                tbl.setColumnWidth(0, SIZE_TABLE_COL_SM)
                tbl.setColumnWidth(2, SIZE_BTN_W_MD)
                tbl.verticalHeader().setDefaultSectionSize(SIZE_BADGE_H)

                for row_i, cls in enumerate(classes):
                    idx = int(cls.get("class_index", 0))
                    cname = cls.get("class_name", f"Class {idx}")

                    en = ToggleSwitch(width=SIZE_SECTION_H, height=SIZE_CONTROL_18)
                    if idx in overrides and overrides[idx].get("enabled") is not None:
                        en.setChecked(bool(overrides[idx]["enabled"]))
                    else:
                        en.setChecked(cls.get("enabled") not in (0, "0", False))
                    cell0 = QWidget()
                    cell0.setStyleSheet("background:transparent;")
                    h0 = QHBoxLayout(cell0)
                    h0.setContentsMargins(SPACE_14, 0, SPACE_SM, 0)
                    h0.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                    h0.addWidget(en)
                    tbl.setCellWidget(row_i, 0, cell0)

                    it1 = QTableWidgetItem(cname)
                    it1.setForeground(Qt.GlobalColor.white)
                    tbl.setItem(row_i, 1, it1)

                    sp = QSpinBox()
                    sp.setRange(0, 100)
                    sp.setSuffix("%")
                    sp.setFixedWidth(SIZE_BTN_W_SM)
                    sp.setStyleSheet(_spin_ss())
                    if idx in overrides and overrides[idx].get("confidence") is not None:
                        raw = float(overrides[idx]["confidence"])
                    elif cls.get("confidence") is not None:
                        raw = float(cls["confidence"])
                    else:
                        raw = def_conf
                    sp.setValue(int(raw * 100) if raw <= 1.0 else int(raw))
                    cell2 = QWidget()
                    cell2.setStyleSheet("background:transparent;")
                    h2 = QHBoxLayout(cell2)
                    h2.setContentsMargins(0, 0, 0, 0)
                    h2.setAlignment(Qt.AlignmentFlag.AlignVCenter)
                    h2.addWidget(sp)
                    tbl.setCellWidget(row_i, 2, cell2)

                    cw[idx] = (cls, en, sp)

                row_h_total = min(len(classes), 8) * SIZE_BADGE_H
                hdr_h = tbl.horizontalHeader().height() or SIZE_ITEM_SM
                tbl.setFixedHeight(row_h_total + hdr_h + SPACE_XXS)
                wl.addWidget(tbl)

            plugin_class_widgets[plugin_id] = (cw, classes, def_conf)
            return wrap, cw

        plugin_checks: dict[int, ToggleSwitch] = {}
        for p in all_plugins:
            row_w = QWidget()
            row_w.setStyleSheet("background:transparent; border:none;")
            row_h = QHBoxLayout(row_w)
            row_h.setContentsMargins(0, 0, 0, 0)
            row_h.setSpacing(SPACE_SM)

            ts = ToggleSwitch()
            ts.setChecked(p["id"] in assigned_ids)
            row_h.addWidget(ts)
            row_h.addStretch()

            expand_btn = QPushButton()
            expand_btn.setFixedSize(SIZE_ITEM_SM, SIZE_ITEM_SM)
            expand_btn.setCheckable(True)
            expand_btn.setEnabled(p["id"] in assigned_ids)
            expand_btn.setIcon(_expand_icon(False))
            expand_btn.setStyleSheet(
                """
                QPushButton {{
                    background:{bg}; border:{bw}px solid {border};
                    border-radius:{radius}px; padding:0;
                }}
                QPushButton:hover  {{border-color:{accent};}}
                QPushButton:checked{{
                    background:{accent_bg};
                    border-color:{accent};
                }}
                """.format(
                    bg=_BG_RAISED,
                    bw=SPACE_XXXS,
                    border=_BORDER,
                    radius=RADIUS_5,
                    accent=_ACCENT,
                    accent_bg=_ACCENT_BG_15,
                )
            )
            row_h.addWidget(expand_btn)
            body_l.addWidget(_srow(p["name"], row_w))

            cls_panel, _cls_wgts = _build_classes_panel(p["id"])
            cls_panel.setVisible(False)
            body_l.addWidget(cls_panel)

            def _toggle_cls(checked, panel=cls_panel, btn=expand_btn):
                panel.setVisible(checked)
                btn.setIcon(_expand_icon(checked))

            expand_btn.toggled.connect(_toggle_cls)
            ts.toggled.connect(
                lambda checked, btn=expand_btn, panel=cls_panel: (
                    btn.setEnabled(checked),
                    panel.setVisible(panel.isVisible() and checked),
                    btn.setChecked(btn.isChecked() and checked),
                )
            )
            plugin_checks[p["id"]] = ts

        body_l.addStretch()

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(_SEPARATOR_STYLE)
        lay.addWidget(sep)

        del_btn_edit = ConfirmDeleteButton("Delete", "Sure?")
        del_btn_edit.setFixedHeight(SIZE_CONTROL_MD)
        del_btn_edit.setFixedWidth(SIZE_BTN_W_MD)
        del_btn_edit.set_button_styles(_TEXT_BTN_RED, _TEXT_BTN_RED_CONFIRM)

        def _do_delete_edit():
            try:
                logger.info("camera_manager.delete requested (edit) id=%s name=%s", self._cam_id, cam.get("name"))
            except (TypeError, ValueError):
                logger.debug("Failed to log edit delete request id=%s", self._cam_id, exc_info=True)
            self.delete_requested.emit(self._cam_id)

        del_btn_edit.set_confirm_callback(_do_delete_edit)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(SIZE_CONTROL_MD)
        cancel_btn.setFixedWidth(SIZE_BTN_W_80)
        cancel_btn.setStyleSheet(_TEXT_BTN_GHOST)
        cancel_btn.clicked.connect(lambda: self.load_camera(db.get_camera(cam_id) or cam))

        save_btn = QPushButton("Save")
        save_btn.setFixedHeight(SIZE_CONTROL_MD)
        save_btn.setFixedWidth(SIZE_BTN_W_80)
        save_btn.setStyleSheet(_TEXT_BTN_BLUE)

        def _do_save():
            name = e_name.text().strip()
            source = e_source.text().strip()
            logger.info("camera_manager.edit save start id=%s name=%s source=%s", cam_id, name, source)
            if not name or not source:
                logger.warning("Camera save skipped: name/source required.")
                return
            try:
                db.update_camera(
                    cam_id,
                    name=name,
                    source=source,
                    location=e_location.text().strip(),
                    resolution=res_combo.currentText(),
                    fps_limit=fps_spin.value(),
                    enabled=1 if enabled_toggle.isChecked() else 0,
                    face_recognition=1 if face_toggle.isChecked() else 0,
                    face_similarity_threshold=(thresh_spin.value() / 100.0),
                )
            except (sqlite3.Error, OSError, ValueError):
                logger.exception("camera_manager.edit save failed id=%s name=%s", cam_id, name)
                return
            try:
                db.set_setting(f"camera_{cam_id}_max_faces", int(max_faces_spin.value()))
            except (sqlite3.Error, OSError, ValueError):
                logger.warning("Failed to persist max faces setting for camera id=%s", cam_id, exc_info=True)
            try:
                db.set_setting(f"camera_{cam_id}_min_face_size", int(min_face_size_spin.value()))
            except (sqlite3.Error, OSError, ValueError):
                logger.warning("Failed to persist min face size setting for camera id=%s", cam_id, exc_info=True)
            for pid, cb in plugin_checks.items():
                try:
                    if cb.isChecked():
                        db.assign_plugin_to_camera(cam_id, pid)
                    else:
                        db.unassign_plugin_from_camera(cam_id, pid)
                except (sqlite3.Error, OSError, ValueError):
                    logger.exception("Failed to assign/unassign plugin %s", pid)
            try:
                db.set_setting(f"camera_{cam_id}_plugins_explicit", True)
            except (sqlite3.Error, OSError, ValueError):
                logger.warning("Failed to persist explicit plugin mode for camera id=%s", cam_id, exc_info=True)
            for pid, cb in plugin_checks.items():
                if not cb.isChecked():
                    continue
                _persist_plugin_class_overrides(pid)
            try:
                notify_plugins_changed()
            except (RuntimeError, OSError):
                logger.warning("Failed to notify plugin changes after camera save", exc_info=True)
            try:
                cm = get_camera_manager()
                if enabled_toggle.isChecked():
                    cm.start_camera(cam_id)
                else:
                    cm.stop_camera(cam_id)
            except (ImportError, RuntimeError, OSError):
                logger.warning("Failed to apply camera runtime state cam_id=%s", cam_id, exc_info=True)
            logger.info(
                "camera_manager.edit save success id=%s name=%s enabled=%s face_on=%s",
                cam_id,
                name,
                enabled_toggle.isChecked(),
                face_toggle.isChecked(),
            )
            self.saved.emit()

        save_btn.clicked.connect(_do_save)
        lay.addLayout(
            make_manager_footer_layout(
                left_widget=del_btn_edit,
                right_widgets=[cancel_btn, save_btn],
                margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
                spacing=SPACE_SM,
            )
        )

    def _open_edit(self):
        if self._cam is None:
            return
        try:
            logger.info("camera_manager.edit open id=%s name=%s", self._cam.get("id"), self._cam.get("name"))
        except (TypeError, ValueError):
            logger.debug("Failed to log edit open metadata", exc_info=True)
        self._show_edit(self._cam)

