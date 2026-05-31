from __future__ import annotations

import contextlib
import weakref

from PySide6.QtCore import QEasingCurve, QEvent, QObject, QPropertyAnimation, Qt
from PySide6.QtWidgets import QAbstractButton, QGraphicsOpacityEffect
from shiboken6 import isValid


class PressAnimationFilter(QObject):
    def __init__(
        self,
        parent: QObject | None = None,
        *,
        press_opacity: float = 0.88,
        press_duration: int = 110,
        release_duration: int = 150,
    ) -> None:
        super().__init__(parent)
        self._press_opacity = press_opacity
        self._press_duration = press_duration
        self._release_duration = release_duration
        self._anims: weakref.WeakKeyDictionary[QAbstractButton, QPropertyAnimation] = weakref.WeakKeyDictionary()
        self._owns_effect: weakref.WeakKeyDictionary[QAbstractButton, bool] = weakref.WeakKeyDictionary()

    def eventFilter(self, obj, event):
        if not isinstance(obj, QAbstractButton):
            return False
        if not obj.isEnabled():
            return False
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            self._animate(obj, self._press_opacity, self._press_duration)
        elif etype == QEvent.Type.MouseButtonRelease:
            self._animate(obj, 1.0, self._release_duration)
        elif etype == QEvent.Type.KeyPress:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._animate(obj, self._press_opacity, self._press_duration)
        elif etype == QEvent.Type.KeyRelease:
            if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
                self._animate(obj, 1.0, self._release_duration)
        elif etype in (QEvent.Type.Leave, QEvent.Type.FocusOut):
            self._animate(obj, 1.0, self._release_duration)
        return False

    def _ensure_effect(self, btn: QAbstractButton) -> QGraphicsOpacityEffect | None:
        effect = btn.graphicsEffect()
        if effect is None:
            effect = QGraphicsOpacityEffect(btn)
            effect.setOpacity(1.0)
            btn.setGraphicsEffect(effect)
            self._owns_effect[btn] = True
        elif not isinstance(effect, QGraphicsOpacityEffect):
            return None
        return effect

    def _animate(self, btn: QAbstractButton, target: float, duration: int) -> None:
        effect = self._ensure_effect(btn)
        if effect is None:
            return
        anim = self._anims.pop(btn, None)
        if anim is not None and isValid(anim):
            with contextlib.suppress(RuntimeError):
                anim.stop()
                anim.deleteLater()
        anim = QPropertyAnimation(effect, b"opacity", btn)
        anim.setDuration(duration)
        anim.setStartValue(effect.opacity())
        anim.setEndValue(target)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda b=btn, e=effect, a=anim, t=target: self._animation_finished(b, e, a, t))
        anim.start()
        self._anims[btn] = anim

    def _animation_finished(
        self,
        btn: QAbstractButton,
        effect: QGraphicsOpacityEffect,
        anim: QPropertyAnimation,
        target: float,
    ) -> None:
        if self._anims.get(btn) is anim:
            self._anims.pop(btn, None)
        if target >= 0.999 and self._owns_effect.get(btn, False):
            self._cleanup_effect(btn, effect)
        if isValid(anim):
            anim.deleteLater()

    def _cleanup_effect(self, btn: QAbstractButton, effect: QGraphicsOpacityEffect) -> None:
        if isValid(btn) and isValid(effect) and btn.graphicsEffect() is effect:
            btn.setGraphicsEffect(None)
        self._owns_effect.pop(btn, None)
        self._anims.pop(btn, None)


_filter_instance: PressAnimationFilter | None = None


def install_press_animations(app, press_opacity: float = 0.88) -> PressAnimationFilter:
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = PressAnimationFilter(app, press_opacity=press_opacity)
    app.installEventFilter(_filter_instance)
    return _filter_instance
