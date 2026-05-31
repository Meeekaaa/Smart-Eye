from __future__ import annotations

import logging
import math
import os
import random

from PySide6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.dialogs import apply_popup_theme
from frontend.widgets.password_visibility import attach_password_visibility_toggle
from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_HI,
    _ACCENT_HI_BG_03,
    _BG_RAISED,
    _BORDER_DIM,
    _DANGER,
    _DANGER_BORDER_SOFT,
    _DANGER_DIM,
    _DB_ACCENT_DARK,
    _DB_AXIS,
    _DB_BG_GRAD_1,
    _DB_BG_GRAD_2,
    _DB_BG_GRAD_3,
    _DB_CANCEL_BG,
    _DB_CANCEL_BG_ALT,
    _DB_DANGER_DARK,
    _DB_GRID,
    _DB_NEUTRAL,
    _DB_SHEEN_1,
    _DB_SHEEN_2,
    _DB_SHEEN_3,
    _DB_VG_0,
    _DB_VG_0_HOVER,
    _DB_VG_1,
    _DB_VG_1_HOVER,
    _DB_VG_2,
    _DB_WARNING_DARK,
    _TEXT_DIM,
    _TEXT_MUTED,
    _TEXT_ON_ACCENT,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_SOFT,
    _WARNING,
)
from frontend.ui_tokens import (
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_DISPLAY,
    FONT_SIZE_HEADING,
    FONT_SIZE_LABEL,
    FONT_SIZE_MICRO,
    FONT_SIZE_TINY,
    FONT_SIZE_XL,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_NORMAL,
    SIZE_BTN_W_80,
    SIZE_FIELD_W,
    SIZE_LABEL_W_180,
    SIZE_LABEL_W_LG,
    SIZE_PANEL_MAX,
    SIZE_PANEL_W_LG,
    SIZE_ROW_54,
    SPACE_10,
    SPACE_20,
    SPACE_6,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XXXS,
)

from ._constants import (
    _FIELD_H,
    _PRIMARY_BTN,
    _SECONDARY_BTN,
    _combo_ss,
    _make_sdiv,
)

logger = logging.getLogger(__name__)

_UNITS = ["KB", "MB", "GB"]
_UNIT_BYTES = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}


def _fmt_bytes(n: int) -> str:
    if n <= 0:
        return "0 B"
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


class _WaterTankWidget(QWidget):
    faucet_clicked = Signal()
    drain_complete = Signal()

    _PIPE_W = 16
    _VALVE_R = 17
    _PIPE_LEN = 52

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._fill = 0.0
        self._phase1 = 0.0
        self._phase2 = 1.2
        self._current_bytes = 0
        self._limit_bytes = 0
        self._draining = False
        self._valve_angle = 0.0
        self._valve_target = 0.0
        self._drops: list[list[float]] = []
        self._hovered = False
        self._valve_rect = QRectF()

        self._confirming = False
        self._confirm_ok_hov = False
        self._confirm_cancel_hov = False
        self._confirm_ok_rect = QRectF()
        self._confirm_cancel_rect = QRectF()
        self.setMinimumSize(SIZE_PANEL_W_LG, SIZE_PANEL_MAX)
        self.setMouseTracking(True)

        self._drain_phase = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(16)

    def set_data(self, current_bytes: int, limit_bytes: int) -> None:
        self._current_bytes = current_bytes
        self._limit_bytes = limit_bytes
        if limit_bytes > 0:
            self._fill = max(0.0, min(1.0, current_bytes / limit_bytes))
        elif current_bytes > 0:
            ceilings = [
                512 * 1024,
                1024**2,
                5 * 1024**2,
                10 * 1024**2,
                50 * 1024**2,
                100 * 1024**2,
                500 * 1024**2,
                1024**3,
                5 * 1024**3,
            ]
            visual_ceil = next((c for c in ceilings if c > current_bytes), ceilings[-1])
            self._fill = max(0.01, min(1.0, current_bytes / visual_ceil))
        else:
            self._fill = 0.0
        self.update()

    def start_drain(self) -> None:
        self._draining = True
        self._valve_target = 90.0

    def _tick(self) -> None:

        if self._draining:
            speed = 0.11 + self._fill * 0.09
        else:
            speed = 0.025 + self._fill * 0.018
        self._phase1 += speed
        self._phase2 += speed * 0.73

        diff = self._valve_target - self._valve_angle
        if abs(diff) > 0.5:
            self._valve_angle += diff * 0.18
        else:
            self._valve_angle = self._valve_target

        if self._draining:
            self._drain_phase += 0.07
            if self._fill > 0.001:
                progress = 1.0 - self._fill
                ease = 0.5 - 0.5 * math.cos(math.pi * progress)
                self._fill = max(0.0, self._fill - (0.001 + ease * 0.003))

                max_drops = int(50 + self._fill * 180)
                spawn_n = max(3, int(self._fill * 14)) + random.randint(0, 5)
                if len(self._drops) < max_drops:
                    for _ in range(spawn_n):
                        jx = (random.random() - 0.5) * (12 + self._fill * 30)
                        sz = 1.8 + random.random() * 3.2
                        vel = 1.4 + random.random() * 3.0
                        self._drops.append([jx, 0.0, jx * 0.05, vel, sz])
            else:
                self._fill = 0.0
                self._draining = False
                self._drain_phase = 0.0
                self._valve_target = 0.0
                self._drops.clear()
                self.drain_complete.emit()

        new_drops = []
        for d in self._drops:
            d[0] += d[2]
            d[1] += d[3]
            d[3] += 0.28
            if d[1] < 170:
                new_drops.append(d)
        self._drops = new_drops
        self.update()

    def _wave_color(self) -> tuple[QColor, QColor]:
        if self._fill < 0.6:
            return QColor(_ACCENT), QColor(_DB_ACCENT_DARK)
        if self._fill < 0.85:
            return QColor(_WARNING), QColor(_DB_WARNING_DARK)
        return QColor(_DANGER), QColor(_DB_DANGER_DARK)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        pad = 24
        faucet_area = self._PIPE_LEN + self._VALVE_R * 2 + 16
        tank_x = float(pad)
        tank_y = float(pad)
        tank_w = float(w - pad * 2)
        tank_h = float(h - pad - faucet_area - 8)
        radius = 18.0
        tank_cx = tank_x + tank_w / 2
        tank_rect = QRectF(tank_x, tank_y, tank_w, tank_h)

        p.setPen(QPen(QColor(0, 0, 0, 80), 6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tank_rect.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)

        bg_grad = QLinearGradient(QPointF(tank_x, tank_y), QPointF(tank_x + tank_w, tank_y + tank_h))
        bg_grad.setColorAt(0.0, QColor(_DB_BG_GRAD_1))
        bg_grad.setColorAt(0.55, QColor(_DB_BG_GRAD_2))
        bg_grad.setColorAt(1.0, QColor(_DB_BG_GRAD_3))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg_grad)
        p.drawRoundedRect(tank_rect, radius, radius)

        if self._fill > 0.0:
            if self._draining:
                amp1 = tank_h * 0.058
                amp2 = tank_h * 0.032
            else:
                amp1 = tank_h * 0.026
                amp2 = tank_h * 0.014
            freq1 = 2.0 * math.pi / (tank_w * 0.55)
            freq2 = 2.0 * math.pi / (tank_w * 0.38)
            water_top_y = tank_y + tank_h * (1.0 - self._fill)

            path = QPainterPath()
            path.moveTo(tank_x, tank_y + tank_h)
            steps = max(int(tank_w), 2)
            for i in range(steps + 1):
                px = tank_x + tank_w * i / steps
                py = water_top_y + amp1 * math.sin(px * freq1 + self._phase1) + amp2 * math.sin(px * freq2 - self._phase2)
                path.lineTo(px, py)
            path.lineTo(tank_x + tank_w, tank_y + tank_h)
            path.closeSubpath()

            clip = QPainterPath()
            clip.addRoundedRect(tank_rect, radius, radius)
            p.setClipPath(clip)

            top_c, bot_c = self._wave_color()
            fill_grad = QLinearGradient(QPointF(0, water_top_y), QPointF(0, tank_y + tank_h))
            fill_grad.setColorAt(0.0, top_c)
            fill_grad.setColorAt(1.0, bot_c)
            p.setBrush(fill_grad)
            p.drawPath(path)

            surf_g = QLinearGradient(QPointF(0, water_top_y - 2), QPointF(0, water_top_y + 7))
            surf_g.setColorAt(0.0, QColor(255, 255, 255, 0))
            surf_g.setColorAt(0.45, QColor(255, 255, 255, 70))
            surf_g.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(surf_g)
            p.drawRect(QRectF(tank_x + radius / 2, water_top_y - 2, tank_w - radius, 9))

            gloss_w = tank_w * 0.20
            water_h = tank_y + tank_h - water_top_y
            gloss_grad = QLinearGradient(QPointF(tank_x, 0), QPointF(tank_x + gloss_w, 0))
            gloss_grad.setColorAt(0.0, QColor(255, 255, 255, 26))
            gloss_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
            p.setBrush(gloss_grad)
            p.drawRoundedRect(QRectF(tank_x + 7, water_top_y + 4, gloss_w, water_h * 0.52), 5, 5)

            if self._draining and self._fill > 0.025:
                vx = tank_cx
                vy = tank_y + tank_h - 14.0
                for i in range(4):
                    r = max(2.0, 28.0 - i * 6)
                    alpha = 110 - i * 22
                    start = int((self._drain_phase * 230 + i * 85) % 360) * 16
                    p.setPen(QPen(QColor(0, 0, 0, alpha), 2.2 - i * 0.3))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawArc(
                        QRectF(vx - r, vy - r * 0.38, r * 2.0, r * 0.76),
                        start,
                        290 * 16,
                    )

                funnel_g = QRadialGradient(QPointF(vx, vy), 32)
                funnel_g.setColorAt(0.0, QColor(0, 0, 0, 90))
                funnel_g.setColorAt(1.0, QColor(0, 0, 0, 0))
                p.setBrush(funnel_g)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(vx, vy), 34.0, 14.0)

            p.setClipping(False)

        tick_clip = QPainterPath()
        tick_clip.addRoundedRect(tank_rect, radius, radius)
        p.setClipPath(tick_clip)
        for pct in (25, 50, 75):
            ty = tank_y + tank_h * (1.0 - pct / 100.0)
            dp = QPen(QColor(255, 255, 255, 20), 1)
            dp.setStyle(Qt.PenStyle.DashLine)
            p.setPen(dp)
            p.drawLine(
                QPointF(tank_x + radius * 0.6, ty),
                QPointF(tank_x + tank_w - radius * 0.6, ty),
            )
        p.setClipping(False)

        p.setFont(QFont("Segoe UI", FONT_SIZE_TINY))
        for pct in (25, 50, 75):
            ty = tank_y + tank_h * (1.0 - pct / 100.0)
            p.setPen(QColor(_DB_GRID))
            p.drawText(
                QRectF(tank_x + tank_w - 40, ty - 14, 36, 12),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                f"{pct}%",
            )

        p.setPen(QPen(QColor(_DB_AXIS), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(tank_rect.adjusted(0.75, 0.75, -0.75, -0.75), radius, radius)
        p.setPen(QPen(QColor(255, 255, 255, 16), 1))
        p.drawRoundedRect(tank_rect.adjusted(1.5, 1.5, -1.5, -1.5), radius - 0.5, radius - 0.5)

        shine_clip = QPainterPath()
        shine_clip.addRoundedRect(tank_rect, radius, radius)
        p.setClipPath(shine_clip)
        shine_w = tank_w * 0.15
        shine_g = QLinearGradient(QPointF(tank_x + 7, 0), QPointF(tank_x + 7 + shine_w, 0))
        shine_g.setColorAt(0.0, QColor(255, 255, 255, 22))
        shine_g.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setBrush(shine_g)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(tank_x + 7, tank_y + 6, shine_w, tank_h * 0.84), 7, 7)
        p.setClipping(False)

        pct_val = int(self._fill * 100)
        p.setFont(QFont("Segoe UI", FONT_SIZE_DISPLAY, QFont.Weight.Bold))
        text_rect = QRectF(tank_x, tank_y, tank_w, tank_h * 0.64)
        p.setPen(QColor(0, 0, 0, 90))
        p.drawText(
            text_rect.adjusted(1, 2, 1, 2),
            Qt.AlignmentFlag.AlignCenter,
            f"{pct_val}%",
        )
        p.setPen(QColor(_TEXT_PRI))
        p.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, f"{pct_val}%")

        p.setFont(QFont("Segoe UI", FONT_SIZE_MICRO))
        p.setPen(QColor(_TEXT_SEC))
        if self._limit_bytes > 0:
            sub_text = f"{_fmt_bytes(self._current_bytes)}  /  {_fmt_bytes(self._limit_bytes)}"
        else:
            sub_text = _fmt_bytes(self._current_bytes)
        p.drawText(
            QRectF(tank_x, tank_y + tank_h * 0.66, tank_w, 22),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            sub_text,
        )

        pipe_x = tank_cx - self._PIPE_W / 2
        pipe_top_y = tank_y + tank_h
        valve_cy = pipe_top_y + self._VALVE_R + 8
        spout_y = valve_cy + self._VALVE_R + 9

        sheen = QLinearGradient(QPointF(pipe_x, 0), QPointF(pipe_x + self._PIPE_W, 0))
        sheen.setColorAt(0.0, QColor(_DB_SHEEN_1))
        sheen.setColorAt(0.3, QColor(_DB_SHEEN_2))
        sheen.setColorAt(0.65, QColor(_DB_SHEEN_3))
        sheen.setColorAt(1.0, QColor(_DB_SHEEN_1))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(sheen)
        top_seg_h = max(0.0, valve_cy - self._VALVE_R - pipe_top_y)
        bot_seg_h = max(0.0, spout_y - valve_cy - self._VALVE_R)
        if top_seg_h > 0:
            p.drawRect(QRectF(pipe_x, pipe_top_y, self._PIPE_W, top_seg_h))
        if bot_seg_h > 0:
            p.drawRect(QRectF(pipe_x, valve_cy + self._VALVE_R, self._PIPE_W, bot_seg_h))

        vg = QLinearGradient(
            QPointF(tank_cx - self._VALVE_R, valve_cy - self._VALVE_R),
            QPointF(tank_cx + self._VALVE_R, valve_cy + self._VALVE_R),
        )
        vg.setColorAt(0.0, QColor(_DB_VG_0 if not self._hovered else _DB_VG_0_HOVER))
        vg.setColorAt(0.5, QColor(_DB_VG_1 if not self._hovered else _DB_VG_1_HOVER))
        vg.setColorAt(1.0, QColor(_DB_VG_2))
        p.setBrush(vg)
        glow_col = QColor(_ACCENT_HI) if self._hovered else QColor(_DB_VG_1)
        p.setPen(QPen(glow_col, 2.5 if self._hovered else 1.5))
        vr = float(self._VALVE_R)
        p.drawEllipse(QPointF(tank_cx, valve_cy), vr, vr)

        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(tank_cx, valve_cy), vr - 3, vr - 3)

        angle_rad = math.radians(self._valve_angle)
        hlen = vr + 11
        hx = math.cos(angle_rad) * hlen
        hy = math.sin(angle_rad) * hlen
        h_col = QColor(_DANGER) if self._draining else (QColor(_ACCENT_HI) if self._hovered else QColor(_DB_NEUTRAL))
        p.setPen(QPen(h_col, 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(tank_cx - hx, valve_cy - hy), QPointF(tank_cx + hx, valve_cy + hy))
        p.setBrush(h_col)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QPointF(tank_cx + hx, valve_cy + hy), 4.5, 4.5)
        p.drawEllipse(QPointF(tank_cx - hx, valve_cy - hy), 4.5, 4.5)

        self._valve_rect = QRectF(
            tank_cx - vr - 6,
            valve_cy - vr - 6,
            (vr + 6) * 2,
            (vr + 6) * 2,
        )

        if self._drops:
            top_c, _ = self._wave_color()
            for d in self._drops:
                dc = QColor(top_c)

                alpha = max(0, int(220 * (1.0 - d[1] / 80.0)))
                dc.setAlpha(alpha)
                p.setBrush(dc)
                p.setPen(Qt.PenStyle.NoPen)
                sz = d[4] if len(d) > 4 else 3.0
                spd = d[3]

                elong = min(3.0, 1.0 + max(0.0, spd) * 0.22)
                p.drawEllipse(QPointF(tank_cx + d[0], spout_y + d[1]), sz, sz * elong)

        p.setFont(QFont("Segoe UI", FONT_SIZE_TINY))
        hint_col = QColor(_ACCENT_HI if self._hovered else _DB_GRID)
        p.setPen(hint_col)
        p.drawText(
            QRectF(tank_x, spout_y + 6, tank_w, 16),
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
            "click valve to purge" if not self._draining else f"draining…  {max(0, int(self._fill * 100))}%",
        )

        if self._confirming:
            ovr = QPainterPath()
            ovr.addRoundedRect(tank_rect, radius, radius)
            p.setClipPath(ovr)
            p.setBrush(QColor(0, 0, 0, 175))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(tank_rect, radius, radius)
            p.setClipping(False)

            p.setFont(QFont("Segoe UI", FONT_SIZE_XL))
            p.setPen(QColor(_DANGER))
            p.drawText(
                QRectF(tank_x, tank_y + tank_h * 0.06, tank_w, 36),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                "\u26a0",
            )

            p.setFont(QFont("Segoe UI", FONT_SIZE_HEADING, QFont.Weight.Bold))
            p.setPen(QColor(_TEXT_PRI))
            p.drawText(
                QRectF(tank_x, tank_y + tank_h * 0.24, tank_w, 30),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                "Open the valve?",
            )

            p.setFont(QFont("Segoe UI", FONT_SIZE_MICRO))
            p.setPen(QColor(_TEXT_SEC))
            p.drawText(
                QRectF(tank_x + 24, tank_y + tank_h * 0.40, tank_w - 48, 46),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                "All data will be permanently deleted.\nCameras, faces, rules, events and logs.",
            )

            btn_w, btn_h, gap = 110.0, 36.0, 14.0
            bx = tank_cx - (btn_w * 2 + gap) / 2
            by = tank_y + tank_h * 0.66
            cancel_r = QRectF(bx, by, btn_w, btn_h)
            ok_r = QRectF(bx + btn_w + gap, by, btn_w, btn_h)

            p.setBrush(QColor(_DB_CANCEL_BG if self._confirm_cancel_hov else _DB_CANCEL_BG_ALT))
            p.setPen(QPen(QColor(_TEXT_DIM), 1))
            p.drawRoundedRect(cancel_r, 8, 8)
            p.setFont(QFont("Segoe UI", FONT_SIZE_CAPTION, QFont.Weight.DemiBold))
            p.setPen(QColor(_TEXT_SOFT))
            p.drawText(cancel_r, Qt.AlignmentFlag.AlignCenter, "Cancel")

            p.setBrush(QColor(_DANGER if self._confirm_ok_hov else _DANGER_DIM))
            p.setPen(QPen(QColor(_DANGER_BORDER_SOFT if self._confirm_ok_hov else _DANGER), 1))
            p.drawRoundedRect(ok_r, 8, 8)
            p.setFont(QFont("Segoe UI", FONT_SIZE_CAPTION, QFont.Weight.DemiBold))
            p.setPen(QColor(_TEXT_ON_ACCENT))
            p.drawText(ok_r, Qt.AlignmentFlag.AlignCenter, "Purge")

            self._confirm_ok_rect = ok_r
            self._confirm_cancel_rect = cancel_r
        p.end()

    def mouseMoveEvent(self, e) -> None:
        pos = QPointF(e.position())
        if self._confirming:
            ok_h = self._confirm_ok_rect.contains(pos)
            can_h = self._confirm_cancel_rect.contains(pos)
            changed = ok_h != self._confirm_ok_hov or can_h != self._confirm_cancel_hov
            self._confirm_ok_hov = ok_h
            self._confirm_cancel_hov = can_h
            if changed:
                self.setCursor(Qt.CursorShape.PointingHandCursor if (ok_h or can_h) else Qt.CursorShape.ArrowCursor)
                self.update()
            return
        was = self._hovered
        self._hovered = self._valve_rect.contains(pos)
        if self._hovered != was:
            self.setCursor(Qt.CursorShape.PointingHandCursor if self._hovered else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _e) -> None:
        changed = self._hovered or self._confirm_ok_hov or self._confirm_cancel_hov
        self._hovered = False
        self._confirm_ok_hov = False
        self._confirm_cancel_hov = False
        if changed:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            self.update()

    def mousePressEvent(self, e) -> None:
        if e.button() != Qt.MouseButton.LeftButton:
            return
        pos = QPointF(e.position())
        if self._valve_rect.contains(pos) and not self._draining:
            self.faucet_clicked.emit()


class _PurgeWorker(QThread):
    finished = Signal(bool, str)

    def run(self) -> None:
        try:
            # Drain any in-flight queued writes before and after reset so one purge action is enough.
            db.wait_for_writer_idle(5.0)
            db.reset_database()
            db.wait_for_writer_idle(2.0)
            db.reset_database()
            db.wait_for_writer_idle(2.0)
            from backend.database.migrations import apply as _run_migrations

            _run_migrations(db.get_conn())
            db.ensure_default_account()
            self.finished.emit(True, "")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            self.finished.emit(False, str(exc))


class DatabaseTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._current_bytes = 0
        self._purge_worker: _PurgeWorker | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, SPACE_XL)
        bl.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        bl.addWidget(_make_sdiv("Storage Limit"))
        bl.addWidget(self._build_limit_card())

        bl.addWidget(_make_sdiv("Actions"))
        bl.addWidget(self._build_actions_card())

        bl.addWidget(_make_sdiv("Storage"))
        bl.addWidget(self._build_tank_card())

        bl.addStretch()

        root.addWidget(self._build_action_bar())

    def _build_tank_card(self) -> QWidget:
        card = QWidget()
        card.setStyleSheet(f"background: {_BG_RAISED}; border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(SPACE_XL, SPACE_20, SPACE_XL, SPACE_20)
        vl.setSpacing(SPACE_10)

        self._tank = _WaterTankWidget()
        self._tank.setToolTip("Turn the valve to purge operational database data (accounts and settings are preserved)")
        self._tank.faucet_clicked.connect(self._on_faucet_clicked)
        self._tank.drain_complete.connect(self._on_drain_complete)
        vl.addWidget(self._tank, alignment=Qt.AlignmentFlag.AlignHCenter)

        info_row = QHBoxLayout()
        info_row.setSpacing(SPACE_6)

        db_label = QLabel("smarteye.db")
        db_label.setStyleSheet(
            f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_BODY}px; font-weight: {FONT_WEIGHT_BOLD}; background: transparent;"
        )
        info_row.addWidget(db_label)

        sep = QLabel("—")
        sep.setStyleSheet(f"color: {_TEXT_MUTED}; background: transparent;")
        info_row.addWidget(sep)

        self._db_size_label = QLabel("…")
        self._db_size_label.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_BODY}px; background: transparent;")
        info_row.addWidget(self._db_size_label)
        info_row.addStretch()

        self._limit_status_label = QLabel("")
        self._limit_status_label.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_LABEL}px; background: transparent;")
        info_row.addWidget(self._limit_status_label)

        vl.addLayout(info_row)
        return card

    def _build_limit_card(self) -> QWidget:
        card = QWidget()
        card.setStyleSheet("background: transparent;")
        vl = QVBoxLayout(card)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)

        row = QFrame()
        row.setMinimumHeight(SIZE_ROW_54)
        row.setStyleSheet(f"""
            QFrame {{
                background: transparent;
                border: none;
                border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
            }}
            QFrame:hover {{ background: {_ACCENT_HI_BG_03}; }}
        """)
        hl = QHBoxLayout(row)
        hl.setContentsMargins(SPACE_20, 0, SPACE_20, 0)
        hl.setSpacing(SPACE_LG)

        lbl = QLabel("Max database size")
        lbl.setFixedWidth(SIZE_LABEL_W_180)
        lbl.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lbl.setStyleSheet(
            f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_NORMAL}; background: transparent; border: none;"
        )
        hl.addWidget(lbl)

        self._limit_spin = QDoubleSpinBox()
        self._limit_spin.setRange(0, 99999)
        self._limit_spin.setDecimals(1)
        self._limit_spin.setValue(0)
        self._limit_spin.setFixedHeight(_FIELD_H)
        self._limit_spin.setSpecialValueText("No limit")
        self._limit_spin.setToolTip("Set to 0 for no limit. New data will be blocked once this size is reached.")
        hl.addWidget(self._limit_spin, stretch=1)

        self._limit_unit = QComboBox()
        self._limit_unit.setStyleSheet(_combo_ss())
        self._limit_unit.addItems(_UNITS)
        self._limit_unit.setCurrentText("MB")
        self._limit_unit.setFixedHeight(_FIELD_H)
        self._limit_unit.setFixedWidth(SIZE_BTN_W_80)
        hl.addWidget(self._limit_unit)

        vl.addWidget(row)

        hint_lbl = QLabel(
            "When the database exceeds this size the app stops saving new events, snapshots and logs "
            "until you vacuum or raise the limit.  Set to 0 to disable the cap."
        )
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet(
            f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px; background: transparent;"
            f" padding: {SPACE_SM}px {SPACE_20}px {SPACE_MD}px {SPACE_20}px;"
        )
        vl.addWidget(hint_lbl)
        return card

    def _build_actions_card(self) -> QWidget:
        card = QWidget()
        card.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(card)
        hl.setContentsMargins(SPACE_20, SPACE_LG, SPACE_20, SPACE_LG)
        hl.setSpacing(SPACE_10)

        vacuum_btn = QPushButton("Vacuum")
        vacuum_btn.setStyleSheet(_PRIMARY_BTN)
        vacuum_btn.setFixedWidth(SIZE_FIELD_W)
        vacuum_btn.setToolTip("Reclaim unused space and optimise the database file.")
        vacuum_btn.clicked.connect(self._vacuum_db)
        hl.addWidget(vacuum_btn)

        backup_btn = QPushButton("Backup…")
        backup_btn.setStyleSheet(_SECONDARY_BTN)
        backup_btn.setFixedWidth(SIZE_FIELD_W)
        backup_btn.setToolTip("Save a copy of the database to a chosen location.")
        backup_btn.clicked.connect(self._backup_db)
        hl.addWidget(backup_btn)

        purge_btn = QPushButton("Purge Operational Data")
        purge_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                color: {_DANGER};
                border: {SPACE_XXXS}px solid {_DANGER_BORDER_SOFT};
                border-radius: 8px;
                font-weight: {FONT_WEIGHT_BOLD};
                padding: 0 {SPACE_20}px;
            }}
            QPushButton:hover {{
                background: {_DANGER_DIM};
                color: {_TEXT_ON_ACCENT};
            }}
            """
        )
        purge_btn.setFixedWidth(SIZE_LABEL_W_180)
        purge_btn.setToolTip("Admin-confirmed purge for cameras, faces, rules, events, logs, and media indexes.")
        purge_btn.clicked.connect(self._on_faucet_clicked)
        hl.addWidget(purge_btn)

        hl.addStretch()
        return card

    def _build_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background: {_BG_RAISED}; border-top: {SPACE_XXXS}px solid {_BORDER_DIM};")
        hl = QHBoxLayout(bar)
        hl.setContentsMargins(SPACE_20, SPACE_MD, SPACE_20, SPACE_MD)
        hl.setSpacing(SPACE_10)
        hl.addStretch()

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_PRIMARY_BTN)
        save_btn.setFixedWidth(SIZE_LABEL_W_LG)
        save_btn.clicked.connect(self._save_limit)
        hl.addWidget(save_btn)
        return bar

    def _save_limit(self) -> None:
        value = self._limit_spin.value()
        unit = self._limit_unit.currentText()
        limit_bytes = int(value * _UNIT_BYTES[unit]) if value > 0 else 0
        db.set_setting("db_size_limit_bytes", str(limit_bytes))
        self._update_tank()
        QMessageBox.information(
            self,
            "Saved",
            "No limit set." if limit_bytes == 0 else f"Limit saved: {_fmt_bytes(limit_bytes)}",
        )

    def _vacuum_db(self) -> None:
        try:
            db.vacuum()
            QMessageBox.information(self, "Done", "Database vacuumed successfully.")
            self.load()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _backup_db(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Backup Database", "smarteye_backup.db", "SQLite DB (*.db)")
        if not path:
            return
        try:
            db.backup(path)
            QMessageBox.information(self, "Done", f"Backup saved to:\n{path}")
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _on_faucet_clicked(self) -> None:
        if self._purge_worker is not None:
            return
        if not self._confirm_admin_purge():
            return
        if not self._start_purge_worker():
            return
        self._tank.start_drain()

    def _start_purge_worker(self) -> bool:
        if not self._stop_active_cameras_for_purge():
            return False
        self._current_bytes = 0
        self._db_size_label.setText(_fmt_bytes(0))
        self._tank.set_data(0, 0)
        self._limit_status_label.setText("Purging database…")
        QApplication.processEvents()
        self._purge_worker = _PurgeWorker(self)
        self._purge_worker.finished.connect(self._on_purge_done)
        self._purge_worker.start()
        return True

    def _stop_active_cameras_for_purge(self) -> bool:
        try:
            from backend.camera.camera_manager import get_camera_manager

            get_camera_manager().stop_all()
            return True
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Purge Blocked", f"Unable to stop active camera streams before purge:\n{exc}")
            return False

    def _confirm_admin_purge(self) -> bool:
        dlg = QDialog(self)
        dlg.setWindowTitle("Confirm Database Purge")
        dlg.setModal(True)
        dlg.setFixedSize(SIZE_PANEL_W_LG, 300)
        apply_popup_theme(
            dlg,
            f"""
            QDialog QLabel {{
                color: {_TEXT_PRI};
                background: transparent;
                font-size: {FONT_SIZE_BODY}px;
            }}
            QDialog QLineEdit {{
                min-height: {_FIELD_H}px;
                padding: 0 {SPACE_10}px;
                font-size: {FONT_SIZE_LABEL}px;
            }}
            """,
        )
        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(SPACE_20, SPACE_20, SPACE_20, SPACE_20)
        layout.setSpacing(SPACE_10)

        title = QLabel("Administrator Confirmation Required")
        title.setStyleSheet(
            f"color: {_TEXT_PRI}; font-size: {FONT_SIZE_HEADING}px; font-weight: {FONT_WEIGHT_BOLD}; background: transparent;"
        )
        layout.addWidget(title)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        form.setHorizontalSpacing(SPACE_10)
        form.setVerticalSpacing(SPACE_10)

        email_edit = QLineEdit()
        email_edit.setPlaceholderText("admin@smarteye.local")
        password_edit = QLineEdit()
        password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        password_edit.setPlaceholderText("Administrator password")
        attach_password_visibility_toggle(password_edit)

        form.addRow("Admin Email", email_edit)
        form.addRow("Password", password_edit)
        layout.addLayout(form)

        hint = QLabel("Purge will delete operational data only. Accounts and app settings are preserved.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {_TEXT_MUTED}; font-size: {FONT_SIZE_CAPTION}px;")
        layout.addWidget(hint)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        confirm_btn = QPushButton("Purge")
        confirm_btn.setStyleSheet(_PRIMARY_BTN)
        confirm_btn.setFixedWidth(SIZE_LABEL_W_LG)
        confirm_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(confirm_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_SECONDARY_BTN)
        cancel_btn.setFixedWidth(SIZE_LABEL_W_LG)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

        email_edit.setFocus()

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

        email = email_edit.text().strip()
        password = password_edit.text()
        account = db.verify_credentials(email, password)
        if not account or not bool(account.get("is_admin")):
            QMessageBox.warning(self, "Authorization Failed", "Valid administrator credentials are required.")
            return False
        return True

    def _on_drain_complete(self) -> None:
        # Drain animation completion is visual-only; purge starts right after auth.
        pass

    def _on_purge_done(self, success: bool, error_msg: str) -> None:
        self._purge_worker = None
        if not success:
            QMessageBox.warning(self, "Purge Error", error_msg)
        try:
            self.load()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        if success:
            self._limit_status_label.setText("Database purged successfully (accounts preserved).")
        QApplication.processEvents()
        QTimer.singleShot(120, self.load)

    def _reset_db(self) -> None:
        try:
            db.reset_database()
            from backend.database.migrations import apply as _run_migrations

            _run_migrations(db.get_conn())
            self.load()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "Error", str(exc))

    def _update_tank(self) -> None:
        limit_bytes = int(db.get_setting("db_size_limit_bytes", "0") or "0")
        self._tank.set_data(self._current_bytes, limit_bytes)
        if limit_bytes > 0:
            pct = self._current_bytes / limit_bytes * 100
            self._limit_status_label.setText(f"Limit: {_fmt_bytes(limit_bytes)}  \u2022  {pct:.0f}% used")
        else:
            self._limit_status_label.setText(f"{_fmt_bytes(self._current_bytes)} used  \u2022  no limit set")

    def load(self) -> None:
        db_path = db.get_db_path()
        self._current_bytes = os.path.getsize(db_path) if os.path.isfile(db_path) else 0
        self._db_size_label.setText(_fmt_bytes(self._current_bytes))

        limit_bytes = int(db.get_setting("db_size_limit_bytes", "0") or "0")
        if limit_bytes > 0:
            for unit in reversed(_UNITS):
                divisor = _UNIT_BYTES[unit]
                if limit_bytes >= divisor:
                    self._limit_spin.setValue(limit_bytes / divisor)
                    self._limit_unit.setCurrentText(unit)
                    break
        else:
            self._limit_spin.setValue(0)
            self._limit_unit.setCurrentText("MB")

        self._update_tank()

