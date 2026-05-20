from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QPoint, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QStackedWidget, QWidget


class AnimatedStackedWidget(QStackedWidget):
    transition_finished = Signal(QWidget)

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        duration: int = 200,
        offset: int = 10,
        use_fade: bool = True,
        max_fade_pixels: int | None = 1_000_000,
        easing: QEasingCurve.Type = QEasingCurve.Type.OutCubic,
    ) -> None:
        super().__init__(parent)
        self._anim_duration = duration
        self._anim_offset = offset
        self._use_fade = use_fade
        self._max_fade_pixels = max_fade_pixels
        self._easing = easing
        self._anim_group: QParallelAnimationGroup | None = None
        self._anim_target: QWidget | None = None
        self._owns_effect = False
        self._pending_widget: QWidget | None = None
        self._animating = False

    def setCurrentIndex(self, index: int) -> None:
        widget = self.widget(index)
        if widget is None:
            return
        self.setCurrentWidget(widget)

    def setCurrentWidget(self, widget: QWidget | None) -> None:
        if widget is None:
            return
        if widget == self.currentWidget():
            return
        if self._animating:
            self._pending_widget = widget
            if self._anim_group is not None:
                self._anim_group.stop()
                self._cleanup_animation()
        super().setCurrentWidget(widget)
        use_fade = self._should_fade(widget)
        if not use_fade and self._anim_offset <= 0:
            self.transition_finished.emit(widget)
            return
        self._animate_in(widget, use_fade)

    def _animate_in(self, widget: QWidget, use_fade: bool) -> None:
        self._animating = True
        final_pos = widget.pos()
        start_pos = QPoint(final_pos.x(), final_pos.y() + self._anim_offset)
        widget.move(start_pos)

        group = QParallelAnimationGroup(self)
        pos_anim = QPropertyAnimation(widget, b"pos", group)
        pos_anim.setDuration(self._anim_duration)
        pos_anim.setStartValue(start_pos)
        pos_anim.setEndValue(final_pos)
        pos_anim.setEasingCurve(self._easing)
        group.addAnimation(pos_anim)

        effect = None
        self._owns_effect = False
        if use_fade:
            current_effect = widget.graphicsEffect()
            if current_effect is None:
                effect = QGraphicsOpacityEffect(widget)
                effect.setOpacity(0.0)
                widget.setGraphicsEffect(effect)
                self._owns_effect = True
            elif isinstance(current_effect, QGraphicsOpacityEffect):
                effect = current_effect
                effect.setOpacity(0.0)
            if effect is not None:
                op_anim = QPropertyAnimation(effect, b"opacity", group)
                op_anim.setDuration(self._anim_duration)
                op_anim.setStartValue(effect.opacity())
                op_anim.setEndValue(1.0)
                op_anim.setEasingCurve(self._easing)
                group.addAnimation(op_anim)

        self._anim_group = group
        self._anim_target = widget
        group.finished.connect(self._on_anim_finished)
        group.start()

    def _should_fade(self, widget: QWidget) -> bool:
        if not self._use_fade:
            return False
        if self._max_fade_pixels is None:
            return True
        w = widget.width() or widget.sizeHint().width()
        h = widget.height() or widget.sizeHint().height()
        if w <= 0 or h <= 0:
            return True
        return (w * h) <= self._max_fade_pixels

    def _cleanup_animation(self) -> None:
        if self._owns_effect and self._anim_target is not None:
            if self._anim_target.graphicsEffect() is not None:
                self._anim_target.setGraphicsEffect(None)
        self._anim_group = None
        self._anim_target = None
        self._owns_effect = False
        self._animating = False

    def _on_anim_finished(self) -> None:
        self._cleanup_animation()
        current = self.currentWidget()
        if current is not None:
            self.transition_finished.emit(current)
        if self._pending_widget is not None and self._pending_widget != self.currentWidget():
            pending = self._pending_widget
            self._pending_widget = None
            self.setCurrentWidget(pending)
