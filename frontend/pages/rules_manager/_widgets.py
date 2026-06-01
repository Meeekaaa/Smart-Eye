from __future__ import annotations

import os
import sqlite3
from typing import ClassVar

from PySide6.QtCore import Qt, QSize, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.widgets.animated_stack import AnimatedStackedWidget
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.styles._btn_styles import _ICON_BTN_GHOST_DANGER
from frontend.styles._colors import (
    _ACCENT,
    _ACCENT_BG_12,
    _ACCENT_BG_18,
    _ACCENT_HI,
    _ACCENT_HI_BG_35,
    _ACCENT_HI_BG_70,
    _BG_RAISED,
    _BORDER,
    _BORDER_DIM,
    _HEAT_AMBER,
    _HEAT_GREEN,
    _HEAT_LIME,
    _HEAT_ORANGE,
    _HEAT_RED,
    _MUTED_BG_10,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_MICRO,
    FONT_SIZE_LABEL,
    FONT_SIZE_SUBHEAD,
    FONT_WEIGHT_BOLD,
    FONT_WEIGHT_SEMIBOLD,
    RADIUS_3,
    RADIUS_6,
    RADIUS_9,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_XS,
    SIZE_ICON_64,
    SPACE_3,
    SPACE_5,
    SPACE_6,
    SPACE_10,
    SPACE_MD,
    SPACE_SM,
    SPACE_9,
    SPACE_14,
    SPACE_XS,
    SPACE_XXL,
    SPACE_20,
    SIZE_CONTROL_22,
    SIZE_CONTROL_MID,
    SIZE_ITEM_SM,
    SIZE_PANEL_SM,
    SIZE_PANEL_W_MD,
    SIZE_BTN_W_62,
    SIZE_BTN_W_58,
    SIZE_BTN_W_82,
    SIZE_BTN_W_MD,
    SIZE_BTN_W_LG,
    SIZE_FIELD_W_SM,
    SIZE_SECTION_H,
    SIZE_HERO_HEADER,
    SIZE_ROW_72,
    SPACE_XXS,
    SPACE_XXXS,
)
from frontend.widgets.base.roster_card_base import (
    apply_roster_card_style,
    build_roster_card_layout,
)

from ._constants import (
    _ACTION_META,
    _combo_ss,
    _input_ss,
    _pill,
    _spin_ss,
)


class HeatBar(QWidget):
    SEGMENTS = 5

    def __init__(self, heat_level: int, enabled: bool, parent=None):
        super().__init__(parent)
        self._heat_level = max(0, min(heat_level, 15))
        self._enabled = enabled
        self.setFixedWidth(SIZE_PANEL_SM)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def _colors_for_level(self, level_step: int):
        palette = [_HEAT_GREEN, _HEAT_LIME, _HEAT_AMBER, _HEAT_ORANGE, _HEAT_RED]
        idx = max(0, min(level_step - 1, len(palette) - 1))
        bright = QColor(palette[idx])
        dim = QColor(bright.red(), bright.green(), bright.blue(), 60)
        return bright, dim

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        seg_h, gap = 5, 4
        total_h = self.SEGMENTS * seg_h + (self.SEGMENTS - 1) * gap
        start_y = (h - total_h) // 2
        level_frac = min(1.0, max(0.0, self._heat_level / 15.0))
        level_step = max(1, int(round(level_frac * 4)) + 1)
        bright, dim = self._colors_for_level(level_step)
        if not self._enabled:
            bright = QColor(_TEXT_MUTED)
            bright.setAlpha(80)
            dim = QColor(_TEXT_MUTED)
            dim.setAlpha(30)
        lit_count = max(1, int(round(level_frac * self.SEGMENTS)))
        seg_w, x = w - 20, 10
        for i in range(self.SEGMENTS):
            idx_from_bottom = self.SEGMENTS - 1 - i
            y = start_y + i * (seg_h + gap)
            if idx_from_bottom < lit_count:
                color = QColor(bright)
                p.setBrush(color)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(x, y, seg_w, seg_h, 2, 2)
                glow = QLinearGradient(x, y, x + seg_w, y)
                glow.setColorAt(0, QColor(bright.red(), bright.green(), bright.blue(), 0))
                glow.setColorAt(0.5, QColor(bright.red(), bright.green(), bright.blue(), 60))
                glow.setColorAt(1, QColor(bright.red(), bright.green(), bright.blue(), 0))
                p.setBrush(glow)
                p.drawRoundedRect(x - 2, y - 1, seg_w + 4, seg_h + 2, 2, 2)
            else:
                if self._enabled:
                    p.setBrush(dim)
                else:
                    dim_border = QColor(_BORDER)
                    dim_border.setAlpha(100)
                    p.setBrush(dim_border)
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRoundedRect(x, y, seg_w, seg_h, 2, 2)
        p.end()


def build_rule_header(
    name: str,
    subtitle: str,
    action: str,
    logic: str,
    priority: int,
    heat_level: int,
    enabled: bool,
    label: str | None = None,
    parent: QWidget | None = None,
) -> QFrame:
    hero_frame = QFrame(parent)
    hero_frame.setFixedHeight(SIZE_HERO_HEADER)
    hero_frame.setStyleSheet(f"QFrame {{ background: {_BG_RAISED}; border: none; }}")
    hero_layout = QHBoxLayout(hero_frame)
    hero_layout.setContentsMargins(SPACE_20, SPACE_14, SPACE_20, SPACE_14)
    hero_layout.setSpacing(SPACE_14)
    hero_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

    heat_wrap = QFrame()
    heat_wrap.setFixedSize(SIZE_ROW_72, SIZE_ROW_72)
    heat_wrap.setStyleSheet(f"""
        QFrame {{
            background-color: {_BG_RAISED};
            border: {SPACE_XXXS}px solid {_BORDER_DIM};
            border-radius: {RADIUS_LG}px;
        }}
    """)
    heat_layout = QVBoxLayout(heat_wrap)
    heat_layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
    heat_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    heat = HeatBar(heat_level, enabled)
    heat.setFixedSize(SIZE_ICON_64, SIZE_ICON_64)
    heat_layout.addWidget(heat)
    hero_layout.addWidget(heat_wrap, alignment=Qt.AlignmentFlag.AlignVCenter)

    heading_col = QVBoxLayout()
    heading_col.setContentsMargins(0, SPACE_XXS, 0, 0)
    heading_col.setSpacing(SPACE_XS)

    name_lbl = QLabel(name or "Rule")
    nf = QFont()
    safe_set_point_size(nf, FONT_SIZE_SUBHEAD)
    nf.setBold(True)
    name_lbl.setFont(nf)
    name_lbl.setStyleSheet(f"color: {_TEXT_PRI};")
    heading_col.addWidget(name_lbl)

    subtitle_lbl = QLabel(subtitle or "No description")
    subtitle_lbl.setStyleSheet(f"font-size: {FONT_SIZE_LABEL}px; color: {_TEXT_SEC};")
    heading_col.addWidget(subtitle_lbl)
    heading_col.addSpacing(SPACE_6)

    def _chip(text: str, fg: str, bg: str) -> QLabel:
        chip = QLabel(text)
        chip.setStyleSheet(
            f"font-size: {FONT_SIZE_MICRO}px; font-weight: {FONT_WEIGHT_BOLD}; "
            f"padding: {SPACE_3}px {SPACE_10}px; border-radius: {RADIUS_LG}px; "
            f"background-color: {bg}; color: {fg}; border: none;"
        )
        return chip

    chip_row = QHBoxLayout()
    chip_row.setSpacing(SPACE_6)
    act_fg, act_bg, _act_border, act_lbl = _ACTION_META.get(action, (_TEXT_SEC, _ACCENT_BG_12, _BORDER, action.upper()))
    chip_row.addWidget(_chip(act_lbl, act_fg, act_bg))
    chip_row.addWidget(_chip(logic, _ACCENT_HI, _ACCENT_BG_12))
    if priority:
        chip_row.addWidget(_chip(f"P{priority}", _TEXT_SEC, _MUTED_BG_10))
    chip_row.addStretch()
    heading_col.addLayout(chip_row)

    hero_layout.addLayout(heading_col, stretch=1)
    return hero_frame


class _IdentityPicker(QWidget):
    def __init__(self, initial_value: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(SPACE_6)

        faces = []
        try:
            faces = db.get_faces()
        except (sqlite3.Error, RuntimeError, AttributeError, TypeError):
            pass
        self._faces = faces

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.lineEdit().setPlaceholderText("Search name or UUID…")
        self._combo.setStyleSheet(_combo_ss())

        search_list = []
        for f in faces:
            if f.get("name"):
                search_list.append(f["name"])
            if f.get("external_uuid"):
                search_list.append(f["external_uuid"])
        comp = QCompleter(search_list, self._combo)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self._combo.setCompleter(comp)

        self._uuid_btn = QPushButton("Name")
        self._uuid_btn.setCheckable(True)
        self._uuid_btn.setFixedHeight(SIZE_SECTION_H)
        self._uuid_btn.setFixedWidth(SIZE_BTN_W_62)
        self._uuid_btn.setToolTip("Match by Name or UUID")
        self._uuid_btn.setStyleSheet(f"""
            QPushButton {{
                background:{_BG_RAISED}; border:{SPACE_XXXS}px solid {_BORDER}; border-radius:{RADIUS_MD}px;
                color:{_TEXT_MUTED}; font-size:{FONT_SIZE_MICRO}px; font-weight:{FONT_WEIGHT_BOLD}; padding:0 {SPACE_6}px;
                min-height:{SIZE_SECTION_H}px; max-height:{SIZE_SECTION_H}px;
            }}
            QPushButton:checked {{
                background:{_ACCENT_BG_18}; border-color:{_ACCENT};
                color:{_ACCENT_HI};
            }}
            QPushButton:hover {{ border-color:{_TEXT_SEC}; color:{_TEXT_PRI}; }}
        """)
        self._uuid_btn.toggled.connect(self._on_uuid_mode_changed)

        h.addWidget(self._combo, stretch=1)
        h.addWidget(self._uuid_btn)

        self._rebuild_items(use_uuid=False)
        self._seed(initial_value)

    def _rebuild_items(self, use_uuid: bool, preserve_value: str = ""):
        self._combo.blockSignals(True)
        self._combo.clear()
        self._combo.addItem("\u2500 select identity \u2500", ("", ""))
        self._combo.addItem("Unknown", ("unknown", "unknown"))
        for f in self._faces:
            name = (f.get("name", "") or "").strip()
            uuid = (f.get("external_uuid", "") or "").strip()
            label = uuid if (use_uuid and uuid) else (name or uuid)
            if not label:
                continue
            self._combo.addItem(label, (name, uuid))
        self._combo.blockSignals(False)

        if preserve_value:
            target = preserve_value.strip().lower()
            for i in range(self._combo.count()):
                data = self._combo.itemData(i)
                if not isinstance(data, tuple):
                    continue
                candidate = (data[1] if use_uuid else data[0]) or ""
                if candidate.strip().lower() == target:
                    self._combo.setCurrentIndex(i)
                    return
            self._combo.setCurrentText(preserve_value)

    def _on_uuid_mode_changed(self, checked: bool):
        self._uuid_btn.setText("UUID" if checked else "Name")
        preserve = self.get_value()
        data = self._combo.currentData()
        if isinstance(data, tuple):
            preserve = (data[1] if checked else data[0]) or preserve
        self._rebuild_items(use_uuid=checked, preserve_value=preserve)

    def _seed(self, value: str):
        if not value:
            return
        import re

        _uuid_re = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
        is_uuid = bool(_uuid_re.match(value.strip()))
        if is_uuid:
            self._uuid_btn.setChecked(True)
            for i in range(self._combo.count()):
                d = self._combo.itemData(i)
                if isinstance(d, tuple) and d[1] == value:
                    self._combo.setCurrentIndex(i)
                    return
            self._combo.setCurrentText(value)
        else:
            for i in range(self._combo.count()):
                d = self._combo.itemData(i)
                if isinstance(d, tuple) and d[0].lower() == value.lower():
                    self._combo.setCurrentIndex(i)
                    return
            self._combo.setCurrentText(value)

    def get_value(self) -> str:
        use_uuid = self._uuid_btn.isChecked()
        data = self._combo.currentData()
        text = self._combo.currentText().strip()
        if isinstance(data, tuple):
            if not (data[0] or data[1]):
                if self._combo.currentIndex() >= 0 and text != self._combo.itemText(self._combo.currentIndex()).strip():
                    return text
                return ""
            return (data[1] or data[0]) if use_uuid else (data[0] or data[1])
        return text


class _ObjectClassPicker(QWidget):
    def __init__(self, initial_value: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.lineEdit().setPlaceholderText("Search class name…")
        self._combo.setStyleSheet(_combo_ss())

        class_names = self._collect_classes()
        if class_names:
            self._combo.addItem("\u2500 pick class \u2500", "")
            for cn in class_names:
                self._combo.addItem(cn, cn)

        comp = QCompleter(class_names, self._combo)
        comp.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        comp.setFilterMode(Qt.MatchFlag.MatchContains)
        self._combo.setCompleter(comp)

        h.addWidget(self._combo, stretch=1)

        if initial_value:
            idx = self._combo.findData(initial_value)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
            else:
                self._combo.setCurrentText(initial_value)

    @staticmethod
    def _collect_classes() -> list[str]:
        try:
            from backend.models.model_loader import get_loaded_plugins

            seen: set[str] = set()
            result: list[str] = []
            for model in get_loaded_plugins().values():
                cn = getattr(model, "class_names", None)
                if isinstance(cn, dict):
                    for v in cn.values():
                        s = str(v)
                        if s not in seen:
                            seen.add(s)
                            result.append(s)
            result.sort()
            return result
        except (ImportError, AttributeError, TypeError):
            return []

    def get_value(self) -> str:
        data = self._combo.currentData()
        text = self._combo.currentText().strip()
        if data:
            return str(data)
        if (
            self._combo.currentIndex() >= 0
            and self._combo.itemData(self._combo.currentIndex()) == ""
            and text == self._combo.itemText(self._combo.currentIndex()).strip()
        ):
            return ""
        return text


class _ObjectCountPicker(QWidget):
    def __init__(self, initial_value: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)

        self._spin = QSpinBox()
        self._spin.setRange(0, 999)
        self._spin.setStyleSheet(_spin_ss())
        self._spin.setToolTip("Number of active object detections in the frame")
        try:
            self._spin.setValue(max(0, int(float(str(initial_value or "0")))))
        except (TypeError, ValueError):
            self._spin.setValue(0)
        h.addWidget(self._spin, stretch=1)

    def get_value(self) -> str:
        return str(self._spin.value())


class _GenderPicker(QWidget):
    def __init__(self, initial_value: str = "", parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self._combo = QComboBox()
        self._combo.setStyleSheet(_combo_ss())
        for value in ("male", "female", "unknown"):
            self._combo.addItem(value.title(), value)
        h.addWidget(self._combo, stretch=1)
        idx = self._combo.findData((initial_value or "").strip().lower())
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

    def get_value(self) -> str:
        return str(self._combo.currentData() or "unknown")


class ConditionRow(QFrame):
    remove_requested = Signal(object)

    _OPS: ClassVar[list[tuple[str, str]]] = [
        ("equals", "eq"),
        ("not equals", "neq"),
        ("contains", "contains"),
        ("greater than", "gt"),
        ("less than", "lt"),
        ("greater than or equal", "gte"),
        ("less than or equal", "lte"),
    ]
    _OPS_BY_ATTR: ClassVar[dict[str, tuple[str, ...]]] = {
        "identity": ("eq", "neq", "contains"),
        "gender": ("eq", "neq"),
        "object": ("eq", "neq", "contains"),
        "objects": ("eq", "neq", "gt", "lt", "gte", "lte"),
    }

    def __init__(self, attribute="object", operator="eq", value="", parent=None):
        super().__init__(parent)
        self._build(attribute, operator, value)

    def _build(self, attribute, operator, value):
        self.setStyleSheet(f"""
            QFrame {{
                background:{_BG_RAISED}; border:none; border-radius:{RADIUS_9}px;
            }}
            QFrame:hover {{ border-color:{_ACCENT_HI_BG_35}; }}
        """)
        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE_MD, SPACE_10, SPACE_MD, SPACE_10)
        row.setSpacing(SPACE_SM)

        from ._constants import _get_attributes

        attr_labels = {
            "identity": "Identity",
            "gender": "Gender",
            "object": "Object class",
            "objects": "Object count",
        }
        self._attr = QComboBox()
        for attr_key in _get_attributes():
            self._attr.addItem(attr_labels.get(attr_key, attr_key.title()), attr_key)
        if attribute in _get_attributes():
            for idx in range(self._attr.count()):
                if self._attr.itemData(idx) == attribute:
                    self._attr.setCurrentIndex(idx)
                    break
        self._attr.setStyleSheet(_combo_ss())

        self._op = QComboBox()
        self._op.setFixedWidth(SIZE_FIELD_W_SM)
        self._op.setStyleSheet(_combo_ss())
        self._set_operator_options(str(self._attr.currentData() or ""), operator)

        self._val_stack = AnimatedStackedWidget()
        self._val_stack.setStyleSheet("background:transparent;")

        self._val_text = QLineEdit(value)
        self._val_text.setPlaceholderText("value\u2026")
        self._val_text.setStyleSheet(_input_ss())
        self._val_stack.addWidget(self._val_text)

        self._val_identity = _IdentityPicker(value)
        self._val_stack.addWidget(self._val_identity)

        self._val_object = _ObjectClassPicker(value)
        self._val_stack.addWidget(self._val_object)
        self._val_gender = _GenderPicker(value)
        self._val_stack.addWidget(self._val_gender)
        self._val_count = _ObjectCountPicker(value)
        self._val_stack.addWidget(self._val_count)

        self._attr.currentIndexChanged.connect(lambda _idx: self._on_attr_changed(str(self._attr.currentData() or "")))
        from PySide6.QtCore import QTimer

        QTimer.singleShot(0, lambda: self._on_attr_changed(str(self._attr.currentData() or "")))

        remove = QPushButton()
        remove.setFixedSize(SIZE_ITEM_SM, SIZE_ITEM_SM)
        _x_pix = QPixmap("frontend/assets/icons/x.png")
        if not _x_pix.isNull():
            remove.setIcon(QIcon(_x_pix))
            remove.setIconSize(QSize(SPACE_14, SPACE_14))
        else:
            remove.setText("\u00d7")
        remove.setStyleSheet(_ICON_BTN_GHOST_DANGER)
        remove.clicked.connect(lambda: self.remove_requested.emit(self))

        row.addWidget(self._attr, stretch=1)
        row.addWidget(self._op)
        row.addWidget(self._val_stack, stretch=2)
        row.addWidget(remove)

    def _set_operator_options(self, attr: str, preferred: str | None = None):
        current = preferred or self._op.currentData() or "eq"
        allowed = set(self._OPS_BY_ATTR.get(attr, ("eq", "neq")))
        self._op.blockSignals(True)
        self._op.clear()
        for label, key in self._OPS:
            if key in allowed:
                self._op.addItem(label, key)
        target = str(current)
        idx = self._op.findData(target)
        if idx < 0:
            idx = self._op.findData("gte" if attr == "objects" else "eq")
        self._op.setCurrentIndex(max(0, idx))
        self._op.blockSignals(False)

    def _on_attr_changed(self, attr: str):
        self._set_operator_options(attr)
        if attr == "identity":
            self._val_stack.setCurrentIndex(1)
        elif attr == "gender":
            self._val_stack.setCurrentIndex(3)
        elif attr == "object":
            self._val_stack.setCurrentIndex(2)
        elif attr == "objects":
            self._val_stack.setCurrentIndex(4)
        else:
            self._val_stack.setCurrentIndex(0)

    def get_data(self) -> dict:
        attr = str(self._attr.currentData() or self._attr.currentText())
        if attr == "identity":
            val = self._val_identity.get_value()
        elif attr == "gender":
            val = self._val_gender.get_value()
        elif attr == "object":
            val = self._val_object.get_value()
        elif attr == "objects":
            val = self._val_count.get_value()
        else:
            val = self._val_text.text().strip()
        return {
            "attribute": attr,
            "operator": self._op.currentData(),
            "value": val,
        }


class AlarmCard(QFrame):
    remove_requested = Signal(object)

    def __init__(self, data: dict | None = None, parent=None):
        super().__init__(parent)
        self._build(data or {})

    def _build(self, data: dict):
        self.setObjectName("AlarmCard")

        row = QHBoxLayout(self)
        row.setContentsMargins(SPACE_MD, SPACE_9, SPACE_MD, SPACE_9)
        row.setSpacing(SPACE_SM)

        def _lbl(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setStyleSheet(
                f"color:{_TEXT_MUTED}; font-size:{FONT_SIZE_MICRO}px; font-weight:{FONT_WEIGHT_BOLD}; "
                f"letter-spacing:0.{SPACE_5}px; background:transparent;"
            )
            return lbl

        row.addWidget(_lbl("LVL"))
        self._level = QSpinBox()
        self._level.setRange(1, 5)
        self._level.setValue(int(data.get("escalation_level", 1)))
        self._level.setFixedWidth(SIZE_BTN_W_58)
        self._level.setStyleSheet(_spin_ss())
        self._level.valueChanged.connect(self._update_ui)
        row.addWidget(self._level)

        row.addWidget(_lbl("ACTION"))
        self._type = QComboBox()
        self._type.addItems(["sound", "popup", "email", "webhook"])
        initial_type = data.get("action_type", "sound")
        if initial_type not in ("sound", "popup", "email", "webhook"):
            initial_type = "sound"
        self._type.setCurrentText(initial_type)
        self._type.setFixedWidth(SIZE_BTN_W_LG)
        self._type.setStyleSheet(_combo_ss())
        self._type.currentIndexChanged.connect(self._update_ui)
        row.addWidget(self._type)

        row.addWidget(_lbl("DELAY"))
        self._delay = QSpinBox()
        self._delay.setRange(0, 3600)
        self._delay.setValue(int(data.get("trigger_after_sec", 0)))
        self._delay.setFixedWidth(SIZE_BTN_W_82)
        self._delay.setSuffix(" s")
        self._delay.setStyleSheet(_spin_ss())
        self._delay.setToolTip("Seconds before this escalation level fires")
        row.addWidget(self._delay)

        row.addWidget(_lbl("COOLDOWN"))
        self._cooldown = QSpinBox()
        self._cooldown.setRange(0, 3600)
        self._cooldown.setValue(int(data.get("cooldown_sec", 10)))
        self._cooldown.setFixedWidth(SIZE_BTN_W_82)
        self._cooldown.setSuffix(" s")
        self._cooldown.setStyleSheet(_spin_ss())
        self._cooldown.setToolTip("Minimum gap between repeat triggers")
        row.addWidget(self._cooldown)

        self._val_combo = QComboBox()
        self._val_combo.setEditable(True)
        self._val_combo.setStyleSheet(_combo_ss())
        row.addWidget(self._val_combo, stretch=1)
        self._initial_action_value = str(data.get("action_value", "") or "")

        self._sound_lbl = QLabel()
        self._sound_lbl.setStyleSheet(
            f"color:{_ACCENT_HI}; font-size:{FONT_SIZE_CAPTION}px; font-weight:{FONT_WEIGHT_SEMIBOLD}; background:transparent;"
        )
        row.addWidget(self._sound_lbl)

        self._mute = QCheckBox("Mute")
        self._mute.setStyleSheet(f"""
            QCheckBox {{ color:{_TEXT_SEC}; font-size:{FONT_SIZE_CAPTION}px; spacing:{SPACE_5}px; }}
            QCheckBox::indicator {{ width:{SPACE_14}px; height:{SPACE_14}px; border:{SPACE_XXXS}px solid {_BORDER};
                border-radius:{RADIUS_3}px; background:{_BG_RAISED}; image: none; }}
            QCheckBox::indicator:checked {{ background:{_ACCENT}; border-color:{_ACCENT}; image: url(frontend/assets/icons/checkmark.png); }}
        """)
        self._mute.stateChanged.connect(self._update_ui)
        row.addWidget(self._mute)

        self._vol_slider = QSlider(Qt.Orientation.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(80)
        self._vol_slider.setFixedWidth(SIZE_BTN_W_MD)
        self._vol_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{ height:{SPACE_XS}px; background:{_BORDER}; border-radius:{RADIUS_XS}px; }}
            QSlider::handle:horizontal {{
                background:{_ACCENT_HI}; border:none;
                width:{SPACE_MD}px; height:{SPACE_MD}px; border-radius:{RADIUS_6}px; margin:-{SPACE_XS}px 0;
            }}
            QSlider::sub-page:horizontal {{ background:{_ACCENT}; border-radius:{RADIUS_XS}px; }}
        """)
        row.addWidget(self._vol_slider)

        self._vol_lbl = QLabel("80%")
        self._vol_lbl.setFixedWidth(SPACE_XXL)
        self._vol_lbl.setStyleSheet(f"color:{_TEXT_SEC}; font-size:{FONT_SIZE_CAPTION}px; background:transparent;")
        self._vol_slider.valueChanged.connect(lambda v: self._vol_lbl.setText(f"{v}%"))
        row.addWidget(self._vol_lbl)

        row.addStretch()

        remove = QPushButton()
        remove.setFixedSize(SIZE_ITEM_SM, SIZE_ITEM_SM)
        _x_pix2 = QPixmap("frontend/assets/icons/x.png")
        if not _x_pix2.isNull():
            remove.setIcon(QIcon(_x_pix2))
            remove.setIconSize(QSize(SPACE_14, SPACE_14))
        else:
            remove.setText("×")
        remove.setStyleSheet(_ICON_BTN_GHOST_DANGER)
        remove.clicked.connect(lambda: self.remove_requested.emit(self))
        row.addWidget(remove)

        if data.get("action_type") == "sound":
            raw = data.get("action_value", "")
            if "|" in raw:
                _, vol_part = raw.split("|", 1)
                try:
                    v = float(vol_part)
                    self._vol_slider.setValue(int(v * 100))
                    if v <= 0:
                        self._mute.setChecked(True)
                except (TypeError, ValueError):
                    pass

        self._update_ui()

    def _load_notification_targets(self, ntype: str, current_value: str):
        self._val_combo.blockSignals(True)
        self._val_combo.clear()
        self._val_combo.addItem("Custom target…", "")
        try:
            profiles = db.get_notification_profiles(enabled_only=True, ntype=ntype)
        except (sqlite3.Error, RuntimeError, AttributeError, TypeError, ValueError):
            profiles = []

        for p in profiles:
            pid = int(p.get("id") or 0)
            name = str(p.get("name") or "").strip() or f"{ntype.title()} Profile {pid}"
            endpoint = str(p.get("endpoint") or "").strip()
            label = f"{name} ({endpoint})" if endpoint else name
            self._val_combo.addItem(label, f"profile:{pid}")

        self._val_combo.blockSignals(False)

        value = (current_value or "").strip()
        if value:
            idx = self._val_combo.findData(value)
            if idx >= 0:
                self._val_combo.setCurrentIndex(idx)
                return
            if not value.startswith("profile:"):
                self._val_combo.setCurrentText(value)
                return
        self._val_combo.setCurrentIndex(0)
        if self._val_combo.lineEdit() is not None:
            self._val_combo.lineEdit().setPlaceholderText("email address" if ntype == "email" else "webhook URL")

    def _current_target_value(self) -> str:
        data = self._val_combo.currentData()
        if isinstance(data, str) and data.startswith("profile:"):
            return data
        return self._val_combo.currentText().strip()

    def _update_ui(self):
        self.setStyleSheet(f"""
            QFrame#AlarmCard {{
                background:{_BG_RAISED};
                border:{SPACE_XXXS}px solid {_BORDER};
                border-radius:{RADIUS_9}px;
            }}
            QFrame#AlarmCard:hover {{ border-color:{_ACCENT_HI_BG_35}; }}
        """)

        t = self._type.currentText()
        is_sound = t == "sound"
        has_val = t in ("email", "webhook")

        self._val_combo.setVisible(has_val)
        self._sound_lbl.setVisible(is_sound)
        self._mute.setVisible(is_sound)
        self._vol_slider.setVisible(is_sound)
        self._vol_lbl.setVisible(is_sound)

        if is_sound:
            path = os.path.join("frontend", "assets", "sounds", f"alarm_level_{self._level.value()}.wav")
            self._sound_lbl.setText(os.path.basename(path))
            disabled = self._mute.isChecked()
            self._vol_slider.setEnabled(not disabled)
            self._vol_lbl.setEnabled(not disabled)
        elif has_val:
            current_val = self._current_target_value() or self._initial_action_value
            self._load_notification_targets(t, current_val)

    def get_data(self) -> dict:
        t = self._type.currentText()
        if t == "sound":
            path = os.path.join("frontend", "assets", "sounds", f"alarm_level_{self._level.value()}.wav")
            vol = 0.0 if self._mute.isChecked() else self._vol_slider.value() / 100.0
            val = f"{path}|{vol:.2f}"
        else:
            val = self._current_target_value()
        return {
            "escalation_level": self._level.value(),
            "trigger_after_sec": self._delay.value(),
            "cooldown_sec": self._cooldown.value(),
            "action_type": t,
            "action_value": val,
        }


class RuleCard(QFrame):
    clicked = Signal(int)

    def __init__(self, rule: dict, is_active: bool = False, on_stop_sounds=None, on_toggle_changed=None, parent=None):
        super().__init__(parent)
        self._rule_id = rule["id"]
        self._on_stop_sounds = on_stop_sounds
        self._on_toggle_changed = on_toggle_changed
        self._is_active = is_active
        self._active_border = _BORDER
        self._inactive_border = _BORDER
        self._active_bg = _BG_RAISED
        self._inactive_bg = _BG_RAISED
        self._build(rule, is_active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build(self, rule: dict, is_active: bool):
        enabled = bool(rule.get("enabled", 1))
        action = rule.get("action", "log_only")
        logic = rule.get("logic", "AND")
        priority = int(rule.get("priority", 0))

        heat_level = priority
        try:
            alarms = db.get_alarm_actions(rule.get("id"))
            if alarms:
                max_level = max(int(a.get("escalation_level", 0) or 0) for a in alarms)
                heat_level = max(heat_level, max_level * 3)
        except (sqlite3.Error, RuntimeError, AttributeError, TypeError, ValueError):
            pass

        action_fg, action_bg, _action_border, action_label = _ACTION_META.get(
            action, (_TEXT_SEC, _ACCENT_BG_12, _BORDER_DIM, action.upper())
        )

        self._active_border = _ACCENT_HI_BG_70
        self._inactive_border = _BORDER
        self._active_bg = _ACCENT_BG_12
        self._inactive_bg = _BG_RAISED
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_roster_card_style(self, "RuleCard", is_active)

        left_layout, info, pills, right = build_roster_card_layout(self, pills_slot_width=SIZE_PANEL_W_MD)
        left_layout.addWidget(HeatBar(heat_level, enabled))
        pills_wrap = pills.parentWidget()
        if pills_wrap is not None:
            pills_wrap.setFixedWidth(0)
            pills_wrap.hide()

        info.setSpacing(SPACE_XS)

        full_rule_name = str(rule.get("name") or "Rule").strip() or "Rule"
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(SPACE_6)
        name_lbl = QLabel(full_rule_name)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        name_lbl.setMinimumWidth(SPACE_20)
        name_lbl.setToolTip(full_rule_name)
        name_font = QFont()
        safe_set_point_size(name_font, FONT_SIZE_CAPTION)
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        name_lbl.setStyleSheet(f"color: {_TEXT_PRI if enabled else _TEXT_SEC}; background: transparent;")
        title_row.addWidget(name_lbl, stretch=1)
        info.addLayout(title_row)

        right.addWidget(_pill(action_label, action_fg, action_bg))
        right.addWidget(_pill(logic, _ACCENT_HI, _ACCENT_BG_12))

        toggle = ToggleSwitch(width=SIZE_CONTROL_MID, height=SIZE_CONTROL_22)
        toggle.setChecked(enabled)
        toggle.toggled.connect(lambda v, rid=rule["id"]: self._toggle_rule(rid, v))
        right.addWidget(toggle)

    def _toggle_rule(self, rule_id: int, enabled: bool) -> None:
        if self._on_stop_sounds:
            self._on_stop_sounds()
        if self._on_toggle_changed:
            self._on_toggle_changed(rule_id, enabled)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._rule_id)
        super().mousePressEvent(event)

    def set_active(self, active: bool) -> None:
        if self._is_active == active:
            return
        self._is_active = active
        self._apply_active_style(active)

    def _apply_active_style(self, active: bool) -> None:
        apply_roster_card_style(self, "RuleCard", active)
