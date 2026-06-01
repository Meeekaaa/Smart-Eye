from __future__ import annotations

import contextlib
import logging
import os

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QProgressBar,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from backend.repository import db
from frontend.dialogs import apply_popup_theme

from ._constants import _STYLESHEET, _TEXT_MUTED, _TEXT_SEC, _PRIMARY_BTN
from ._enroll_panel import _EnrollPanelMixin
from ._ui_builder import build_page_ui
from ._widgets import RosterRowWidget
from frontend.styles._btn_styles import _SECONDARY_BTN
from frontend.styles._colors import _ACCENT_BG_22, _ACCENT_HI, _DANGER, _MUTED_BG_25, _SUCCESS
from frontend.styles.page_styles import divider_style, muted_label_style, text_style
from frontend.ui_tokens import (
    FONT_SIZE_15,
    FONT_SIZE_9,
    FONT_SIZE_BODY,
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_SIZE_SUBHEAD,
    FONT_SIZE_XL,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_HEAVY,
    RADIUS_5,
    RADIUS_6,
    RADIUS_MD,
    RADIUS_SM,
    SIZE_BADGE_H,
    SIZE_CONTROL_MD,
    SIZE_BTN_W_LG,
    SIZE_DIALOG_H_360,
    SIZE_DIALOG_W_500,
    SIZE_IMAGE_240,
    SIZE_LABEL_W_50,
    SIZE_PANEL_MAX,
    SIZE_ROW_72,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_5,
    SPACE_LG,
    SPACE_MD,
    SPACE_XL,
    SPACE_XXL,
    SPACE_XXS,
    SPACE_XXXS,
)

logger = logging.getLogger(__name__)
_RETIRED_IMPORT_WORKERS: set[QThread] = set()
_COUNT_BADGE_ACTIVE_STYLE = (
    f"background: {_ACCENT_BG_22}; color: {_ACCENT_HI}; "
    f"border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px; "
    f"font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;"
)
_COUNT_BADGE_INACTIVE_STYLE = (
    f"background: {_MUTED_BG_25}; color: {_TEXT_MUTED}; "
    f"border-radius: {RADIUS_MD}px; padding: 0 {SPACE_5}px; "
    f"font-size: {FONT_SIZE_9}px; font-weight: {FONT_WEIGHT_HEAVY}; min-width: {SPACE_LG}px;"
)
_EMPTY_TITLE_STYLE = text_style(_TEXT_SEC, size=FONT_SIZE_BODY, weight=FONT_WEIGHT_BOLD)
_EMPTY_SUB_STYLE = muted_label_style(size=FONT_SIZE_CAPTION)


class FaceManagerPage(_EnrollPanelMixin, QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(_STYLESHEET)
        self._all_faces: list[dict] = []
        self._inbox: list[dict] = []
        self._inbox_view: list[dict] = []
        self._active_face_id: int | None = None
        self._worker = None
        self._single_import_worker = None
        self._batch_import_worker = None
        self._row_widgets: dict[int, RosterRowWidget] = {}
        self._active_filter: str = "all"
        self._tab_counts: dict[str, QLabel] = {}
        self._inbox_panel = None
        build_page_ui(self)

    def _set_filter(self, key: str):
        self._active_filter = key
        for k, btn in self._tab_buttons.items():
            btn.setChecked(k == key)
        self._update_tab_count_styles()
        self._apply_filter_and_search()

    def _update_tab_count_styles(self):
        for key, lbl in self._tab_counts.items():
            if self._tab_buttons[key].isChecked():
                lbl.setStyleSheet(_COUNT_BADGE_ACTIVE_STYLE)
            else:
                lbl.setStyleSheet(_COUNT_BADGE_INACTIVE_STYLE)

    def on_activated(self):
        self._refresh()

    def on_deactivated(self):
        self._cleanup_import_workers()
        self._detail_panel.clear()
        self._render_roster([])
        with contextlib.suppress(Exception):
            self._close_enroll_panel()
        with contextlib.suppress(Exception):
            self._close_inbox_panel()

    def on_unload(self):
        self._cleanup_import_workers()
        self._detail_panel.clear()
        self._render_roster([])
        with contextlib.suppress(Exception):
            self._close_enroll_panel()
        with contextlib.suppress(Exception):
            self._close_inbox_panel()

    def _cleanup_import_workers(self) -> None:
        for attr in ("_single_import_worker", "_batch_import_worker"):
            worker = getattr(self, attr, None)
            if worker is None:
                continue
            setattr(self, attr, None)
            with contextlib.suppress(Exception):
                worker.progress.disconnect()
            with contextlib.suppress(Exception):
                worker.finished.disconnect()
            with contextlib.suppress(Exception):
                worker.cancel()
            if worker.isRunning():
                worker.setParent(None)
                _RETIRED_IMPORT_WORKERS.add(worker)

                def _cleanup(*_args, w=worker):
                    _RETIRED_IMPORT_WORKERS.discard(w)
                    with contextlib.suppress(Exception):
                        w.deleteLater()

                worker.finished.connect(_cleanup)
            else:
                with contextlib.suppress(Exception):
                    worker.deleteLater()

    def _refresh(self):
        self._all_faces = db.get_faces()
        with contextlib.suppress(Exception):
            self._inbox = db.get_face_inbox()
        self._inbox_view = [self._map_inbox_face(f) for f in self._inbox]
        self._apply_filter_and_search()

        total = len(self._all_faces)
        authorized = sum(1 for f in self._all_faces if f.get("authorized_cameras", "[]") != "[]")
        restricted = total - authorized
        inbox_cnt = len(self._inbox)

        self._tab_counts["all"].setText(str(total))
        self._tab_counts["authorized"].setText(str(authorized))
        self._tab_counts["restricted"].setText(str(restricted))
        self._tab_counts["inbox"].setText(str(inbox_cnt))
        self._update_tab_count_styles()

        if self._active_face_id is not None:
            face = next((f for f in self._all_faces if f["id"] == self._active_face_id), None)
            if face:
                self._detail_panel.load_face(face)
            else:
                self._active_face_id = None
                self._detail_panel.clear()
        if self._active_filter == "inbox":
            self._close_inbox_panel()

    def _apply_filter_and_search(self):
        search_text = self._search_edit.text().lower().strip()
        faces = self._all_faces
        if self._active_filter == "inbox":
            faces = self._inbox_view
        if self._active_filter == "authorized":
            faces = [f for f in faces if f.get("authorized_cameras", "[]") != "[]"]
        elif self._active_filter == "restricted":
            faces = [f for f in faces if f.get("authorized_cameras", "[]") == "[]"]
        if search_text:
            faces = [f for f in faces if search_text in f.get("name", "").lower() or search_text in (f.get("department") or "").lower()]
        self._render_roster(faces)

    def _render_roster(self, faces: list):
        self._row_widgets.clear()
        while self._roster_vbox.count():
            item = self._roster_vbox.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not faces:
            empty_w = QWidget()
            empty_w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            empty_w.setStyleSheet("background: transparent; border: none;")
            from PySide6.QtWidgets import QVBoxLayout as _VL

            el = _VL(empty_w)
            el.setAlignment(Qt.AlignmentFlag.AlignCenter)
            el.setSpacing(SPACE_10)
            el.setContentsMargins(SPACE_LG, SPACE_XXL, SPACE_LG, SPACE_XXL)

            has_search = bool(self._search_edit.text().strip())
            title = QLabel("No results" if has_search else "No faces enrolled")
            title.setAlignment(Qt.AlignmentFlag.AlignCenter)
            title.setStyleSheet(_EMPTY_TITLE_STYLE)
            el.addWidget(title)

            sub = QLabel("Try a different search term." if has_search else "Enroll a person or import a folder to get started.")
            sub.setWordWrap(True)
            sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
            sub.setStyleSheet(_EMPTY_SUB_STYLE)
            el.addWidget(sub)

            self._roster_vbox.addWidget(empty_w)
            return

        for face in faces:
            is_active = face["id"] == self._active_face_id
            row = RosterRowWidget(face, is_active=is_active)
            row.clicked.connect(self._on_roster_row_clicked)
            row.enabled_toggled.connect(self._on_face_enabled_toggled)
            self._roster_vbox.addWidget(row)
            self._row_widgets[face["id"]] = row


        self._roster_vbox.addStretch(1)

    def _on_roster_row_clicked(self, face_id: int):
        self._active_face_id = face_id
        if self._active_filter == "inbox":
            face = next((f for f in self._inbox if f["id"] == face_id), None)
            if face:
                self._show_inbox_panel(face)
        else:
            self._close_inbox_panel()
            self._right_stack.setCurrentIndex(0)
            face = next((f for f in self._all_faces if f["id"] == face_id), None)
            if face:
                self._detail_panel.load_face(face)
        self._update_roster_active_state()

    def _close_details(self):
        self._active_face_id = None
        self._detail_panel.clear()
        self._update_roster_active_state()
        self._close_inbox_panel()

    def _save_face_details(self, face_id: int, updates: dict):
        db.update_face(face_id, **updates)
        self._refresh()

    def _update_roster_active_state(self):
        for fid, row_widget in self._row_widgets.items():
            if row_widget.parent():
                idx = self._roster_vbox.indexOf(row_widget)
                if idx >= 0:
                    face = next(
                        (f for f in (self._inbox_view if self._active_filter == "inbox" else self._all_faces) if f["id"] == fid), None
                    )
                    if face:
                        new_row = RosterRowWidget(face, is_active=(fid == self._active_face_id))
                        new_row.clicked.connect(self._on_roster_row_clicked)
                        if self._active_filter != "inbox":
                            new_row.enabled_toggled.connect(self._on_face_enabled_toggled)
                        self._roster_vbox.replaceWidget(row_widget, new_row)
                        row_widget.deleteLater()
                        self._row_widgets[fid] = new_row

    def _filter_faces(self, text: str):
        self._apply_filter_and_search()

    def _edit_face(self, face_id: int):
        from ._dialogs import show_edit_face_dialog

        show_edit_face_dialog(self, face_id)
        self._refresh()

    def _delete_face(self, face_id: int):
        db.delete_face(face_id)
        if self._active_face_id == face_id:
            self._active_face_id = None
            self._detail_panel.clear()
        self._refresh()
        try:
            from backend.models.model_loader import get_face_model

            fm = get_face_model()
            if fm is not None:
                fm.invalidate_known_cache()
        except (ImportError, RuntimeError, OSError):
            logger.warning("Failed to invalidate known face cache after delete face_id=%s", face_id, exc_info=True)

    def _delete_inbox(self, face_id: int):
        db.delete_face_inbox(face_id)
        if self._active_face_id == face_id:
            self._active_face_id = None
            self._close_inbox_panel()
        self._refresh()

    def _on_face_enabled_toggled(self, face_id: int, enabled: bool):
        db.update_face(face_id, enabled=int(enabled))
        try:
            from backend.models.model_loader import get_face_model

            fm = get_face_model()
            if fm is not None:
                fm.invalidate_known_cache()
        except (ImportError, RuntimeError, OSError):
            logger.warning("Failed to invalidate known face cache after toggle face_id=%s", face_id, exc_info=True)
        self._refresh()

    def _show_inbox_panel(self, face: dict):
        if self._inbox_panel is not None:
            self._right_stack.removeWidget(self._inbox_panel)
            self._inbox_panel.deleteLater()
        panel = QWidget()
        root = QVBoxLayout(panel)
        root.setContentsMargins(SPACE_20, SPACE_20, SPACE_20, SPACE_20)
        root.setSpacing(SPACE_10)

        top_row = QHBoxLayout()
        top_row.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setFixedHeight(SIZE_BADGE_H)
        from ._constants import _DANGER_BTN
        from frontend.styles._btn_styles import _TEXT_BTN_BLUE

        close_btn.setStyleSheet(_TEXT_BTN_BLUE)
        close_btn.clicked.connect(self._close_inbox_panel)
        top_row.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)
        root.addLayout(top_row)

        img = QLabel()
        img.setFixedSize(SIZE_IMAGE_240, SIZE_IMAGE_240)
        img.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pix = QPixmap(face.get("image_path", ""))
        if not pix.isNull():
            img.setPixmap(
                pix.scaled(SIZE_IMAGE_240, SIZE_IMAGE_240, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            )
        root.addWidget(img, alignment=Qt.AlignmentFlag.AlignCenter)

        self._inbox_name = QLineEdit(face.get("temp_name") or "Unlabeled")
        self._inbox_name.setPlaceholderText("Name")
        root.addWidget(self._inbox_name)

        self._inbox_dept = QLineEdit()
        self._inbox_dept.setPlaceholderText("Department")
        root.addWidget(self._inbox_dept)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACE_10)
        add_btn = QPushButton("Add to faces")
        add_btn.setStyleSheet(_PRIMARY_BTN)
        add_btn.clicked.connect(lambda: self._assign_inbox(face))
        btn_row.addWidget(add_btn)

        del_btn = QPushButton("Discard")
        del_btn.setStyleSheet(_DANGER_BTN)
        del_btn.clicked.connect(lambda: self._delete_inbox(face.get("id")))
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self._inbox_panel = panel
        self._right_stack.addWidget(panel)
        self._right_stack.setCurrentWidget(panel)

    def _close_inbox_panel(self):
        if self._inbox_panel is not None:
            self._right_stack.removeWidget(self._inbox_panel)
            self._inbox_panel.deleteLater()
            self._inbox_panel = None
        self._right_stack.setCurrentIndex(0)

    def _assign_inbox(self, face: dict):
        name = self._inbox_name.text().strip() if hasattr(self, "_inbox_name") else ""
        dept = self._inbox_dept.text().strip() if hasattr(self, "_inbox_dept") else ""
        emb = face.get("embedding")
        if isinstance(emb, memoryview):
            emb = emb.tobytes()
        if emb is None:
            return
        if hasattr(emb, "tobytes"):
            try:
                emb = emb.tobytes()
            except (TypeError, ValueError):
                logger.warning("Failed to convert embedding to bytes for inbox face id=%s", face.get("id"), exc_info=True)
        from utils.embedding_utils import embedding_to_bytes

        emb_model = face.get("embedding_model", "") or ""
        if not emb_model:
            with contextlib.suppress(Exception):
                from backend.models.model_loader import get_face_model

                fm = get_face_model()
                if fm and getattr(fm, "model_name", ""):
                    emb_model = fm.model_name
        try:
            emb_bytes = embedding_to_bytes(emb) if not isinstance(emb, (bytes, bytearray)) else bytes(emb)
        except (TypeError, ValueError):
            return
        new_id = db.add_known_face(
            name=name or "Unknown",
            role="",
            department=dept,
            embedding_bytes=emb_bytes,
            image_path=face.get("image_path", ""),
            embedding_model=emb_model,
            gender="unknown",
        )
        db.delete_face_inbox(face.get("id"))
        with contextlib.suppress(Exception):
            from backend.models.model_loader import get_face_model

            fm = get_face_model()
            if fm is not None:
                fm.invalidate_known_cache()
        self._active_face_id = new_id
        self._close_inbox_panel()
        self._refresh()

    def _map_inbox_face(self, row: dict) -> dict:
        emb = row.get("embedding")
        if isinstance(emb, memoryview):
            emb = emb.tobytes()
        emb_model = row.get("embedding_model", "")
        if not emb_model:
            with contextlib.suppress(Exception):
                from backend.models.model_loader import get_face_model

                fm = get_face_model()
                if fm and getattr(fm, "model_name", ""):
                    emb_model = fm.model_name
        return {
            "id": row.get("id"),
            "name": row.get("temp_name") or "Unlabeled",
            "department": "",
            "authorized_cameras": "[]",
            "enabled": 1,
            "image_path": row.get("image_path", ""),
            "uuid": "",
            "embedding_model": emb_model,
            "embedding": emb,
        }

    def _import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder to Import")
        if not folder:
            return

        entries = os.listdir(folder)
        has_subdirs = any(os.path.isdir(os.path.join(folder, e)) for e in entries)
        supported_ext = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        has_images = any(os.path.splitext(e)[1].lower() in supported_ext for e in entries)

        from ._constants import (
            _BG_RAISED,
            _BG_OVERLAY,
            _BORDER_DIM,
            _TEXT_PRI,
            _TEXT_SEC,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Import Mode")
        dlg.setModal(True)
        dlg.setMinimumWidth(SIZE_PANEL_MAX)
        from ._constants import _STYLESHEET

        apply_popup_theme(dlg, _STYLESHEET)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(SPACE_XL, SPACE_20, SPACE_XL, SPACE_20)
        vl.setSpacing(SPACE_14)

        title = QLabel("How do you want to import?")
        title.setStyleSheet(text_style(_TEXT_PRI, size=FONT_SIZE_SUBHEAD, weight=FONT_WEIGHT_BOLD))
        vl.addWidget(title)

        desc = QLabel(
            f"Selected: <b>{os.path.basename(folder)}</b><br>"
            + (f"<span style='color:{_ACCENT_HI}'>⊞ Contains sub-folders</span>  " if has_subdirs else "")
            + (f"<span style='color:{_SUCCESS}'>⊞ Contains images</span>" if has_images else "")
        )
        desc.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_LABEL))
        desc.setWordWrap(True)
        vl.addWidget(desc)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(divider_style(_BORDER_DIM))
        vl.addWidget(sep)

        def _card(icon, title_txt, body_txt):
            btn = QPushButton()
            btn.setFixedHeight(SIZE_ROW_72)
            btn.setStyleSheet(
                """
                QPushButton {{
                    background:{bg}; border:{bw}px solid {border};
                    border-radius:{radius}px; text-align:left; padding:0 {pad}px;
                }}
                QPushButton:hover {{
                    background:{hover_bg}; border-color:{accent};
                }}
                """.format(
                    bg=_BG_RAISED,
                    bw=SPACE_XXXS,
                    border=_BORDER_DIM,
                    radius=RADIUS_MD,
                    pad=SPACE_14,
                    hover_bg=_BG_OVERLAY,
                    accent=_ACCENT_HI,
                )
            )
            inner = QHBoxLayout(btn)
            inner.setContentsMargins(SPACE_MD, 0, SPACE_MD, 0)
            inner.setSpacing(SPACE_14)
            ico = QLabel(icon)
            ico.setStyleSheet(text_style(_ACCENT_HI, size=FONT_SIZE_XL, extra="background:transparent; border:none;"))
            inner.addWidget(ico)
            txt_w = QWidget()
            txt_w.setStyleSheet("background:transparent;")
            txt_l = QVBoxLayout(txt_w)
            txt_l.setContentsMargins(0, 0, 0, 0)
            txt_l.setSpacing(SPACE_XXS)
            t = QLabel(title_txt)
            t.setStyleSheet(text_style(_TEXT_PRI, size=FONT_SIZE_BODY, weight=FONT_WEIGHT_BOLD, extra="background:transparent;"))
            b = QLabel(body_txt)
            b.setStyleSheet(muted_label_style(size=FONT_SIZE_CAPTION) + " background:transparent;")
            txt_l.addWidget(t)
            txt_l.addWidget(b)
            inner.addWidget(txt_w, stretch=1)
            return btn

        single_btn = _card(
            "\U0001f9d1",
            "Single Person",
            "Folder contains images of ONE person — each file → one face entry",
        )
        batch_btn = _card(
            "\U0001f465",
            "Batch Import  (multiple people)",
            "Folder contains sub-folders, each named after a person",
        )
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        cancel_btn.setStyleSheet(_SECONDARY_BTN)

        vl.addWidget(single_btn)
        vl.addWidget(batch_btn)
        vl.addWidget(cancel_btn)

        _choice = [None]

        def _pick_single():
            _choice[0] = "single"
            dlg.accept()

        def _pick_batch():
            _choice[0] = "batch"
            dlg.accept()

        single_btn.clicked.connect(_pick_single)
        batch_btn.clicked.connect(_pick_batch)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

        if _choice[0] == "single":
            self._import_single_person(folder)
        elif _choice[0] == "batch":
            self._import_batch(folder)

    def _import_single_person(self, folder: str):
        from backend.models.model_loader import get_face_model

        model = get_face_model()
        if model is None or not model.is_loaded:
            QMessageBox.warning(
                self,
                "Model Not Loaded",
                "The face recognition model is not loaded.\nImages will be stored without recognition capability.",
            )
            return

        supported = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        files = [f for f in os.listdir(folder) if os.path.splitext(f)[1].lower() in supported]
        if not files:
            QMessageBox.information(
                self,
                "No Images",
                "No supported image files found in the selected folder.",
            )
            return

        if self._single_import_worker is not None and self._single_import_worker.isRunning():
            QMessageBox.information(self, "Import Running", "A face import is already running.")
            return

        progress = QProgressDialog("Importing face images...", "Cancel", 0, len(files), self)
        progress.setWindowTitle("Import Faces")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        worker = _SinglePersonImportWorker(folder, files)
        self._single_import_worker = worker

        def _on_progress(done: int, message: str):
            progress.setValue(done)
            progress.setLabelText(message)

        def _on_done(ok: bool, msg: str):
            self._single_import_worker = None
            progress.close()
            worker.deleteLater()
            if ok:
                QMessageBox.information(self, "Import Results", msg)
                self._refresh()
                with contextlib.suppress(Exception):
                    from backend.models.model_loader import get_face_model

                    fm = get_face_model()
                    if fm:
                        fm.invalidate_known_cache()
            else:
                QMessageBox.warning(self, "Import Failed", msg)

        progress.canceled.connect(worker.cancel)
        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_done)
        worker.start()
        progress.show()

    def _import_batch(self, folder: str):
        from ._constants import (
            _BG_RAISED,
            _BORDER_DIM,
            _TEXT_PRI,
            _TEXT_SEC,
            _ACCENT,
            _STYLESHEET,
        )

        dlg = QDialog(self)
        dlg.setWindowTitle("Batch Import Progress")
        dlg.setModal(True)
        dlg.setMinimumWidth(SIZE_DIALOG_W_500)
        dlg.setMinimumHeight(SIZE_DIALOG_H_360)
        apply_popup_theme(dlg, _STYLESHEET)

        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(SPACE_XL, SPACE_20, SPACE_XL, SPACE_20)
        vl.setSpacing(SPACE_MD)

        hdr = QLabel("Batch Face Import")
        hdr.setStyleSheet(text_style(_TEXT_PRI, size=FONT_SIZE_15, weight=FONT_WEIGHT_BOLD))
        vl.addWidget(hdr)

        sub = QLabel(f"Importing from: {folder}")
        sub.setStyleSheet(text_style(_TEXT_SEC, size=FONT_SIZE_CAPTION))
        sub.setWordWrap(True)
        vl.addWidget(sub)

        prog_row = QHBoxLayout()
        prog_bar = QProgressBar()
        prog_bar.setRange(0, 100)
        prog_bar.setValue(0)
        prog_bar.setFixedHeight(SPACE_10)
        prog_bar.setTextVisible(False)
        prog_bar.setStyleSheet(
            """
            QProgressBar {{ background:{bg}; border:{bw}px solid {border};
                           border-radius:{radius}px; }}
            QProgressBar::chunk {{ background:{accent}; border-radius:{chunk_radius}px; }}
            """.format(
                bg=_BG_RAISED,
                bw=SPACE_XXXS,
                border=_BORDER_DIM,
                radius=RADIUS_5,
                accent=_ACCENT,
                chunk_radius=RADIUS_SM,
            )
        )
        prog_lbl = QLabel("Starting…")
        prog_lbl.setStyleSheet(muted_label_style(size=FONT_SIZE_CAPTION) + f" min-width:{SIZE_LABEL_W_50}px;")
        prog_row.addWidget(prog_bar, stretch=1)
        prog_row.addWidget(prog_lbl)
        vl.addLayout(prog_row)

        log = QTextEdit()
        log.setReadOnly(True)
        log.setStyleSheet(
            f"background:{_BG_RAISED}; border:{SPACE_XXXS}px solid {_BORDER_DIM};"
            f"border-radius:{RADIUS_6}px; font-family:Consolas,monospace; font-size:{FONT_SIZE_CAPTION}px;"
            f"color:{_TEXT_SEC};"
        )
        vl.addWidget(log, stretch=1)

        worker = _BatchImportWorker(folder)
        self._batch_import_worker = worker
        done_state = {"done": False}

        close_btn = QPushButton("Cancel")
        close_btn.setFixedSize(SIZE_BTN_W_LG, SIZE_CONTROL_MD)
        close_btn.setStyleSheet(_SECONDARY_BTN)

        def _cancel_or_close():
            if done_state["done"]:
                dlg.accept()
                return
            worker.cancel()
            close_btn.setEnabled(False)
            log.append("Canceling import...")

        close_btn.clicked.connect(_cancel_or_close)
        close_row = QHBoxLayout()
        close_row.addStretch()
        close_row.addWidget(close_btn)
        vl.addLayout(close_row)

        def _on_progress(pct, msg):
            prog_bar.setValue(pct)
            prog_lbl.setText(f"{pct}%")
            log.append(msg)

        def _on_done(ok, msg):
            done_state["done"] = True
            self._batch_import_worker = None
            close_btn.setEnabled(True)
            close_btn.setText("Close")
            color = _SUCCESS if ok else _DANGER
            log.append(f"<span style='color:{color}'><b>{'✓' if ok else '✗'} {msg}</b></span>")
            prog_bar.setValue(100 if ok else prog_bar.value())
            prog_lbl.setText("Done" if ok else "Failed")
            worker.deleteLater()
            if not ok:
                return
            self._refresh()
            try:
                from backend.models.model_loader import get_face_model

                fm = get_face_model()
                if fm:
                    fm.invalidate_known_cache()
            except (ImportError, RuntimeError, OSError):
                logger.warning("Failed to invalidate known cache after batch import", exc_info=True)

        worker.progress.connect(_on_progress)
        worker.finished.connect(_on_done)
        worker.start()
        dlg.exec()


class _SinglePersonImportWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, folder: str, files: list[str], parent=None):
        super().__init__(parent)
        self._folder = folder
        self._files = files
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self):
        try:
            import cv2
            from backend.repository import db
            from backend.models.model_loader import get_face_model
            from utils.embedding_utils import embedding_to_bytes

            model = get_face_model()
            if model is None or not model.is_loaded:
                self.finished.emit(False, "Face model is not loaded.")
                return

            count, skipped = 0, 0
            total = max(1, len(self._files))
            for idx, fname in enumerate(self._files, 1):
                if self._cancel_requested:
                    self.finished.emit(False, f"Import canceled. Imported {count} face(s), skipped {skipped}.")
                    return
                fpath = os.path.join(self._folder, fname)
                self.progress.emit(idx - 1, f"Processing {fname}...")
                img = cv2.imread(fpath)
                if img is None:
                    skipped += 1
                    self.progress.emit(idx, f"Skipped {fname} (unreadable)")
                    continue
                emb = model.get_embedding(img)
                if emb is None:
                    skipped += 1
                    self.progress.emit(idx, f"Skipped {fname} (no face detected)")
                    continue
                emb_bytes = embedding_to_bytes(emb)
                name = os.path.splitext(fname)[0].replace("_", " ").replace("-", " ").title()
                db.add_face(
                    name,
                    "",
                    emb_bytes,
                    fpath,
                    1,
                    "[]",
                    embedding_model=getattr(model, "model_name", "") or "",
                )
                count += 1
                self.progress.emit(idx, f"Imported {name} ({idx}/{total})")

            msg = f"Import complete.\n+ {count} faces imported."
            if skipped:
                msg += f"\n- {skipped} files skipped (no face detected or unreadable)."
            self.finished.emit(True, msg)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            logger.exception("Single-person face import failed")
            self.finished.emit(False, str(exc))


class _BatchImportWorker(QThread):
    progress = Signal(int, str)
    finished = Signal(bool, str)

    def __init__(self, folder: str, parent=None):
        super().__init__(parent)
        self._folder = folder
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True

    def run(self):
        try:
            import cv2
            from backend.repository import db
            from backend.models.model_loader import get_face_model
            from utils.embedding_utils import embedding_to_bytes, average_embeddings

            model = get_face_model()
            if model is None or not model.is_loaded:
                self.finished.emit(False, "Face model is not loaded.")
                return

            supported = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
            people = [d for d in os.listdir(self._folder) if os.path.isdir(os.path.join(self._folder, d))]
            if not people:
                self.finished.emit(
                    False,
                    "No sub-folders found. Each sub-folder should be named after a person.",
                )
                return

            total = len(people)
            count = 0
            skipped = 0
            for i, person_name in enumerate(people):
                if self._cancel_requested:
                    self.finished.emit(False, f"Import canceled. Enrolled {count} / {total} people.")
                    return
                person_dir = os.path.join(self._folder, person_name)
                embeddings = []
                photo_path = ""
                for fname in sorted(os.listdir(person_dir)):
                    if self._cancel_requested:
                        self.finished.emit(False, f"Import canceled. Enrolled {count} / {total} people.")
                        return
                    if os.path.splitext(fname)[1].lower() not in supported:
                        continue
                    fpath = os.path.join(person_dir, fname)
                    img = cv2.imread(fpath)
                    if img is None:
                        continue
                    emb = model.get_embedding(img)
                    if emb is not None:
                        embeddings.append(emb)
                        if not photo_path:
                            photo_path = fpath

                if embeddings:
                    avg_emb = average_embeddings(embeddings)
                    emb_bytes = embedding_to_bytes(avg_emb)
                    display_name = person_name.replace("_", " ").replace("-", " ").title()
                    db.add_face(
                        display_name,
                        "",
                        emb_bytes,
                        photo_path,
                        1,
                        "[]",
                        embedding_model=getattr(model, "model_name", "") or "",
                    )
                    count += 1
                    self.progress.emit(
                        int((i + 1) / total * 100),
                        f"+  {display_name}  ({len(embeddings)} image{'s' if len(embeddings) != 1 else ''})",
                    )
                else:
                    skipped += 1
                    self.progress.emit(
                        int((i + 1) / total * 100),
                        f"\u2212  {person_name}  (no faces detected — skipped)",
                    )

            msg = f"Enrolled {count} / {total} people."
            if skipped:
                msg += f"  {skipped} skipped (no faces detected)."
            self.finished.emit(True, msg)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
            logger.exception("Batch face import failed")
            self.finished.emit(False, str(exc))

