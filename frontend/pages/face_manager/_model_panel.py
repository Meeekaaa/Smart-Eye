from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon, QPixmap, QTransform
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.styles._colors import _WARNING_ORANGE
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_WEIGHT_SEMIBOLD,
    SIZE_BTN_W_SM,
    SIZE_CONTROL_LG,
    SIZE_CONTROL_SM,
    SPACE_10,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XXXS,
)

from ._constants import (
    _BG_SURFACE,
    _BORDER_DIM,
    _DANGER,
    _DANGER_BTN,
    _PRIMARY_BTN,
    _SUCCESS,
    _TEXT_SEC,
)


_FM_LOAD_WORKERS: set = set()


class _ModelPanelMixin:
    def _apply_loading_icon(self, dlg: QProgressDialog) -> None:
        base_icon = QPixmap("frontend/assets/icons/loading.png")
        if base_icon.isNull():
            return

        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        angle = 0

        def _render_frame() -> None:
            rotated = base_icon.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(
                rotated.scaled(
                    36,
                    36,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        def _tick() -> None:
            nonlocal angle
            angle = (angle + 18) % 360
            _render_frame()

        _render_frame()

        timer = QTimer(dlg)
        timer.setInterval(40)
        timer.timeout.connect(_tick)
        timer.start()

        layout = dlg.layout()
        if layout is not None:
            layout.insertWidget(0, icon_lbl, 0, Qt.AlignmentFlag.AlignHCenter)

    def _build_model_config_panel(self) -> QFrame:
        from backend.models.face_model import AVAILABLE_MODELS

        panel = QFrame()
        panel.setObjectName("ModelConfigPanel")
        panel.setStyleSheet(f"""
            QFrame#ModelConfigPanel {{
                background-color: {_BG_SURFACE};
                border-top: none;
                border-bottom: {SPACE_XXXS}px solid {_BORDER_DIM};
            }}
        """)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD)
        pl.setSpacing(SPACE_SM)

        hdr = QHBoxLayout()
        hdr.setSpacing(SPACE_10)
        sec_lbl = QLabel("InsightFace Model Configuration")
        sf = QFont()
        safe_set_point_size(sf, FONT_SIZE_CAPTION)
        sf.setBold(True)
        sec_lbl.setFont(sf)
        sec_lbl.setStyleSheet(f"color: {_TEXT_SEC}; background: transparent;")
        hdr.addWidget(sec_lbl)
        hdr.addStretch()
        self._fm_loading_icon_lbl = QLabel()
        self._fm_loading_icon_lbl.setFixedSize(16, 16)
        self._fm_loading_icon_lbl.setVisible(False)
        hdr.addWidget(self._fm_loading_icon_lbl)
        self._fm_model_status = QLabel("Status: checking\u2026")
        self._fm_model_status.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};")
        hdr.addWidget(self._fm_model_status)
        pl.addLayout(hdr)

        pack_row = QHBoxLayout()
        pack_row.setSpacing(SPACE_SM)
        pack_lbl = QLabel("Pack:")
        pack_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px;")
        pack_lbl.setFixedWidth(SIZE_CONTROL_LG)
        pack_row.addWidget(pack_lbl)
        self._fm_buffalo_combo = QComboBox()
        self._fm_buffalo_combo.setFixedHeight(SIZE_CONTROL_SM)
        for key, desc in AVAILABLE_MODELS.items():
            self._fm_buffalo_combo.addItem(desc, key)
        self._fm_buffalo_combo.setToolTip(
            "buffalo_l: most accurate, downloads ~300 MB on first use\n"
            "buffalo_s / buffalo_sc: faster, smaller, less accurate\n"
            "antelopev2: highest accuracy, largest model"
        )
        self._fm_buffalo_combo.activated.connect(self._fm_on_model_changed)
        pack_row.addWidget(self._fm_buffalo_combo, stretch=1)
        pl.addLayout(pack_row)

        path_row = QHBoxLayout()
        path_row.setSpacing(SPACE_SM)
        path_lbl = QLabel("Root:")
        path_lbl.setStyleSheet(f"color: {_TEXT_SEC}; font-size: {FONT_SIZE_LABEL}px;")
        path_lbl.setFixedWidth(SIZE_CONTROL_LG)
        path_row.addWidget(path_lbl)
        self._fm_model_path = QLineEdit()
        self._fm_model_path.setPlaceholderText("~/.insightface  (leave blank for default)")
        self._fm_model_path.setFixedHeight(SIZE_CONTROL_SM)
        path_row.addWidget(self._fm_model_path, stretch=1)

        browse_btn = QPushButton("Browse\u2026")
        browse_btn.setFixedHeight(SIZE_CONTROL_SM)
        browse_btn.setFixedWidth(SIZE_BTN_W_SM)
        browse_btn.setStyleSheet(_PRIMARY_BTN)
        browse_btn.clicked.connect(self._fm_browse_path)
        path_row.addWidget(browse_btn)

        self._fm_save_reload_btn = QPushButton("Save")
        self._fm_save_reload_btn.setFixedHeight(SIZE_CONTROL_SM)
        self._fm_save_reload_btn.setFixedWidth(SIZE_BTN_W_SM)
        self._fm_save_reload_btn.setStyleSheet(_PRIMARY_BTN)
        self._fm_save_reload_btn.clicked.connect(self._fm_save_only)
        path_row.addWidget(self._fm_save_reload_btn)

        close_panel_btn = QPushButton("Close")
        close_panel_btn.setFixedHeight(SIZE_CONTROL_SM)
        close_panel_btn.setFixedWidth(SIZE_BTN_W_SM)
        close_panel_btn.setStyleSheet(_DANGER_BTN)
        close_panel_btn.clicked.connect(self._close_model_panel)
        path_row.addWidget(close_panel_btn)
        pl.addLayout(path_row)

        return panel

    def _toggle_model_panel(self):
        visible = self._model_config_panel.isVisible()
        self._model_config_panel.setVisible(not visible)
        self._model_config_btn.setChecked(not visible)
        if not visible:
            self._fm_load_model_status()

    def _close_model_panel(self):
        self._model_config_panel.setVisible(False)
        self._model_config_btn.setChecked(False)

    def _fm_load_model_status(self):
        from backend.models.model_loader import get_face_model

        fm = get_face_model()
        if fm.is_loaded:
            providers_str = ", ".join(p.replace("ExecutionProvider", "") for p in (fm.providers_used or [])) or "CPU"
            self._fm_model_status.setText(f"\u25cf {fm.model_name} \u2014 {providers_str}")
            self._fm_model_status.setStyleSheet(f"color: {_SUCCESS}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};")
        else:
            self._fm_model_status.setText("\u25cf Not loaded")
            self._fm_model_status.setStyleSheet(f"color: {_DANGER}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};")
        with contextlib.suppress(Exception):
            self._fm_model_path.setText(db.get_setting("insightface_model_dir", ""))
        with contextlib.suppress(Exception):
            saved = db.get_setting("insightface_model_name", "buffalo_l")
            self._fm_buffalo_combo.blockSignals(True)
            for i in range(self._fm_buffalo_combo.count()):
                if self._fm_buffalo_combo.itemData(i) == saved:
                    self._fm_buffalo_combo.setCurrentIndex(i)
                    break
            self._fm_buffalo_combo.blockSignals(False)

    def _fm_select_model_key(self, model_name: str) -> None:
        self._fm_buffalo_combo.blockSignals(True)
        for i in range(self._fm_buffalo_combo.count()):
            if self._fm_buffalo_combo.itemData(i) == model_name:
                self._fm_buffalo_combo.setCurrentIndex(i)
                break
        self._fm_buffalo_combo.blockSignals(False)

    def _fm_confirm_download_if_missing(self, model_name: str) -> bool | None:
        from backend.models.face_model import is_insightface_model_installed

        model_path = self._fm_model_path.text().strip()
        if is_insightface_model_installed(model_name, model_path):
            return False

        answer = QMessageBox.question(
            self,
            "Download InsightFace Model?",
            f"{model_name} is not installed locally.\n\nDownload this model pack now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._fm_model_status.setText(f"\u25cf {model_name} is not installed. Download canceled.")
            self._fm_model_status.setStyleSheet(
                f"color: {_WARNING_ORANGE}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};"
            )
            return None
        return True

    def _fm_on_model_changed(self, idx):
        previous = db.get_setting("insightface_model_name", "buffalo_l") or "buffalo_l"
        sel = self._fm_buffalo_combo.itemData(idx) or "buffalo_l"
        download_missing = self._fm_confirm_download_if_missing(sel)
        if download_missing is None:
            self._fm_select_model_key(previous)
            return
        db.set_setting("insightface_model_name", sel)
        if hasattr(self, "_fm_reload_timer") and self._fm_reload_timer is not None:
            self._fm_reload_timer.stop()
        self._fm_force_reload(download_missing=download_missing)

    def _fm_save_only(self):
        self._fm_save_and_reload()

    def _fm_save_and_reload(self):
        db.set_setting("insightface_model_dir", self._fm_model_path.text().strip())
        selected = self._fm_buffalo_combo.currentData() or "buffalo_l"
        download_missing = self._fm_confirm_download_if_missing(selected)
        if download_missing is None:
            return
        db.set_setting("insightface_model_name", selected)
        self._fm_force_reload(download_missing=download_missing)

    def _fm_force_reload(self, download_missing: bool = False):
        db.set_setting("insightface_model_dir", self._fm_model_path.text().strip())
        db.set_setting("insightface_model_name", self._fm_buffalo_combo.currentData() or "buffalo_l")
        self._fm_reload_model(force=True, download_missing=download_missing)

    def _fm_mark_restart_pending(self, message: str) -> None:
        self._fm_model_status.setText(f"\u25cf {message}")
        self._fm_model_status.setStyleSheet(
            f"color: {_WARNING_ORANGE}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};"
        )

    def _fm_browse_path(self):
        folder = QFileDialog.getExistingDirectory(self, "Select InsightFace Model Root Folder", self._fm_model_path.text() or ".")
        if folder:
            self._fm_model_path.setText(folder)

    def _start_fm_header_spinner(self) -> None:
        base_icon = QPixmap("frontend/assets/icons/loading.png")
        if base_icon.isNull() or not hasattr(self, "_fm_loading_icon_lbl"):
            return

        self._stop_fm_header_spinner()
        angle = 0

        def _render_frame() -> None:
            rotated = base_icon.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self._fm_loading_icon_lbl.setPixmap(
                rotated.scaled(
                    16,
                    16,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        def _tick() -> None:
            nonlocal angle
            angle = (angle + 18) % 360
            _render_frame()

        _render_frame()
        self._fm_loading_icon_lbl.setVisible(True)
        self._fm_header_spin_timer = QTimer(self)
        self._fm_header_spin_timer.setInterval(40)
        self._fm_header_spin_timer.timeout.connect(_tick)
        self._fm_header_spin_timer.start()

    def _stop_fm_header_spinner(self) -> None:
        timer = getattr(self, "_fm_header_spin_timer", None)
        if timer is not None:
            timer.stop()
            self._fm_header_spin_timer = None
        if hasattr(self, "_fm_loading_icon_lbl"):
            self._fm_loading_icon_lbl.clear()
            self._fm_loading_icon_lbl.setVisible(False)

    def _start_fm_button_spinner(self) -> None:
        base_icon = QPixmap("frontend/assets/icons/loading.png")
        if base_icon.isNull():
            return

        self._stop_fm_button_spinner()
        angle = 0

        def _render_frame() -> None:
            rotated = base_icon.transformed(QTransform().rotate(angle), Qt.TransformationMode.SmoothTransformation)
            self._fm_save_reload_btn.setIcon(
                QIcon(
                    rotated.scaled(
                        14,
                        14,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
            )

        def _tick() -> None:
            nonlocal angle
            angle = (angle + 18) % 360
            _render_frame()

        _render_frame()
        self._fm_btn_spin_timer = QTimer(self)
        self._fm_btn_spin_timer.setInterval(40)
        self._fm_btn_spin_timer.timeout.connect(_tick)
        self._fm_btn_spin_timer.start()

    def _stop_fm_button_spinner(self) -> None:
        timer = getattr(self, "_fm_btn_spin_timer", None)
        if timer is not None:
            timer.stop()
            self._fm_btn_spin_timer = None
        self._fm_save_reload_btn.setIcon(QIcon())

    def _fm_reload_model(self, force: bool = False, download_missing: bool = False):
        if getattr(self, "_fm_reload_busy", False):
            return
        self._fm_reload_busy = True

        old = getattr(self, "_fm_load_worker", None)
        if old is not None and old.isRunning():
            old.quit()
            old.wait(800)

        path = self._fm_model_path.text().strip() or ""
        self._start_fm_header_spinner()
        self._fm_model_status.setText("Downloading and applying…" if download_missing else "Applying — cameras will pause…")
        self._fm_model_status.setStyleSheet(
            f"color: {_WARNING_ORANGE}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};"
        )
        self._fm_save_reload_btn.setEnabled(False)
        self._fm_save_reload_btn.setText("Applying…")
        self._start_fm_button_spinner()
        model_name = self._fm_buffalo_combo.currentData() or "buffalo_l"

        from PySide6.QtCore import QThread, Signal as _Signal

        _force = force

        class _FMLoadWorker(QThread):
            finished = _Signal(bool, str)

            def __init__(self, p, force_reload, name, do_download):
                super().__init__()
                self._path = p
                self._force = force_reload
                self._name = name
                self._do_download = do_download

            def run(self):
                active_ids = []
                mgr = None
                try:
                    from backend.models.face_model import download_insightface_model_pack, is_insightface_model_installed
                    from backend.models import model_loader
                    from backend.camera.camera_manager import get_camera_manager

                    mgr = get_camera_manager()
                    active_ids = mgr.get_active_ids()
                    if active_ids:
                        mgr.stop_all()
                    if self._do_download and not is_insightface_model_installed(self._name, self._path):
                        download_insightface_model_pack(self._name, self._path)
                    fm = model_loader.reload_face_model(self._path, cpu_only=True)
                    self.finished.emit(fm.is_loaded, "")
                except Exception as exc:
                    self.finished.emit(False, str(exc))
                finally:
                    if mgr is not None:
                        for cid in active_ids:
                            try:
                                mgr.start_camera(cid)
                            except Exception:
                                pass

        worker = _FMLoadWorker(path, _force, model_name, download_missing)
        _FM_LOAD_WORKERS.add(worker)
        self._fm_load_worker = worker

        if hasattr(self, "_fm_progress") and self._fm_progress is not None:
            with contextlib.suppress(Exception):
                self._fm_progress.close()
        progress_label = "Downloading and applying InsightFace model\u2026" if download_missing else "Applying InsightFace model\u2026"
        self._fm_progress = QProgressDialog(progress_label, None, 0, 0, self)
        self._fm_progress.setWindowTitle("Loading")
        self._apply_loading_icon(self._fm_progress)
        self._fm_progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        self._fm_progress.setCancelButton(None)
        self._fm_progress.setMinimumDuration(0)
        self._fm_progress.show()

        def _on_done(ok, err):
            self._fm_reload_busy = False
            with contextlib.suppress(Exception):
                self._fm_progress.close()
                self._fm_progress = None
            self._fm_save_reload_btn.setEnabled(True)
            self._fm_save_reload_btn.setText("Save")
            self._stop_fm_button_spinner()
            self._stop_fm_header_spinner()
            if ok:
                from backend.models.model_loader import get_face_model

                fm = get_face_model()
                providers_str = ", ".join(p.replace("ExecutionProvider", "") for p in (fm.providers_used or [])) or "CPU"
                self._fm_model_status.setText(f"\u25cf {model_name} applied for this session - {providers_str}")
                self._fm_model_status.setStyleSheet(
                    f"color: {_SUCCESS}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};"
                )
            else:
                msg = f"\u25cf Error \u2014 {err}" if err else "\u25cf Not loaded"
                self._fm_model_status.setText(msg)
                self._fm_model_status.setStyleSheet(
                    f"color: {_DANGER}; font-size: {FONT_SIZE_LABEL}px; font-weight: {FONT_WEIGHT_SEMIBOLD};"
                )

        worker.finished.connect(_on_done)
        worker.finished.connect(lambda *_args, w=worker: _FM_LOAD_WORKERS.discard(w))
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _fm_detect_gpu(self):
        parts = []
        prov_names = []
        try:
            import onnxruntime as ort

            avail = ort.get_available_providers()
            prov_names = [p.replace("ExecutionProvider", "") for p in avail]
            parts.append("ONNX: " + ", ".join(prov_names))
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            parts.append(f"ONNX: error ({exc})")
        gpu_found = bool(prov_names) and any("CUDA" in p or "Dml" in p or "ROCm" in p for p in prov_names)
        self._fm_gpu_label.setText(" | ".join(parts))
        from ._constants import _SUCCESS_DIM, _TEXT_MUTED as _TM

        color = _SUCCESS_DIM if gpu_found else _TM
        self._fm_gpu_label.setStyleSheet(f"color: {color}; font-size: {FONT_SIZE_CAPTION}px;")

