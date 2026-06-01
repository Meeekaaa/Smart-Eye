import contextlib
import logging
from typing import ClassVar

import cv2
from PySide6.QtCore import Qt, QRect, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend.app_theme import safe_set_point_size
from frontend.styles._colors import (
    _ACCENT_BORDER,
    _ACCENT_GRAD_END,
    _ACCENT_GRAD_START,
    _ACCENT_GRAD_V_HOVER_END,
    _ACCENT_GRAD_V_HOVER_START,
    _ACCENT_HI,
    _ACCENT_PRESSED_ALT,
    _BG_OVERLAY,
    _BG_RAISED,
    _BG_SURFACE,
    _BORDER,
    _BORDER_DARK,
    _BORDER_DIM,
    _BLACK,
    _DANGER_DIM,
    _DANGER_GRAD_ALT_END,
    _DANGER_GRAD_ALT_START,
    _DANGER_GRAD_END,
    _DANGER_GRAD_PRESSED_END,
    _DANGER_GRAD_START,
    _SUCCESS,
    _SUCCESS_BG_12,
    _SUCCESS_DIM,
    _SUCCESS_GRAD_START,
    _SUCCESS_PRESSED_ALT,
    _TEXT_MUTED,
    _TEXT_ON_ACCENT,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_MD,
    RADIUS_SM,
    SIZE_BTN_W_70,
    SIZE_BTN_W_MD,
    SIZE_CONTROL_MD,
    SIZE_FIELD_W,
    SIZE_HEADER_H,
    SIZE_PANEL_W_MD,
    SPACE_10,
    SPACE_14,
    SPACE_6,
    SPACE_SM,
    SPACE_XS,
    SPACE_XXS,
    SPACE_XXXS,
)
from frontend.styles.page_styles import muted_label_style, text_style

_BTN_BLUE = f"""
QPushButton {{
    border: {SPACE_XXXS}px solid {_ACCENT_BORDER};
    border-radius: {RADIUS_MD}px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {_ACCENT_GRAD_START},stop:1 {_ACCENT_GRAD_END});
    color: {_TEXT_ON_ACCENT};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    font-size: {FONT_SIZE_LABEL}px;
    padding: 0 {SPACE_14}px;
}}
QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {_ACCENT_GRAD_V_HOVER_START},stop:1 {_ACCENT_GRAD_V_HOVER_END}); }}
QPushButton:pressed {{ background: {_ACCENT_PRESSED_ALT}; }}
QPushButton:disabled {{ background: {_BORDER_DIM}; color: {_TEXT_MUTED}; border-color: {_BORDER_DARK}; }}
"""

_BTN_RED = f"""
QPushButton {{
    border: {SPACE_XXXS}px solid {_DANGER_DIM};
    border-radius: {RADIUS_MD}px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {_DANGER_GRAD_ALT_START},stop:1 {_DANGER_GRAD_ALT_END});
    color: {_TEXT_ON_ACCENT};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    font-size: {FONT_SIZE_LABEL}px;
    padding: 0 {SPACE_14}px;
}}
QPushButton:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {_DANGER_GRAD_START},stop:1 {_DANGER_GRAD_END}); }}
QPushButton:pressed {{ background: {_DANGER_GRAD_PRESSED_END}; }}
QPushButton:disabled {{ background: {_BORDER_DIM}; color: {_TEXT_MUTED}; border-color: {_BORDER_DARK}; }}
"""

_BTN_SEC = f"""
QPushButton {{
    border: {SPACE_XXXS}px solid {_BORDER_DARK};
    border-radius: {RADIUS_MD}px;
    background: {_BORDER_DIM};
    color: {_TEXT_SEC};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    font-size: {FONT_SIZE_LABEL}px;
    padding: 0 {SPACE_14}px;
}}
QPushButton:hover {{ background: {_BORDER}; color: {_TEXT_PRI}; }}
QPushButton:pressed {{ background: {_BG_RAISED}; }}
QPushButton:disabled {{ background: {_BORDER_DIM}; color: {_TEXT_MUTED}; border-color: {_BORDER_DARK}; }}
"""

_BTN_AUTO_ON = f"""
QPushButton {{
    border: {SPACE_XXXS}px solid {_SUCCESS_DIM};
    border-radius: {RADIUS_MD}px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {_SUCCESS_GRAD_START},stop:1 {_SUCCESS_DIM});
    color: {_TEXT_ON_ACCENT};
    font-weight: {FONT_WEIGHT_SEMIBOLD};
    font-size: {FONT_SIZE_LABEL}px;
    padding: 0 {SPACE_14}px;
}}
QPushButton:hover {{ background: {_SUCCESS}; }}
QPushButton:pressed {{ background: {_SUCCESS_PRESSED_ALT}; }}
"""

_AUTO_CAPTURE_FRAMES = 45
logger = logging.getLogger(__name__)


class FaceCaptureWidget(QWidget):
    capture_complete = Signal(list)

    POSES: ClassVar[tuple[str, ...]] = ("Front", "Turn Left", "Turn Right", "Look Up")
    POSE_HINTS: ClassVar[tuple[str, ...]] = (
        "Face the camera straight on",
        "Slowly turn your head to the left",
        "Slowly turn your head to the right",
        "Tilt your head slightly upward",
    )

    def __init__(self, parent=None):
        super().__init__(parent)
        self._captures = []
        self._current_pose = 0
        self._cap = None
        self._last_frame = None
        self._flash_counter = 0
        self._using_shared = False

        self._auto_mode = False
        self._face_lock_frames = 0
        self._cascade = None
        self._auto_capture_taken = False
        self._detect_cache = (False, False, "")
        self._detect_skip = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_preview)
        self._setui()

    def _setui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(SPACE_10)

        left = QVBoxLayout()
        left.setSpacing(SPACE_6)

        self._preview_label = QLabel()
        self._preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_label.setMinimumSize(380, 280)
        self._preview_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._preview_label.setStyleSheet(
            f"background-color: {_BG_SURFACE}; border-radius: {RADIUS_SM}px;"
            f" border: {SPACE_XXXS}px solid {_BORDER_DIM}; color: {_TEXT_MUTED}; font-size: {FONT_SIZE_BODY}px;"
        )
        self._preview_label.setText("Starting camera...")
        left.addWidget(self._preview_label, stretch=1)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(0, SPACE_XS, 0, 0)
        info_row.setSpacing(SPACE_SM)
        self._instruction_label = QLabel(self.POSES[0])
        inst_font = QFont()
        safe_set_point_size(inst_font, 11)
        inst_font.setBold(True)
        self._instruction_label.setFont(inst_font)
        self._instruction_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self._instruction_label.setStyleSheet(text_style(_ACCENT_HI, extra=f"background: transparent; padding: {SPACE_XXS}px;"))
        info_row.addStretch(1)

        self._status_label = QLabel("● Camera Off")
        self._status_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)
        self._status_label.setStyleSheet(muted_label_style(size=FONT_SIZE_LABEL) + " background: transparent;")
        info_row.addWidget(self._status_label)
        left.addLayout(info_row)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, SPACE_6, 0, SPACE_SM)
        action_row.setSpacing(SPACE_SM)

        self._load_file_btn = QPushButton("Load File")
        self._load_file_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._load_file_btn.setMinimumWidth(SIZE_BTN_W_70)
        self._load_file_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._load_file_btn.setStyleSheet(_BTN_BLUE)
        self._load_file_btn.clicked.connect(self._load_image_file)
        action_row.addWidget(self._load_file_btn)

        self._auto_btn = QPushButton("Auto")
        self._auto_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._auto_btn.setMinimumWidth(SIZE_BTN_W_70)
        self._auto_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._auto_btn.setStyleSheet(_BTN_BLUE)
        self._auto_btn.setToolTip("Auto-capture: align your face to the oval matching each pose")
        self._auto_btn.clicked.connect(self._toggle_auto)
        action_row.addWidget(self._auto_btn)

        sep = QLabel("|")
        sep.setStyleSheet("color: {c}; background: transparent; padding: 0 {pad}px;".format(c=_BORDER, pad=SPACE_XXS))
        action_row.addWidget(sep)

        self._capture_btn = QPushButton("Capture")
        self._capture_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._capture_btn.setMinimumWidth(SIZE_BTN_W_70)
        self._capture_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._capture_btn.setEnabled(False)
        self._capture_btn.setStyleSheet(_BTN_BLUE)
        self._capture_btn.clicked.connect(self._do_capture)
        action_row.addWidget(self._capture_btn)

        self._reset_btn = QPushButton("Reset")
        self._reset_btn.setFixedHeight(SIZE_CONTROL_MD)
        self._reset_btn.setMinimumWidth(SIZE_BTN_W_70)
        self._reset_btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._reset_btn.setStyleSheet(_BTN_RED)
        self._reset_btn.clicked.connect(self.reset)
        action_row.addWidget(self._reset_btn)
        self._action_row = action_row
        left.addLayout(action_row)

        content.addLayout(left, stretch=3)

        right_frame = QFrame()
        right_frame.setObjectName("thumbPanel")
        right_frame.setFixedWidth(SIZE_PANEL_W_MD)
        right_frame.setStyleSheet("""
            QFrame#thumbPanel {{
                background-color: {bg};
                border: {bw}px solid {border};
                border-radius: {radius}px;
            }}
        """.format(bg=_BG_RAISED, bw=SPACE_XXXS, border=_BORDER_DIM, radius=RADIUS_SM))
        right = QVBoxLayout(right_frame)
        right.setContentsMargins(SPACE_10, SPACE_10, SPACE_10, SPACE_10)
        right.setSpacing(SPACE_SM)

        prog_lbl = QLabel("Captured Photos")
        prog_lbl.setStyleSheet(
            f"font-weight: {FONT_WEIGHT_SEMIBOLD}; font-size: {FONT_SIZE_LABEL}px; color: {_TEXT_PRI}; background: transparent;"
        )
        right.addWidget(prog_lbl)
        self._progress_label = QLabel("0 / 4 captured")
        self._progress_label.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_CAPTION, extra="background: transparent;"))
        right.addWidget(self._progress_label)

        self._thumb_labels = []
        for i in range(4):
            thumb_frame = QFrame()
            thumb_frame.setStyleSheet("""
                QFrame {{
                    background-color: {bg};
                    border: {bw}px solid {border};
                    border-radius: {radius}px;
                }}
            """.format(bg=_BG_OVERLAY, bw=SPACE_XXXS, border=_BORDER_DIM, radius=RADIUS_SM))
            thumb_frame.setFixedSize(SIZE_FIELD_W, SIZE_BTN_W_MD)
            thumb_layout = QVBoxLayout(thumb_frame)
            thumb_layout.setContentsMargins(SPACE_XS, SPACE_XS, SPACE_XS, SPACE_XS)
            thumb_layout.setSpacing(SPACE_XXS)
            thumb = QLabel()
            thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_CAPTION, extra="background: transparent; border: none;"))
            thumb.setText(self.POSES[i])
            thumb.setFixedHeight(SIZE_HEADER_H)
            thumb_layout.addWidget(thumb)
            pose_lbl = QLabel(f"Step {i + 1}: {self.POSES[i]}")
            pose_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_MICRO) + " background: transparent; border: none;")
            pose_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            thumb_layout.addWidget(pose_lbl)
            right.addWidget(thumb_frame)
            self._thumb_labels.append(thumb)
        right.addStretch()
        content.addWidget(right_frame, stretch=1)

        root.addLayout(content, stretch=1)

    def _toggle_auto(self):
        self._auto_mode = not self._auto_mode
        self._face_lock_frames = 0
        self._auto_capture_taken = False
        self._detect_cache = (False, False, "")
        self._detect_skip = 0
        if self._auto_mode:
            self._auto_btn.setText("Auto: On")
            self._auto_btn.setStyleSheet(_BTN_RED)
        else:
            self._auto_btn.setText("Auto")
            self._auto_btn.setStyleSheet(_BTN_BLUE)

    def _get_cascade(self):
        if self._cascade is None:
            with contextlib.suppress(Exception):
                path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
                clf = cv2.CascadeClassifier(path)
                if not clf.empty():
                    self._cascade = clf
        return self._cascade

    def _get_eye_cascade(self):
        if not hasattr(self, "_eye_cascade"):
            self._eye_cascade = None
            with contextlib.suppress(Exception):
                path = cv2.data.haarcascades + "haarcascade_eye.xml"
                clf = cv2.CascadeClassifier(path)
                if not clf.empty():
                    self._eye_cascade = clf
        return self._eye_cascade

    def _estimate_head_pose(self, gray_full, face_rect):
        fx, fy, fw, fh = face_rect
        roi_h = int(fh * 0.55)
        face_roi = gray_full[fy : fy + roi_h, fx : fx + fw]
        eye_clf = self._get_eye_cascade()
        if eye_clf is None:
            return "Front"
        min_eye = max(12, int(fw * 0.12))
        eyes = eye_clf.detectMultiScale(face_roi, 1.1, 3, minSize=(min_eye, min_eye))
        if len(eyes) == 0:
            return "Look Up"
        eye_xs = [(ex + ew / 2) / fw for (ex, ey, ew, eh) in eyes]
        if len(eyes) >= 2:
            sorted_x = sorted(eye_xs)
            avg_x = sum(sorted_x) / len(sorted_x)
            spread = sorted_x[-1] - sorted_x[0]
            if spread < 0.22:
                if avg_x < 0.44:
                    return "Turn Left"
                elif avg_x > 0.56:
                    return "Turn Right"
                else:
                    return "Front"
            else:
                if 0.30 <= avg_x <= 0.70:
                    return "Front"
                elif avg_x < 0.30:
                    return "Turn Left"
                else:
                    return "Turn Right"
        else:
            ex = eye_xs[0]
            if ex < 0.40:
                return "Turn Left"
            elif ex > 0.60:
                return "Turn Right"
            else:
                return "Front"

    def _detect_pose_match(self, frame, target_pose, oval_cx_n, oval_cy_n, oval_rx_n, oval_ry_n):
        clf = self._get_cascade()
        if clf is None:
            return False, False, ""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=4, minSize=(60, 60))
        if not len(faces):
            return False, False, ""
        h_frame, w_frame = frame.shape[:2]
        for fx, fy, fw, fh in faces:
            cx = (fx + fw / 2) / w_frame
            cy = (fy + fh / 2) / h_frame
            dx = (cx - oval_cx_n) / oval_rx_n
            dy = (cy - oval_cy_n) / oval_ry_n
            if dx * dx + dy * dy <= 1.0:
                pose = self._estimate_head_pose(gray, (fx, fy, fw, fh))
                return True, (pose == target_pose), pose
        return False, False, ""

    def showEvent(self, event):
        super().showEvent(event)
        if self._cap is None and not self._using_shared:
            self.start_camera(0)

    def _toggle_camera(self):
        if self._cap is not None or self._using_shared:
            self.stop_camera()
        else:
            self.start_camera(0)

    def start_camera(self, source=0):
        if self._cap is not None or self._using_shared:
            self.stop_camera()

        try:
            from backend.camera.camera_manager import get_camera_manager

            mgr = get_camera_manager()
            for cam_id in mgr.get_active_ids():
                thread = mgr.get_thread(cam_id)
                if thread is None:
                    continue
                try:
                    thread_src = int(thread._source) if str(thread._source).isdigit() else thread._source
                except (TypeError, ValueError):
                    thread_src = thread._source
                if thread_src == source or str(thread._source) == str(source):
                    thread.frame_ready.connect(self._on_shared_frame)
                    self._using_shared = True
                    self._shared_camera_id = cam_id
                    self._timer.stop()
                    self._status_label.setText("● Live (shared)")
                    self._status_label.setStyleSheet(text_style(_SUCCESS, size=FONT_SIZE_LABEL, extra="background: transparent;"))
                    self._capture_btn.setEnabled(self._current_pose < 4)
                    self._preview_label.setStyleSheet(
                        f"background-color: {_BLACK}; border-radius: {RADIUS_SM}px; border: {SPACE_XXXS}px solid {_SUCCESS_DIM};"
                    )
                    return
        except (ImportError, RuntimeError, OSError):
            logger.debug("Shared camera lookup failed for source=%s", source, exc_info=True)

        backends = [cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY]
        cap = None
        for backend in backends:
            try:
                c = cv2.VideoCapture(source, backend)
                if c and c.isOpened():
                    cap = c
                    break
                if c:
                    c.release()
            except (RuntimeError, OSError):
                pass
        if cap is None:
            with contextlib.suppress(Exception):
                cap = cv2.VideoCapture(source)
        if cap is None or not cap.isOpened():
            self._status_label.setText("Camera not found")
            self._status_label.setStyleSheet(text_style(_DANGER_DIM, size=FONT_SIZE_LABEL, extra="background: transparent;"))
            QMessageBox.warning(self, "Camera Error", f"Could not open camera {source}.\nTry using 'Load from File' instead.")
            return
        self._cap = cap
        self._timer.start(30)
        self._status_label.setText("● Live")
        self._status_label.setStyleSheet(text_style(_SUCCESS, size=FONT_SIZE_LABEL, extra="background: transparent;"))
        self._capture_btn.setEnabled(self._current_pose < 4)
        self._preview_label.setStyleSheet(
            f"background-color: {_BLACK}; border-radius: {RADIUS_SM}px; border: {SPACE_XXXS}px solid {_SUCCESS_DIM};"
        )

    def _on_shared_frame(self, camera_id, frame, state):
        if not self._using_shared:
            return
        self._last_frame = frame.copy()
        self._render_frame(frame)
        if self._flash_counter > 0:
            self._flash_counter -= 1

    def stop_camera(self):
        if self._using_shared:
            try:
                from backend.camera.camera_manager import get_camera_manager

                thread = get_camera_manager().get_thread(self._shared_camera_id)
                if thread:
                    with contextlib.suppress(Exception):
                        thread.frame_ready.disconnect(self._on_shared_frame)
            except (ImportError, RuntimeError, OSError):
                logger.debug("Failed to detach shared frame handler", exc_info=True)
            self._using_shared = False
            self._shared_camera_id = None

        self._timer.stop()
        if self._cap:
            self._cap.release()
            self._cap = None

        self._face_lock_frames = 0
        self._auto_capture_taken = False
        self._detect_cache = (False, False, "")
        self._detect_skip = 0
        self._status_label.setText("● Camera Off")
        self._status_label.setStyleSheet(muted_label_style(size=FONT_SIZE_LABEL) + " background: transparent;")
        if self._current_pose < 4:
            self._capture_btn.setEnabled(False)
        if self._last_frame is None:
            self._preview_label.setText("Camera not available")
            self._preview_label.setStyleSheet(
                f"background-color: {_BG_SURFACE}; border-radius: {RADIUS_SM}px; border: {SPACE_XXXS}px solid {_BORDER_DIM}; color: {_TEXT_MUTED}; font-size: {FONT_SIZE_BODY}px;"
            )

    def _update_preview(self):
        if self._cap and self._cap.isOpened():
            ret, frame = self._cap.read()
            if ret:
                self._last_frame = frame.copy()
                self._render_frame(frame)
        if self._flash_counter > 0:
            self._flash_counter -= 1

    def _render_frame(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        if self._flash_counter > 0:
            overlay = rgb.copy()
            overlay[:] = [255, 255, 255]
            alpha = self._flash_counter / 5.0
            rgb = cv2.addWeighted(overlay, alpha * 0.5, rgb, 1 - alpha * 0.5, 0)

        h, w, ch = rgb.shape
        qimg = QImage(rgb.data.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        lw = self._preview_label.width()
        lh = self._preview_label.height()
        scaled = pixmap.scaled(lw, lh, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        sw, sh = scaled.width(), scaled.height()

        OCX, OCY = 0.50, 0.48
        ORX, ORY = 0.25, 0.38
        cx_px = int(OCX * sw)
        cy_px = int(OCY * sh)
        rx_px = int(ORX * sw)
        ry_px = int(ORY * sh)

        face_inside = False
        countdown_ratio = 0.0
        detected_pose = ""
        pose_matches = False
        if self._auto_mode and self._current_pose < 4:
            self._detect_skip = (self._detect_skip + 1) % 6
            if self._detect_skip == 0:
                self._detect_cache = self._detect_pose_match(frame, self.POSES[self._current_pose], OCX, OCY, ORX * 2.2, ORY * 2.2)
            face_inside, pose_matches, detected_pose = self._detect_cache
            if face_inside and pose_matches:
                self._face_lock_frames += 1
                self._auto_capture_taken = False
            else:
                self._face_lock_frames = max(0, self._face_lock_frames - 2)
            countdown_ratio = min(1.0, self._face_lock_frames / _AUTO_CAPTURE_FRAMES)
            if self._face_lock_frames >= _AUTO_CAPTURE_FRAMES and not self._auto_capture_taken:
                self._auto_capture_taken = True
                self._face_lock_frames = 0
                self._do_capture()
                return

        painter = QPainter(scaled)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        vignette_path = QPainterPath()
        vignette_path.setFillRule(Qt.FillRule.OddEvenFill)
        vignette_path.addRect(0, 0, sw, sh)
        vignette_path.addEllipse(cx_px - rx_px, cy_px - ry_px, rx_px * 2, ry_px * 2)
        painter.fillPath(vignette_path, QColor(0, 0, 0, 120))

        if not self._auto_mode:
            border_color = QColor(88, 166, 255, 200)
            border_w = 2
        elif countdown_ratio >= 1.0:
            border_color = QColor(63, 185, 80, 255)
            border_w = 4
        elif face_inside and pose_matches:
            r = int(255 - countdown_ratio * (255 - 63))
            g = int(140 + countdown_ratio * (185 - 140))
            b = 0
            border_color = QColor(r, g, b, 220)
            border_w = 3
        elif face_inside and not pose_matches:
            border_color = QColor(255, 165, 0, 200)
            border_w = 2
        else:
            border_color = QColor(220, 80, 80, 180)
            border_w = 2

        painter.setPen(QPen(border_color, border_w))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(cx_px - rx_px, cy_px - ry_px, rx_px * 2, ry_px * 2)

        if self._auto_mode and countdown_ratio > 0:
            arc_pen = QPen(QColor(63, 185, 80, 210), 4)
            arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(arc_pen)
            margin = 6
            span = int(countdown_ratio * 360 * 16)
            painter.drawArc(
                cx_px - rx_px - margin,
                cy_px - ry_px - margin,
                (rx_px + margin) * 2,
                (ry_px + margin) * 2,
                90 * 16,
                -span,
            )

        if self._current_pose < 4:
            font_step = QFont()
            font_step.setPixelSize(14)
            font_step.setBold(True)
            painter.setFont(font_step)
            painter.setPen(QPen(QColor(88, 166, 255, 220), 1))
            step_text = f"Step {self._current_pose + 1} / 4 — {self.POSES[self._current_pose]}"
            painter.drawText(QRect(0, cy_px - ry_px - 30, sw, 24), Qt.AlignmentFlag.AlignHCenter, step_text)

            font_hint = QFont()
            font_hint.setPixelSize(13)
            painter.setFont(font_hint)
            painter.setPen(QPen(QColor(230, 237, 243, 210), 1))
            if self._auto_mode:
                if countdown_ratio >= 1.0:
                    hint = "Hold still…"
                elif face_inside and pose_matches:
                    secs = ((1.0 - countdown_ratio) * _AUTO_CAPTURE_FRAMES) / 30.0
                    hint = f"Hold still — {secs:.1f}s"
                elif face_inside and detected_pose:
                    hint = f"Detected: {detected_pose}  →  need: {self.POSES[self._current_pose]}"
                else:
                    hint = self.POSE_HINTS[self._current_pose]
            else:
                hint = self.POSE_HINTS[self._current_pose]
            painter.drawText(QRect(0, cy_px + ry_px + 10, sw, 24), Qt.AlignmentFlag.AlignHCenter, hint)

        painter.end()
        self._preview_label.setPixmap(scaled)

    def _do_capture(self):
        if self._current_pose >= 4:
            return
        frame = None
        if self._cap and self._cap.isOpened():
            ret, f = self._cap.read()
            if ret:
                frame = f.copy()
        if frame is None and self._last_frame is not None:
            frame = self._last_frame.copy()
        if frame is None:
            QMessageBox.warning(self, "Capture Failed", "No frame available. Make sure camera is running.")
            return
        self._captures.append(frame)
        self._flash_counter = 5
        self._face_lock_frames = 0
        self._auto_capture_taken = False

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        thumb = pixmap.scaled(132, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._thumb_labels[self._current_pose].setPixmap(thumb)
        self._thumb_labels[self._current_pose].parent().setStyleSheet(
            f"background-color: {_SUCCESS_BG_12}; border: {SPACE_XXXS}px solid {_SUCCESS_DIM}; border-radius: {RADIUS_SM}px;"
        )
        self._current_pose += 1
        self._progress_label.setText(f"{self._current_pose} / 4 captured")
        if self._current_pose < 4:
            self._instruction_label.setText(self.POSES[self._current_pose])
        else:
            self._instruction_label.setText("All done!")
            self._instruction_label.setStyleSheet(text_style(_SUCCESS, extra=f"background: transparent; padding: {SPACE_XS}px;"))
            self._capture_btn.setEnabled(False)
            self.stop_camera()
            self.capture_complete.emit(self._captures)

    def _load_image_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select Face Image", "", "Images (*.jpg *.jpeg *.png *.bmp)")
        if not path:
            return
        frame = cv2.imread(path)
        if frame is None:
            QMessageBox.warning(self, "Error", "Could not load selected image.")
            return
        if self._current_pose >= 4:
            QMessageBox.information(self, "Full", "All 4 captures already taken. Reset to start over.")
            return
        self._captures.append(frame)
        self._last_frame = frame.copy()
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data.tobytes(), w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg)
        thumb = pixmap.scaled(132, 68, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._thumb_labels[self._current_pose].setPixmap(thumb)
        self._thumb_labels[self._current_pose].parent().setStyleSheet(
            f"background-color: {_SUCCESS_BG_12}; border: {SPACE_XXXS}px solid {_SUCCESS_DIM}; border-radius: {RADIUS_SM}px;"
        )
        scaled = pixmap.scaled(self._preview_label.size(), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        self._preview_label.setPixmap(scaled)
        self._current_pose += 1
        self._progress_label.setText(f"{self._current_pose} / 4 captured")
        if self._current_pose < 4:
            self._instruction_label.setText(self.POSES[self._current_pose])
            self._capture_btn.setEnabled(self._cap is not None or self._using_shared)
        else:
            self._instruction_label.setText("All done!")
            self._instruction_label.setStyleSheet(text_style(_SUCCESS, extra=f"background: transparent; padding: {SPACE_XS}px;"))
            self._capture_btn.setEnabled(False)
            self.capture_complete.emit(self._captures)

    def reset(self):
        self._captures.clear()
        self._current_pose = 0
        self._flash_counter = 0
        self._face_lock_frames = 0
        self._auto_capture_taken = False
        self._detect_cache = (False, False, "")
        self._detect_skip = 0
        self._instruction_label.setText(self.POSES[0])
        self._instruction_label.setStyleSheet(text_style(_ACCENT_HI, extra=f"background: transparent; padding: {SPACE_XS}px;"))
        self._progress_label.setText("0 / 4 captured")
        camera_active = self._cap is not None or self._using_shared
        self._capture_btn.setEnabled(camera_active)
        for i, thumb in enumerate(self._thumb_labels):
            thumb.clear()
            thumb.setText(self.POSES[i])
            thumb.parent().setStyleSheet(
                f"background-color: {_BG_OVERLAY}; border: {SPACE_XXXS}px solid {_BORDER_DIM}; border-radius: {RADIUS_SM}px;"
            )
        if not camera_active:
            self._preview_label.clear()
            self._preview_label.setText("Restarting camera...")
            self._preview_label.setStyleSheet(
                f"background-color: {_BG_SURFACE}; border-radius: {RADIUS_SM}px; border: {SPACE_XXXS}px solid {_BORDER_DIM}; color: {_TEXT_MUTED}; font-size: {FONT_SIZE_BODY}px;"
            )
            self.start_camera(0)

    def prepend_buttons(self, buttons: list):
        sep = QLabel("|")
        sep.setStyleSheet("color: {c}; background: transparent; padding: 0 {pad}px;".format(c=_BORDER, pad=SPACE_XS))
        for i, btn in enumerate(buttons):
            self._action_row.insertWidget(1 + i, btn)
        self._action_row.insertWidget(1 + len(buttons), sep)

    def get_captures(self):
        return list(self._captures)
