import logging
from collections import deque

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPaintEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from frontend.app_theme import safe_set_point_size
from frontend.styles._colors import (
    _BG_OVERLAY,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI,
    _TEXT_SEC,
    _TEXT_MUTED,
    _ACCENT_HI,
    _WARNING,
    _DANGER,
)
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_MD,
    SPACE_6,
    SPACE_SM,
    SPACE_10,
    SPACE_MD,
    SPACE_14,
    SPACE_18,
    SPACE_XXXS,
    SIZE_LABEL_W_SM,
    SIZE_PANEL_H_LG,
)
from frontend.styles.page_styles import divider_style, muted_label_style, text_style, transparent_surface_style
from utils.system_monitor import get_monitor

logger = logging.getLogger(__name__)


class AnimatedBar(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self._value = 0.0
        self._target = 0.0
        self._fill_color = QColor(color)
        self.setFixedHeight(SPACE_6)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)

    def set_fill_color(self, color: str):
        self._fill_color = QColor(color)
        self.update()

    def set_value(self, v: float):
        self._target = max(0.0, min(100.0, v))
        if not self._timer.isActive():
            self._timer.start()

    def _step(self):
        diff = self._target - self._value
        if abs(diff) < 0.25:
            self._value = self._target
            self._timer.stop()
        else:
            self._value += diff * 0.10
        self.update()

    def paintEvent(self, _: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, r = self.width(), self.height(), self.height() / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(_BORDER_DIM))
        p.drawRoundedRect(0, 0, w, h, r, r)
        fw = int(w * self._value / 100)
        if fw > r * 2:
            p.setBrush(self._fill_color)
            p.drawRoundedRect(0, 0, fw, h, r, r)
        p.end()


class MetricRow(QWidget):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_10)

        lbl = QLabel(name)
        lbl.setFixedWidth(SIZE_LABEL_W_SM)
        lbl.setStyleSheet(
            text_style(
                _TEXT_MUTED,
                size=FONT_SIZE_CAPTION,
                weight=FONT_WEIGHT_SEMIBOLD,
                extra="letter-spacing: 0.{}px; {}".format(SPACE_6, transparent_surface_style()),
            )
        )
        layout.addWidget(lbl)

        self._bar = AnimatedBar(_ACCENT_HI)
        layout.addWidget(self._bar)

        self._pct = QLabel("0%")
        self._pct.setFixedWidth(SIZE_LABEL_W_SM)
        self._pct.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._pct.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_CAPTION, weight=FONT_WEIGHT_SEMIBOLD, extra=transparent_surface_style()))
        layout.addWidget(self._pct)

    def update_value(self, value: float):
        self._bar.set_value(value)
        self._pct.setText(f"{value:.0f}%")
        if value >= 85:
            color = _DANGER
            self._bar.set_fill_color(_DANGER)
        elif value >= 65:
            color = _WARNING
            self._bar.set_fill_color(_WARNING)
        else:
            color = _TEXT_SEC
            self._bar.set_fill_color(_ACCENT_HI)
        self._pct.setStyleSheet(text_style(color, size=FONT_SIZE_CAPTION, weight=FONT_WEIGHT_SEMIBOLD, extra=transparent_surface_style()))


class _Divider(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(SPACE_XXXS)
        self.setStyleSheet(divider_style(color=_BG_OVERLAY))


class PerformanceWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("PerformanceWidget")
        self.setStyleSheet("""
            QFrame#PerformanceWidget {{
                background-color: {bg};
                border: {border_w}px solid {border};
                border-radius: {radius}px;
            }}
            QFrame#PerformanceWidget:hover {{
                border-color: {hover_border};
            }}
        """.format(
            bg=_BG_RAISED,
            border_w=SPACE_XXXS,
            border=_BORDER,
            radius=RADIUS_MD,
            hover_border=_BORDER_DIM,
        ))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(SIZE_PANEL_H_LG)

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_18, SPACE_14, SPACE_18, SPACE_14)
        root.setSpacing(0)

        header = QHBoxLayout()
        header.setSpacing(0)

        title = QLabel("System Performance")
        f = QFont()
        safe_set_point_size(f, FONT_SIZE_LABEL)
        f.setBold(True)
        title.setFont(f)
        title.setStyleSheet(text_style(_TEXT_PRI, extra=transparent_surface_style()))
        header.addWidget(title)
        header.addStretch()

        root.addLayout(header)
        root.addSpacing(SPACE_6)

        self._inference_label = QLabel("Inference latency  —")
        self._inference_label.setTextFormat(Qt.TextFormat.RichText)
        self._inference_label.setStyleSheet(muted_label_style(color=_TEXT_MUTED, size=FONT_SIZE_CAPTION, weight=FONT_WEIGHT_SEMIBOLD))
        root.addWidget(self._inference_label)

        root.addSpacing(SPACE_MD)
        root.addWidget(_Divider())
        root.addSpacing(SPACE_MD)

        self._cpu = MetricRow("CPU")
        root.addWidget(self._cpu)
        root.addSpacing(SPACE_10)

        self._ram = MetricRow("RAM")
        root.addWidget(self._ram)
        root.addSpacing(SPACE_10)

        self._gpu = MetricRow("GPU")
        root.addWidget(self._gpu)
        root.addSpacing(SPACE_SM)

        self._ram_total = self._get_ram_total()
        self._face_ms_samples = deque(maxlen=24)
        self._obj_ms_samples = deque(maxlen=24)
        self._providers = QLabel("Face model: --\nObject model: --\nInstalled RAM: --")
        self._providers.setWordWrap(True)
        self._providers.setStyleSheet(muted_label_style(color=_TEXT_MUTED, size=FONT_SIZE_CAPTION))
        root.addSpacing(SPACE_6)
        root.addWidget(self._providers)

        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh)
        self._refresh_timer.start(1000)

    def pause(self):
        self._refresh_timer.stop()

    def resume(self):
        if not self._refresh_timer.isActive():
            self._refresh_timer.start(1000)

    def _refresh(self):
        try:
            m = get_monitor()
            self._cpu.update_value(m.cpu)
            self._ram.update_value(m.ram)
            self._gpu.update_value(m.gpu_load)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            logger.debug("Failed to refresh performance metrics", exc_info=True)

    def update_inference(self, face_ms: float, obj_ms: float):
        try:
            face_val = max(0.0, float(face_ms or 0.0))
        except Exception:
            face_val = 0.0
        try:
            obj_val = max(0.0, float(obj_ms or 0.0))
        except Exception:
            obj_val = 0.0

        self._face_ms_samples.append(face_val)
        self._obj_ms_samples.append(obj_val)
        face_avg = (sum(self._face_ms_samples) / len(self._face_ms_samples)) if self._face_ms_samples else face_val
        obj_avg = (sum(self._obj_ms_samples) / len(self._obj_ms_samples)) if self._obj_ms_samples else obj_val

        self._inference_label.setText(
            f"<span style='color:{_TEXT_MUTED}'>Face</span> "
            f"<span style='color:{_TEXT_SEC}; font-weight:{FONT_WEIGHT_SEMIBOLD}'>{face_avg:.1f}ms</span>"
            f"<span style='color:{_TEXT_MUTED}'>&nbsp;|&nbsp;Object</span> "
            f"<span style='color:{_TEXT_SEC}; font-weight:{FONT_WEIGHT_SEMIBOLD}'>{obj_avg:.1f}ms</span>"
        )

    def update_providers(self, items, gpu_name: str = "", cpu_name: str = "", cpu_name_long: str = ""):
        face_line = "Face model: --"
        obj_line = "Object model: --"
        ram_line = f"Installed RAM: {self._ram_total}"
        cpu_label = cpu_name or "CPU"
        cpu_long = cpu_name_long or cpu_label
        gpu_label = gpu_name or "GPU"

        for ent in items:
            prov_raw = str(ent.get("provider") or "")
            prov_items = [p.strip().lower() for p in prov_raw.split(",") if p.strip()]
            primary = prov_items[0] if prov_items else prov_raw.lower()
            has_gpu = any(any(k in tok for k in ("dml", "cuda", "rocm", "openvino", "coreml", "gpu")) for tok in prov_items)
            if has_gpu or any(k in primary for k in ("dml", "cuda", "rocm", "openvino", "coreml", "gpu")):
                branded = f"GPU ({gpu_label})"
            else:
                branded = f"CPU ({cpu_long})"
            if ent.get("type") == "face":
                face_line = f"Face model: {branded}"
            else:
                obj_line = f"Object model: {branded}"

        self._providers.setText(face_line + "\n" + obj_line + "\n" + ram_line)

    @staticmethod
    def _format_bytes(num_bytes: int) -> str:
        gb = num_bytes / (1024**3)
        return f"{gb:.2f} GB"

    def _get_ram_total(self) -> str:
        try:
            import psutil

            return self._format_bytes(psutil.virtual_memory().total)
        except (ImportError, AttributeError, OSError):
            return "Unknown"
