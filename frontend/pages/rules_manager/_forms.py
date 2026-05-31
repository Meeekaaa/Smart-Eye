from __future__ import annotations

import sqlite3

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.services.rules_service import RulesService
from frontend.widgets.confirm_delete_button import ConfirmDeleteButton
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.widgets.action_feedback import make_manager_footer_layout
from frontend.styles._banner_styles import make_edit_banner
from ._widgets import build_rule_header
from frontend.styles._input_styles import _FORM_INPUT_TITLE, _FORM_INPUTS
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_LABEL,
    FONT_WEIGHT_NORMAL,
    RADIUS_3,
    SIZE_BTN_W_80,
    SIZE_BTN_W_MD,
    SIZE_CONTROL_MD,
    SIZE_LABEL_W,
    SIZE_PANEL_MD,
    SIZE_ROW_LG,
    SPACE_10,
    SPACE_14,
    SPACE_18,
    SPACE_20,
    SPACE_6,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XS,
    SPACE_XXL,
    SPACE_XXS,
    SPACE_XXXS,
)

from ._constants import (
    _ADD_BTN_BLUE,
    _BG_RAISED,
    _BG_SURFACE,
    _BORDER,
    _BORDER_DIM,
    _TEXT_PRI,
    _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST,
    _TEXT_BTN_RED,
    _TEXT_BTN_RED_CONFIRM,
    _TEXT_MUTED,
    _TEXT_SEC,
    _combo_ss,
    _make_sdiv,
    _spin_ss,
    _srow,
)
from ._widgets import AlarmCard, ConditionRow


class _BaseRuleForm(QWidget):
    def __init__(self, rules_service: RulesService, parent=None):
        super().__init__(parent)
        self._rules_service = rules_service
        self._alarm_cards: list[AlarmCard] = []
        self._condition_rows: list[ConditionRow] = []
        self._alarm_vbox: QVBoxLayout | None = None
        self._cond_vbox: QVBoxLayout | None = None

    def _make_banner(self) -> QWidget:
        raise NotImplementedError

    def _build_form(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._make_banner())

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border:none; background:{_BG_SURFACE}; }}
            QScrollBar:vertical {{ border:none; background:transparent; width:{SPACE_6}px; margin:0; }}
            QScrollBar::handle:vertical {{ background:{_BORDER}; min-height:{SPACE_20}px; border-radius:{RADIUS_3}px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height:0; }}
        """)
        body = QWidget()
        body.setStyleSheet(f"background:{_BG_SURFACE};")
        body_l = QVBoxLayout(body)
        body_l.setContentsMargins(0, 0, 0, SPACE_XXL)
        body_l.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        self._populate_body(body_l)
        body_l.addStretch()

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet(f"background:{_BORDER_DIM}; border:none; max-height:{SPACE_XXXS}px;")
        root.addWidget(div)

        root.addLayout(self._make_action_bar())

    def _populate_body(self, layout: QVBoxLayout):
        raise NotImplementedError

    def _make_action_bar(self) -> QHBoxLayout:
        raise NotImplementedError

    def _build_name_row(self) -> QFrame:
        fr = QFrame()
        fr.setFixedHeight(SIZE_ROW_LG)
        fr.setStyleSheet(f"QFrame{{background:transparent;border:none;border-bottom:{SPACE_XXXS}px solid {_BORDER_DIM};}}")
        row = QHBoxLayout(fr)
        row.setContentsMargins(SPACE_XL, SPACE_MD, SPACE_XL, SPACE_MD)
        row.setSpacing(SPACE_20)
        lb = QLabel("Rule Name")
        lb.setFixedWidth(SIZE_LABEL_W)
        lb.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        lb.setStyleSheet(
            f"color:{_TEXT_SEC};font-size:{FONT_SIZE_LABEL}px;font-weight:{FONT_WEIGHT_NORMAL};background:transparent;border:none;"
        )
        row.addWidget(lb)
        self._e_name = QLineEdit()
        self._e_name.setPlaceholderText("e.g.  NO MASK!")
        self._e_name.setStyleSheet(_FORM_INPUT_TITLE)
        row.addWidget(self._e_name, stretch=1)
        return fr

    def _build_desc_row(self) -> QFrame:
        fr = QFrame()
        fr.setFixedHeight(SIZE_PANEL_MD)
        fr.setStyleSheet(f"QFrame{{background:transparent;border:none;border-bottom:{SPACE_XXXS}px solid {_BORDER_DIM};}}")
        row = QHBoxLayout(fr)
        row.setContentsMargins(SPACE_XL, SPACE_MD, SPACE_XL, SPACE_MD)
        row.setSpacing(SPACE_20)
        lb = QLabel("Description")
        lb.setFixedWidth(SIZE_LABEL_W)
        lb.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lb.setStyleSheet(
            f"color:{_TEXT_SEC};font-size:{FONT_SIZE_LABEL}px;font-weight:{FONT_WEIGHT_NORMAL};"
            f"background:transparent;border:none;margin-top:{SPACE_XS}px;"
        )
        row.addWidget(lb)
        self._e_desc = QTextEdit()
        self._e_desc.setPlaceholderText("Optional description\u2026")
        self._e_desc.setStyleSheet(_FORM_INPUTS)
        row.addWidget(self._e_desc, stretch=1)
        return fr

    def _build_core_fields(self, body_l: QVBoxLayout):
        self._e_logic = QComboBox()
        self._e_logic.addItems(["AND", "OR"])
        self._e_logic.setStyleSheet(_combo_ss())
        body_l.addWidget(_srow("Logic", self._e_logic))

        self._e_action = QComboBox()
        self._e_action.addItems(["alarm", "suppress", "log_only"])
        self._e_action.setStyleSheet(_combo_ss())
        body_l.addWidget(_srow("Action", self._e_action))

        self._e_camera = QComboBox()
        self._e_camera.addItem("All Cameras", None)
        for cam in db.get_cameras():
            self._e_camera.addItem(cam["name"], cam["id"])
        self._e_camera.setStyleSheet(_combo_ss())
        body_l.addWidget(_srow("Camera", self._e_camera))

        self._e_priority = QSpinBox()
        self._e_priority.setRange(0, 100)
        self._e_priority.setStyleSheet(_spin_ss())
        body_l.addWidget(_srow("Priority", self._e_priority))

        self._e_enabled = ToggleSwitch()
        en_wrap = QWidget()
        en_wrap.setStyleSheet("background:transparent;border:none;")
        en_h = QHBoxLayout(en_wrap)
        en_h.setContentsMargins(0, 0, 0, 0)
        en_h.setSpacing(SPACE_10)
        en_h.addWidget(self._e_enabled)
        en_lbl = QLabel("Rule is active")
        en_lbl.setStyleSheet(f"color:{_TEXT_SEC};font-size:{FONT_SIZE_LABEL}px;background:transparent;")
        en_h.addWidget(en_lbl)
        en_h.addStretch()
        body_l.addWidget(_srow("Active", en_wrap))

    def _build_conditions_section(self, body_l: QVBoxLayout):
        body_l.addWidget(_make_sdiv("Conditions"))
        cond_pad = QWidget()
        cond_pad.setStyleSheet("background:transparent;")
        cond_lay = QVBoxLayout(cond_pad)
        cond_lay.setContentsMargins(SPACE_18, SPACE_14, SPACE_18, SPACE_14)
        cond_lay.setSpacing(SPACE_SM)

        add_cond = QPushButton("+  Add Condition")
        add_cond.setFixedHeight(SIZE_CONTROL_MD)
        add_cond.setStyleSheet(_ADD_BTN_BLUE)
        add_cond.clicked.connect(self._add_condition_row)
        cond_lay.addWidget(add_cond)

        self._cond_vbox = QVBoxLayout()
        self._cond_vbox.setSpacing(SPACE_SM)
        self._no_cond_lbl = QLabel("No conditions yet \u2014 click the button above to add one.")
        self._no_cond_lbl.setStyleSheet(
            f"color:{_TEXT_MUTED}; font-size:{FONT_SIZE_CAPTION}px; font-style:italic; padding:{SPACE_6}px {SPACE_XXS}px {SPACE_XXS}px;"
        )
        self._cond_vbox.addWidget(self._no_cond_lbl)
        cond_lay.addLayout(self._cond_vbox)
        body_l.addWidget(cond_pad)

    def _add_condition_row(self, attribute="object", operator="eq", value=""):
        if hasattr(self, "_no_cond_lbl") and not self._no_cond_lbl.isHidden():
            self._no_cond_lbl.hide()
        row = ConditionRow(attribute, operator, value)
        row.remove_requested.connect(self._remove_condition_row)
        self._cond_vbox.addWidget(row)
        self._condition_rows.append(row)

    def _remove_condition_row(self, row: ConditionRow):
        if row in self._condition_rows:
            self._condition_rows.remove(row)
        self._cond_vbox.removeWidget(row)
        row.deleteLater()
        if not self._condition_rows and hasattr(self, "_no_cond_lbl"):
            self._no_cond_lbl.show()

    def _build_alarms_section(self, body_l: QVBoxLayout):
        body_l.addWidget(_make_sdiv("Alarm Escalation"))
        alarm_pad = QWidget()
        alarm_pad.setStyleSheet("background:transparent;")
        alarm_lay = QVBoxLayout(alarm_pad)
        alarm_lay.setContentsMargins(SPACE_18, SPACE_14, SPACE_18, SPACE_14)
        alarm_lay.setSpacing(SPACE_10)

        add_alarm = QPushButton("+  Add Escalation Level")
        add_alarm.setFixedHeight(SIZE_CONTROL_MD)
        add_alarm.setStyleSheet(_ADD_BTN_BLUE)
        add_alarm.clicked.connect(self._add_alarm_card)
        alarm_lay.addWidget(add_alarm)

        self._alarm_vbox = QVBoxLayout()
        self._alarm_vbox.setSpacing(SPACE_10)
        self._no_alarm_lbl = QLabel("No escalation levels yet \u2014 click the button above to add one.")
        self._no_alarm_lbl.setStyleSheet(
            f"color:{_TEXT_MUTED}; font-size:{FONT_SIZE_CAPTION}px; font-style:italic; padding:{SPACE_6}px {SPACE_XXS}px {SPACE_XXS}px;"
        )
        self._alarm_vbox.addWidget(self._no_alarm_lbl)
        alarm_lay.addLayout(self._alarm_vbox)
        body_l.addWidget(alarm_pad)

    def _add_alarm_card(self, data: dict | None = None):
        if data is None:
            next_level = (
                max(
                    (c.get_data()["escalation_level"] for c in self._alarm_cards),
                    default=0,
                )
                + 1
            )
            data = {"escalation_level": min(next_level, 5)}
        if hasattr(self, "_no_alarm_lbl") and not self._no_alarm_lbl.isHidden():
            self._no_alarm_lbl.hide()
        card = AlarmCard(data)
        card.remove_requested.connect(self._remove_alarm_card)
        self._alarm_vbox.addWidget(card)
        self._alarm_cards.append(card)

    def _remove_alarm_card(self, card: AlarmCard):
        if card in self._alarm_cards:
            self._alarm_cards.remove(card)
        self._alarm_vbox.removeWidget(card)
        card.deleteLater()
        if not self._alarm_cards and hasattr(self, "_no_alarm_lbl"):
            self._no_alarm_lbl.show()

    def _collect_conditions(self) -> list[dict]:
        return [r.get_data() for r in self._condition_rows if r.get_data()["attribute"] and r.get_data()["value"]]

    def _collect_alarms(self) -> list[dict]:
        return [c.get_data() for c in self._alarm_cards]


class _EditRuleForm(_BaseRuleForm):
    cancel_requested = Signal()
    delete_requested = Signal()
    saved = Signal()

    def __init__(self, rule: dict, rules_service: RulesService, parent=None):
        super().__init__(rules_service, parent)
        self._rule = rule
        self._rule_id = rule["id"]
        self._build_form()
        self._seed_from_rule(rule)

    def _make_banner(self) -> QWidget:
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.setSpacing(0)
        name = self._rule.get("name", "") or "Rule"
        subtitle = (self._rule.get("description") or "").strip() or "No description"
        heat_level = int(self._rule.get("priority", 0) or 0)
        try:
            _a = self._rules_service.get_alarm_actions(self._rule_id)
            if _a:
                heat_level = max(heat_level, max(int(a.get("escalation_level", 0) or 0) for a in _a) * 3)
        except (sqlite3.Error, RuntimeError, AttributeError, TypeError, ValueError):
            pass
        wl.addWidget(
            build_rule_header(
                name,
                subtitle,
                self._rule.get("action", "log_only"),
                self._rule.get("logic", "AND"),
                int(self._rule.get("priority", 0) or 0),
                heat_level,
                bool(self._rule.get("enabled", 1)),
                label="RULE",
                parent=self,
            )
        )
        wl.addWidget(make_edit_banner(f"Editing — {name}", self))
        return wrap

    def _populate_body(self, body_l: QVBoxLayout):
        body_l.addWidget(self._build_name_row())
        body_l.addWidget(self._build_desc_row())
        self._build_core_fields(body_l)
        self._build_conditions_section(body_l)
        self._build_alarms_section(body_l)

    def _make_action_bar(self) -> QHBoxLayout:
        del_btn = ConfirmDeleteButton("Delete", "Sure?")
        del_btn.setFixedHeight(SIZE_CONTROL_MD)
        del_btn.setFixedWidth(SIZE_BTN_W_MD)
        del_btn.set_button_styles(_TEXT_BTN_RED, _TEXT_BTN_RED_CONFIRM)
        del_btn.set_confirm_callback(lambda: self.delete_requested.emit())

        cancel = QPushButton("Cancel")
        cancel.setFixedHeight(SIZE_CONTROL_MD)
        cancel.setFixedWidth(SIZE_BTN_W_80)
        cancel.setStyleSheet(_TEXT_BTN_GHOST)
        cancel.clicked.connect(lambda: self.cancel_requested.emit())

        save = QPushButton("Save")
        save.setFixedHeight(SIZE_CONTROL_MD)
        save.setFixedWidth(SIZE_BTN_W_80)
        save.setStyleSheet(_TEXT_BTN_BLUE)
        save.clicked.connect(self._do_save)
        return make_manager_footer_layout(
            left_widget=del_btn,
            right_widgets=[cancel, save],
            margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
            spacing=SPACE_SM,
        )

    def _seed_from_rule(self, rule: dict):
        self._e_name.setText(rule.get("name", ""))
        self._e_desc.setPlainText(rule.get("description", ""))
        self._e_logic.setCurrentText(rule.get("logic", "AND"))
        action = rule.get("action", "log_only")
        self._e_action.setCurrentText(action)
        self._e_priority.setValue(int(rule.get("priority", 0)))
        self._e_enabled.setChecked(bool(rule.get("enabled", 1)))

        if rule.get("camera_id"):
            for i in range(self._e_camera.count()):
                if self._e_camera.itemData(i) == rule["camera_id"]:
                    self._e_camera.setCurrentIndex(i)
                    break

        for c in self._rules_service.get_rule_conditions(self._rule_id):
            self._add_condition_row(c["attribute"], c["operator"], c["value"])

        for a in self._rules_service.get_alarm_actions(self._rule_id):
            self._add_alarm_card(a)

    def _do_save(self):
        name = self._e_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Rule name is required.")
            self._e_name.setFocus()
            return

        try:
            self._rules_service.save_rule(
                self._rule_id,
                data=dict(
                    name=name,
                    description=self._e_desc.toPlainText().strip(),
                    logic=self._e_logic.currentText(),
                    action=self._e_action.currentText(),
                    priority=self._e_priority.value(),
                    camera_id=self._e_camera.currentData(),
                    enabled=self._e_enabled.isChecked(),
                ),
                conditions=self._collect_conditions(),
                alarms=self._collect_alarms(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Rule", str(exc))
            return
        self.saved.emit()


class NewRulePanel(_BaseRuleForm):
    saved = Signal(int)
    close_requested = Signal()

    def __init__(self, rules_service: RulesService, parent=None):
        super().__init__(rules_service, parent)
        self._build_form()

    def _make_banner(self) -> QWidget:
        banner = QFrame()
        banner.setStyleSheet(f"QFrame{{background:{_BG_RAISED};border:none;}}")
        bi = QHBoxLayout(banner)
        bi.setContentsMargins(SPACE_20, SPACE_14, SPACE_20, SPACE_14)
        bi.setSpacing(SPACE_SM)
        nf = QFont()
        safe_set_point_size(nf, FONT_SIZE_CAPTION)
        nf.setBold(True)
        lbl = QLabel("Add Rule")
        lbl.setFont(nf)
        lbl.setStyleSheet(f"color:{_TEXT_PRI};")
        bi.addWidget(lbl)
        bi.addStretch()
        close_x = QPushButton("X")
        close_x.setFixedSize(SIZE_CONTROL_MD, SIZE_CONTROL_MD)
        close_x.setStyleSheet(_TEXT_BTN_GHOST)
        close_x.clicked.connect(lambda: self.close_requested.emit())
        bi.addWidget(close_x)
        return banner

    def _populate_body(self, body_l: QVBoxLayout):
        body_l.addWidget(self._build_name_row())
        body_l.addWidget(self._build_desc_row())
        self._build_core_fields(body_l)
        self._build_conditions_section(body_l)
        self._build_alarms_section(body_l)

        self._e_action.setCurrentText("log_only")
        self._e_enabled.setChecked(True)

    def _make_action_bar(self) -> QHBoxLayout:
        close = QPushButton("Close")
        close.setFixedHeight(SIZE_CONTROL_MD)
        close.setFixedWidth(SIZE_BTN_W_80)
        close.setStyleSheet(_TEXT_BTN_GHOST)
        close.clicked.connect(lambda: self.close_requested.emit())
        save = QPushButton("Save")
        save.setFixedHeight(SIZE_CONTROL_MD)
        save.setFixedWidth(SIZE_BTN_W_80)
        save.setStyleSheet(_TEXT_BTN_BLUE)
        save.clicked.connect(self._do_save)
        return make_manager_footer_layout(
            right_widgets=[close, save],
            margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
            spacing=SPACE_SM,
        )

    def reset(self):
        self._alarm_cards.clear()
        self._condition_rows.clear()
        self._e_name.clear()
        self._e_desc.clear()
        self._e_logic.setCurrentIndex(0)
        self._e_action.setCurrentText("log_only")
        self._e_priority.setValue(0)
        self._e_camera.setCurrentIndex(0)
        self._e_enabled.setChecked(True)
        if self._cond_vbox:
            while self._cond_vbox.count():
                item = self._cond_vbox.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if hasattr(self, "_no_cond_lbl"):
                self._no_cond_lbl.show()
                self._cond_vbox.addWidget(self._no_cond_lbl)
        if self._alarm_vbox:
            while self._alarm_vbox.count():
                item = self._alarm_vbox.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            if hasattr(self, "_no_alarm_lbl"):
                self._no_alarm_lbl.show()
                self._alarm_vbox.addWidget(self._no_alarm_lbl)

    def _do_save(self):
        name = self._e_name.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Rule name is required.")
            self._e_name.setFocus()
            return

        try:
            rid = self._rules_service.save_rule(
                None,
                data=dict(
                    name=name,
                    description=self._e_desc.toPlainText().strip(),
                    logic=self._e_logic.currentText(),
                    action=self._e_action.currentText(),
                    priority=self._e_priority.value(),
                    camera_id=self._e_camera.currentData(),
                    enabled=self._e_enabled.isChecked(),
                ),
                conditions=self._collect_conditions(),
                alarms=self._collect_alarms(),
            )
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid Rule", str(exc))
            return
        self.saved.emit(int(rid))
