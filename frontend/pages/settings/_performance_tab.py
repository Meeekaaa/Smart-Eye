from __future__ import annotations

import logging

from PySide6.QtCore import QPropertyAnimation, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)

from backend.repository import db
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.styles._colors import _SUCCESS
from frontend.ui_tokens import (
    FONT_SIZE_LABEL,
    FONT_WEIGHT_BOLD,
    SIZE_BTN_W_100,
    SPACE_20,
    SPACE_MD,
    SPACE_XL,
)

from ._constants import (
    _FIELD_H,
    _PRIMARY_BTN,
    _combo_ss,
    _make_sdiv,
    _srow,
)

logger = logging.getLogger(__name__)

_PROVIDER_PRESETS = [
    ("Auto (best available)", "auto"),
    ("CPU only", "cpu"),
    ("NVIDIA GPU (CUDA)", "cuda"),
    ("Intel/AMD GPU (DirectML)", "dml"),
    ("AMD GPU (ROCm)", "rocm"),
]


class PerformanceTab(QWidget):
    tab_transitions_changed = Signal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()
        self.load()

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

        bl.addWidget(_make_sdiv("GPU Acceleration"))

        self._gpu_toggle = ToggleSwitch()
        self._gpu_toggle.toggled.connect(self._sync_provider_controls)
        bl.addWidget(
            _srow(
                "Enable GPU",
                self._gpu_toggle,
                hint="GPU is auto-detected via ONNX Runtime providers. AMD uses ROCm; Intel/AMD on Windows use DirectML.",
            )
        )

        self._face_provider = QComboBox()
        self._face_provider.setStyleSheet(_combo_ss())
        for label, value in _PROVIDER_PRESETS:
            self._face_provider.addItem(label, value)
        self._face_provider.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Face provider",
                self._face_provider,
                hint="Choose provider profile for face recognition. Preset also applies tuned defaults.",
            )
        )

        self._plugin_provider = QComboBox()
        self._plugin_provider.setStyleSheet(_combo_ss())
        for label, value in _PROVIDER_PRESETS:
            self._plugin_provider.addItem(label, value)
        self._plugin_provider.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Plugins provider",
                self._plugin_provider,
                hint="Choose provider profile for loaded ONNX plugins. Preset also applies tuned defaults.",
            )
        )

        bl.addWidget(_make_sdiv("Resource Limits"))

        self._limit_resources = ToggleSwitch()
        self._limit_resources.toggled.connect(self._sync_resource_controls)
        bl.addWidget(
            _srow(
                "Limit resource usage",
                self._limit_resources,
                hint="Enable hard caps for app CPU and memory consumption.",
            )
        )

        self._max_cpu_cores = QSpinBox()
        self._max_cpu_cores.setRange(1, 128)
        self._max_cpu_cores.setValue(2)
        self._max_cpu_cores.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Max CPU cores",
                self._max_cpu_cores,
                hint="Restricts process CPU affinity to this many logical cores when limits are enabled.",
            )
        )

        self._max_ram_mb = QSpinBox()
        self._max_ram_mb.setRange(256, 262144)
        self._max_ram_mb.setValue(4096)
        self._max_ram_mb.setSuffix(" MB")
        self._max_ram_mb.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Max RAM",
                self._max_ram_mb,
                hint="Attempts to cap this process working set. Applies best-effort per OS.",
            )
        )

        bl.addWidget(_make_sdiv("Frame Processing"))

        self._frame_skip = QSpinBox()
        self._frame_skip.setRange(0, 30)
        self._frame_skip.setValue(0)
        self._frame_skip.setSuffix(" frames")
        self._frame_skip.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Frame skip",
                self._frame_skip,
                hint="Drop N display frames between each decoded frame. Reduces CPU/GPU load at the cost of visual smoothness.",
            )
        )

        self._detection_interval = QSpinBox()
        self._detection_interval.setRange(1, 30)
        self._detection_interval.setValue(1)
        self._detection_interval.setSuffix(" frames")
        self._detection_interval.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Detection interval",
                self._detection_interval,
                hint="Run inference every N display frames. "
                "1 = lowest latency and tightest live tracking. "
                "Higher values reduce compute load but increase visible bbox lag.",
            )
        )

        bl.addWidget(_make_sdiv("UI & Tabs"))

        self._tab_transitions = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Tab transition animations",
                self._tab_transitions,
                hint="Animates page and panel changes when switching tabs.",
            )
        )

        self._pause_tabs = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Pause inactive tabs",
                self._pause_tabs,
                hint="Stops timers and UI updates when a tab is not active.",
            )
        )

        self._unload_tabs = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Unload heavy tabs on leave",
                self._unload_tabs,
                hint="Destroys video-heavy pages when you switch away to free memory.",
            )
        )

        self._unload_idle_min = QSpinBox()
        self._unload_idle_min.setRange(1, 60)
        self._unload_idle_min.setValue(5)
        self._unload_idle_min.setSuffix(" min")
        self._unload_idle_min.setFixedHeight(_FIELD_H)
        bl.addWidget(
            _srow(
                "Unload idle tabs after",
                self._unload_idle_min,
                hint="Idle tabs are unloaded after this many minutes.",
            )
        )

        self._auto_pause_live = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Auto-stop live cameras when idle",
                self._auto_pause_live,
                hint="Stops all cameras when no monitoring tabs are active. Restarts when returning.",
            )
        )

        bl.addStretch()
        bl.addWidget(self._make_action_bar())

    def _make_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(SPACE_20, SPACE_MD, SPACE_20, SPACE_MD)
        row.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{_SUCCESS};font-weight:{FONT_WEIGHT_BOLD};font-size:{FONT_SIZE_LABEL}px;")
        self._status_lbl.setContentsMargins(0, 0, 0, 0)
        self._status_lbl.setVisible(False)
        row.addWidget(self._status_lbl)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_PRIMARY_BTN)
        save_btn.setFixedWidth(SIZE_BTN_W_100)
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return bar

    def _save(self) -> None:
        face_pref = str(self._face_provider.currentData() or "auto")
        plugin_pref = str(self._plugin_provider.currentData() or "auto")

        unsupported = self._get_unsupported_provider_prefs(face_pref, plugin_pref)
        if unsupported:
            supported = ", ".join(self._get_supported_provider_prefs())
            details = "\n".join(f"- {item}" for item in unsupported)
            QMessageBox.warning(
                self,
                "Unsupported Provider",
                "Cannot save because one or more selected providers are not supported on this device.\n\n"
                f"{details}\n\n"
                f"Supported options on this device: {supported}",
            )
            return

        db.set_setting("gpu_enabled", "1" if self._gpu_toggle.isChecked() else "0")
        # Always persist user-selected provider preferences, even if unsupported on this machine.
        # This allows copying config to another machine/GPU without losing intent.
        db.set_setting("face_onnx_provider_preference", face_pref)
        db.set_setting("plugin_onnx_provider_preference", plugin_pref)
        db.set_setting("max_cpu_cores", str(self._max_cpu_cores.value()))
        db.set_setting("max_ram_mb", str(self._max_ram_mb.value()))
        # Keep legacy key for components still keyed on max_threads.
        db.set_setting("max_threads", str(self._max_cpu_cores.value()))
        db.set_setting("frame_skip", str(self._frame_skip.value()))
        db.set_setting("detection_interval", str(self._detection_interval.value()))
        db.set_setting("limit_resources", 1 if self._limit_resources.isChecked() else 0)
        tab_transitions_enabled = self._tab_transitions.isChecked()
        db.set_setting("ui_tab_transitions_enabled", 1 if tab_transitions_enabled else 0)
        db.set_setting("ui_pause_inactive_tabs", 1 if self._pause_tabs.isChecked() else 0)
        db.set_setting("ui_unload_on_leave", 1 if self._unload_tabs.isChecked() else 0)
        db.set_setting("ui_unload_idle_min", str(self._unload_idle_min.value()))
        db.set_setting("auto_pause_live_when_idle", 1 if self._auto_pause_live.isChecked() else 0)
        self.tab_transitions_changed.emit(tab_transitions_enabled)

        self._apply_provider_tuning(face_pref, plugin_pref)

        try:
            from utils.resource_limiter import apply_limits

            apply_limits(
                bool(db.get_setting("limit_resources", False)),
                int(db.get_setting("max_cpu_cores", db.get_setting("max_threads", 1) or 1)),
                int(db.get_setting("max_ram_mb", 4096) or 4096),
            )
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.exception("Failed to apply resource limits after save")

        try:
            from backend.models import model_loader
            from utils import config as _cfg

            _cfg.invalidate_cache()
            model_loader.load_face_model_async()
            notify_plugins_changed = None
            try:
                from backend.pipeline.detector_manager import notify_plugins_changed as _npc

                notify_plugins_changed = _npc
            except Exception:
                notify_plugins_changed = None
            if notify_plugins_changed:
                notify_plugins_changed()
            model_loader.load_face_model()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.exception("Failed to reload face model after performance settings save")
        if db.get_bool("ui_show_save_popups", False):
            QMessageBox.information(self, "Saved", "Performance settings saved.")
        else:
            self._flash_status("Saved")
            logger.info("Performance settings saved.")

    def _flash_status(self, text: str) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setVisible(True)
        eff = QGraphicsOpacityEffect(self._status_lbl)
        self._status_lbl.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self._status_lbl)
        anim.setDuration(1000)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(
            lambda: (
                self._status_lbl.setText(""),
                self._status_lbl.setGraphicsEffect(None),
                self._status_lbl.setVisible(False),
            )
        )
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def load(self) -> None:
        self._gpu_toggle.setChecked(db.get_bool("gpu_enabled", False))
        face_pref = str(db.get_setting("face_onnx_provider_preference", "auto") or "auto")
        plugin_pref = str(db.get_setting("plugin_onnx_provider_preference", "auto") or "auto")

        face_idx = self._face_provider.findData(face_pref)
        self._face_provider.setCurrentIndex(face_idx if face_idx >= 0 else 0)
        plugin_idx = self._plugin_provider.findData(plugin_pref)
        self._plugin_provider.setCurrentIndex(plugin_idx if plugin_idx >= 0 else 0)

        self._max_cpu_cores.setValue(int(db.get_int("max_cpu_cores", db.get_int("max_threads", 2) or 2) or 2))
        self._max_ram_mb.setValue(int(db.get_int("max_ram_mb", 4096) or 4096))
        self._frame_skip.setValue(int(db.get_int("frame_skip", 0) or 0))
        self._detection_interval.setValue(int(db.get_int("detection_interval", 1) or 1))
        self._limit_resources.setChecked(db.get_bool("limit_resources", False))

        self._tab_transitions.setChecked(db.get_bool("ui_tab_transitions_enabled", True))
        self._pause_tabs.setChecked(db.get_bool("ui_pause_inactive_tabs", True))
        self._unload_tabs.setChecked(db.get_bool("ui_unload_on_leave", True))
        self._unload_idle_min.setValue(int(db.get_int("ui_unload_idle_min", 5) or 5))
        self._auto_pause_live.setChecked(db.get_bool("auto_pause_live_when_idle", False))
        self._sync_provider_controls(self._gpu_toggle.isChecked())
        self._sync_resource_controls(self._limit_resources.isChecked())

    def _sync_provider_controls(self, gpu_enabled: bool) -> None:
        # "Enable GPU" is the master guard for provider profile controls.
        self._face_provider.setEnabled(bool(gpu_enabled))
        self._plugin_provider.setEnabled(bool(gpu_enabled))

    def _sync_resource_controls(self, limits_enabled: bool) -> None:
        enabled = bool(limits_enabled)
        self._max_cpu_cores.setEnabled(enabled)
        self._max_ram_mb.setEnabled(enabled)

    def _get_supported_provider_prefs(self) -> list[str]:
        # These are preference keys (not ORT provider class names).
        supported = ["auto", "cpu"]
        try:
            import onnxruntime as ort

            avail = set(ort.get_available_providers() or [])
        except Exception:
            avail = set()

        if "CUDAExecutionProvider" in avail:
            supported.append("cuda")
        if "DmlExecutionProvider" in avail:
            supported.append("dml")
        if "ROCMExecutionProvider" in avail:
            supported.append("rocm")
        return supported

    def _get_unsupported_provider_prefs(self, face_pref: str, plugin_pref: str) -> list[str]:
        supported = set(self._get_supported_provider_prefs())
        issues: list[str] = []
        if face_pref not in supported:
            issues.append(f"Face provider: {face_pref}")
        if plugin_pref not in supported:
            issues.append(f"Plugins provider: {plugin_pref}")
        return issues

    def _apply_provider_tuning(self, face_pref: str, plugin_pref: str) -> None:
        # Plugin profile drives frame/inference pacing defaults.
        if plugin_pref == "cuda":
            db.set_setting("detection_interval", "1")
            db.set_setting("live_infer_dim", "512")
            db.set_setting("playback_infer_target_fps", "16")
        elif plugin_pref == "dml":
            db.set_setting("detection_interval", "1")
            db.set_setting("live_infer_dim", "448")
            db.set_setting("playback_infer_target_fps", "12")
        elif plugin_pref == "rocm":
            db.set_setting("detection_interval", "1")
            db.set_setting("live_infer_dim", "512")
            db.set_setting("playback_infer_target_fps", "14")
        elif plugin_pref == "cpu":
            db.set_setting("detection_interval", "2")
            db.set_setting("live_infer_dim", "320")
            db.set_setting("playback_infer_target_fps", "8")

        # Face profile drives face-ID throughput defaults.
        if face_pref in ("cuda", "dml", "rocm"):
            db.set_setting("max_faces_identify_per_frame", "16")
        elif face_pref == "cpu":
            db.set_setting("max_faces_identify_per_frame", "8")

