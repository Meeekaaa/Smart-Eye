from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QPoint, Qt, QTimer
from PySide6.QtGui import QRegion
from PySide6.QtWidgets import QApplication, QComboBox, QFrame
from shiboken6 import isValid as _qt_object_is_valid


def _qt_widget_is_alive(widget) -> bool:
    try:
        return bool(widget is not None and _qt_object_is_valid(widget))
    except RuntimeError:
        return False


class _ComboPopupEnhancer(QObject):
    def __init__(self, app: QApplication):
        super().__init__(app)
        self._app = app

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Show and isinstance(obj, QFrame):
            combo = self._resolve_combo_owner(obj)
            if combo is not None and bool(obj.windowFlags() & Qt.WindowType.Popup):
                QTimer.singleShot(0, lambda o=obj, c=combo: self._enhance_popup(o, c))
        return super().eventFilter(obj, event)

    @staticmethod
    def _resolve_combo_owner(popup: QFrame) -> QComboBox | None:
        parent = popup.parentWidget()
        # Walk up the parent chain to find the originating QComboBox. Some
        # combos live deep inside nested layouts/scrollareas, so allow a
        # generous traversal depth.
        hops = 0
        max_hops = 50
        while parent is not None and hops < max_hops:
            if isinstance(parent, QComboBox):
                return parent
            parent = parent.parentWidget()
            hops += 1
        return None

    def _enhance_popup(self, popup: QFrame, combo: QComboBox) -> None:
        if not _qt_widget_is_alive(popup) or not _qt_widget_is_alive(combo):
            return

        try:
            target_width = max(combo.width(), self._popup_content_width(combo) + 4)
            popup.setMinimumWidth(target_width)
            popup.resize(max(popup.width(), target_width), popup.height())

            screen_geom = combo.screen().availableGeometry() if combo.screen() else self._app.primaryScreen().availableGeometry()
            gap = 4

            below = combo.mapToGlobal(QPoint(0, combo.height() + gap))
            x = below.x()
            y = below.y()

            if y + popup.height() > screen_geom.bottom():
                above = combo.mapToGlobal(QPoint(0, -popup.height() - gap))
                y = max(screen_geom.top(), above.y())

            max_width = max(220, screen_geom.width() - 12)
            if popup.width() > max_width:
                popup.resize(max_width, popup.height())

            if x + popup.width() > screen_geom.right() - 6:
                x = max(screen_geom.left() + 6, screen_geom.right() - popup.width() - 6)
            x = max(screen_geom.left() + 6, x)

            popup.move(x, y)
            popup.setMask(QRegion(0, 0, popup.width(), popup.height()))
            popup.setWindowOpacity(1.0)
        except RuntimeError:
            return

    @staticmethod
    def _popup_content_width(combo: QComboBox) -> int:
        if not _qt_widget_is_alive(combo):
            return 0
        view = combo.view()
        model = combo.model()
        if view is None or model is None:
            return combo.width()

        col_width = 0
        with_col_hint = getattr(view, "sizeHintForColumn", None)
        if callable(with_col_hint):
            try:
                col_width = max(0, int(with_col_hint(combo.modelColumn())))
            except Exception:
                col_width = 0

        if col_width <= 0:
            metrics = combo.fontMetrics()
            for i in range(model.rowCount()):
                text = combo.itemText(i)
                col_width = max(col_width, metrics.horizontalAdvance(text))

        icon_space = 24 if combo.iconSize().width() > 0 else 0
        scrollbar_space = 18
        paddings = 36
        return col_width + icon_space + scrollbar_space + paddings


def setup_combobox_popup_behavior(app: QApplication) -> None:
    enhancer = _ComboPopupEnhancer(app)
    app.installEventFilter(enhancer)
    app.setProperty("_combo_popup_enhancer", enhancer)
