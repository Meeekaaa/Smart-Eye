import contextlib
import importlib
import sys
import logging

from PySide6.QtCore import (
    QByteArray,
    Qt,
    QTimer,
)
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsBlurEffect,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QMenu,
    QSystemTrayIcon,
    QWidget,
)

from frontend.app_theme import get_theme
from frontend.styles._colors import _BG_NAV_DARK
from frontend.ui_tokens import SPACE_XXXS

from frontend.services.rules_service import RulesService
from frontend.state.page_factory import build_pages, get_page_specs, UnloadPolicy
from backend.services.service_manager import get_service_manager
from frontend.widgets.alert_popup import show_alert
from frontend.navigation import nav_label_map
from frontend.widgets.auth_overlay import AuthOverlay
from frontend.widgets.animated_stack import AnimatedStackedWidget
from frontend.widgets.sidebar import SidebarWidget, LOGO_ICON_PATH
from frontend.theme_runtime import invalidate_theme_cache
from frontend.state.session import build_trusted_user, compute_access, pick_initial_tab
from utils.auth_validation import get_email_validation_error
from utils import config

logger = logging.getLogger(__name__)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SmartEye")
        self.setWindowIcon(QIcon(LOGO_ICON_PATH))
        self.setMinimumSize(1200, 700)

        from backend.repository import db as _db

        self._db = _db
        saved_geom = _db.get_setting("window_geometry", "")
        if saved_geom:
            self.restoreGeometry(QByteArray.fromHex(saved_geom.encode()))
        else:
            self.resize(1600, 950)

        self._current_theme = config.theme()
        self.setStyleSheet(get_theme(self._current_theme))
        self._rules_service = RulesService()
        self._service_manager = get_service_manager()
        self._tray_icon: QSystemTrayIcon | None = None
        self._tray_force_quit = False
        self._is_shutting_down = False

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._sidebar = SidebarWidget(
            on_navigate=self._navigate,
            on_logout=self._logout,
            current_theme=self._current_theme,
        )

        self._stack = AnimatedStackedWidget()
        self._stack.setStyleSheet("background: transparent;")

        main_layout.addWidget(self._sidebar)

        side_border = QFrame(self)
        side_border.setFixedWidth(SPACE_XXXS)
        side_border.setStyleSheet(f"background: {_BG_NAV_DARK}; border: none;")
        self._side_border = side_border
        main_layout.addWidget(side_border)

        main_layout.addWidget(self._stack, stretch=1)

        def _preload(name: str) -> bool:
            try:
                return bool(self._db.get_setting(f"preload_{name}_page", False))
            except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                return False
        self._page_specs = get_page_specs(self._rules_service)
        self._pages = build_pages(_preload, self._rules_service)
        self._theme_dirty_pages: set[str] = set()
        self._page_last_active: dict[str, float] = {}
        self._current_key: str | None = None
        if self._pages.get("settings"):
            self._bind_settings_page(self._pages["settings"])

        for page in self._pages.values():
            if page is not None:
                self._stack.addWidget(page)

        try:
            row = self._db.get_conn().execute("SELECT IFNULL(MAX(id),0) FROM detection_logs").fetchone()
            self._alert_last_id = int(row[0]) if row else 0
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            self._alert_last_id = 0
        self._alert_timer = QTimer(self)
        self._alert_timer.setInterval(2000)
        self._alert_timer.timeout.connect(self._poll_alerts)
        self._alert_timer.start()

        self._cleanup_timer = QTimer(self)
        self._cleanup_timer.setInterval(30000)
        self._cleanup_timer.timeout.connect(self._cleanup_idle_pages)
        self._cleanup_timer.start()

        self._session_user = None
        self._allowed_tabs: set[str] = set()
        self._is_admin = False
        self._nav_labels = nav_label_map()
        self._auth_required = bool(self._db.get_setting("auth_onboarded", False))
        self._blur_effect = None

        self._build_auth_overlay()
        self._init_system_tray()
        if "dashboard" in self._pages:
            page = self._pages.get("dashboard")
            self._schedule_page_activation(page)
            self._stack.setCurrentWidget(self._pages["dashboard"])
            self._sidebar.set_active("dashboard")
            self._current_key = "dashboard"
            self._mark_active("dashboard")
            self._log_page_state("startup")
        self._sidebar.set_access(set(), False)
        if self._auth_required:
            if not self._try_restore_remembered_session():
                self._require_login()
        else:
            self._enter_trusted_session()
            if self._current_key:
                self._acquire_services(self._current_key)

    def _navigate(self, key: str, allow_unauth: bool = False):
        if key not in self._pages:
            return
        spec = self._page_specs.get(key)
        if spec is None:
            return
        if self._pages[key] is None:
            try:
                page = self._page_factory_module().create_page(key, self._rules_service)
                if page is None:
                    return
                self._pages[key] = page
                self._stack.addWidget(page)
                if key == "settings":
                    self._bind_settings_page(page)
            except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
                logger.exception("Failed to create page for %s", key)
                return
        if self._pages[key] is None:
            return
        if not allow_unauth:
            if not self._session_user:
                self._require_login()
                return
            if not self._is_admin and key not in self._allowed_tabs:
                self._show_denied(key)
                return
        current = self._stack.currentWidget()
        prev_key = self._current_key
        if prev_key and self._should_pause_inactive():
            if hasattr(current, "on_deactivated"):
                current.on_deactivated()
        if prev_key:
            self._release_services(prev_key)
        page = self._pages[key]
        self._schedule_page_activation(page)
        self._stack.setCurrentWidget(self._pages[key])
        self._sidebar.set_active(key)
        self._current_key = key
        self._mark_active(key)
        self._acquire_services(key)
        if prev_key and prev_key != key:
            self._maybe_unload_on_leave(prev_key)
        self._log_page_state(f"navigated:{key}")

    def _schedule_page_activation(self, page) -> None:
        if page is None or not hasattr(page, "on_activated"):
            return
        if isinstance(self._stack, AnimatedStackedWidget):
            def _on_finish(widget):
                with contextlib.suppress(Exception):
                    self._stack.transition_finished.disconnect(_on_finish)
                if widget is page:
                    try:
                        page.on_activated()
                    except Exception:
                        pass

            self._stack.transition_finished.connect(_on_finish)
        else:
            QTimer.singleShot(0, page.on_activated)

    def _on_theme_changed(self, theme_name: str) -> None:
        try:
            from frontend.styles import _colors as _c

            self._current_theme = str(theme_name or "dark")
            invalidate_theme_cache()
            with contextlib.suppress(Exception):
                config.invalidate_cache()
            self._reload_theme_modules()
            with contextlib.suppress(Exception):
                self._page_specs = self._page_factory_module().get_page_specs(self._rules_service)
            loaded_keys = [k for k, v in self._pages.items() if v is not None]
            app = QApplication.instance()
            if app is not None:
                app.setStyleSheet(get_theme(self._current_theme))
            else:
                self.setStyleSheet(get_theme(self._current_theme))
            if hasattr(self, "_side_border") and self._side_border is not None:
                self._side_border.setStyleSheet(f"background: {_c._BG_NAV_DARK}; border: none;")
            if hasattr(self, "_sidebar") and hasattr(self._sidebar, "refresh_theme"):
                self._sidebar.refresh_theme()

            for key in list(loaded_keys):
                self._recreate_page(key)


            self.style().unpolish(self)
            self.style().polish(self)
            self.update()
            self._refresh_top_level_widgets()
        except Exception:
            logger.exception("Failed to apply theme at runtime")

    def _reload_theme_modules(self) -> None:
        style_targets = (
            "frontend.styles._colors",
            "frontend.styles._btn_styles",
            "frontend.styles._input_styles",
            "frontend.styles.page_styles",
            "frontend.styles.theme_parts",
        )

        for name in style_targets:
            module = sys.modules.get(name)
            if module is not None:
                with contextlib.suppress(Exception):
                    importlib.reload(module)

        for name in sorted(sys.modules.keys()):
            if not (name.startswith("frontend.pages.") or name.startswith("frontend.widgets.")):
                continue
            module = sys.modules.get(name)
            if module is None:
                continue
            with contextlib.suppress(Exception):
                importlib.reload(module)

        module = sys.modules.get("frontend.state.page_factory")
        if module is not None:
            with contextlib.suppress(Exception):
                importlib.reload(module)

    @staticmethod
    def _page_factory_module():
        return importlib.import_module("frontend.state.page_factory")

    def _bind_settings_page(self, page) -> None:
        if page is None:
            return
        if hasattr(page, "bind_bootstrap_cleared"):
            page.bind_bootstrap_cleared(self._on_bootstrap_cleared)
        if hasattr(page, "theme_changed"):
            with contextlib.suppress(Exception):
                page.theme_changed.disconnect(self._on_theme_changed)
            with contextlib.suppress(Exception):
                page.theme_changed.connect(self._on_theme_changed)
        if hasattr(page, "tab_transitions_changed"):
            with contextlib.suppress(Exception):
                page.tab_transitions_changed.disconnect(self._set_tab_transitions_enabled)
            with contextlib.suppress(Exception):
                page.tab_transitions_changed.connect(self._set_tab_transitions_enabled)

    def _set_tab_transitions_enabled(self, enabled: bool) -> None:
        app = QApplication.instance()
        widgets = app.allWidgets() if app is not None else []
        for widget in widgets:
            if isinstance(widget, AnimatedStackedWidget):
                with contextlib.suppress(Exception):
                    widget.setAnimationsEnabled(enabled)

    def _recreate_current_after_theme(self, expected_key: str) -> None:
        if self._current_key != expected_key:
            return
        if expected_key in self._theme_dirty_pages:
            self._recreate_page(expected_key)
            self._theme_dirty_pages.discard(expected_key)

    def _refresh_top_level_widgets(self) -> None:
        with contextlib.suppress(Exception):
            from frontend.dialogs import apply_popup_theme

            for w in QApplication.topLevelWidgets():
                with contextlib.suppress(Exception):
                    if isinstance(w, QDialog):
                        apply_popup_theme(w, w.styleSheet())
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()

    def _recreate_page(self, key: str) -> None:
        old = self._pages.get(key)
        was_current = self._current_key == key
        if old is not None:
            with contextlib.suppress(Exception):
                self._stack.removeWidget(old)
            with contextlib.suppress(Exception):
                old.deleteLater()
            self._pages[key] = None

        page = self._page_factory_module().create_page(key, self._rules_service)
        if page is None:
            return
        self._pages[key] = page
        self._stack.addWidget(page)
        if key == "settings":
            self._bind_settings_page(page)

        if was_current:
            self._stack.setCurrentWidget(page)
            self._sidebar.set_active(key)
            with contextlib.suppress(Exception):
                if hasattr(page, "on_activated"):
                    page.on_activated()

        with contextlib.suppress(Exception):
            self._sidebar.set_access(self._allowed_tabs, self._is_admin)
        with contextlib.suppress(Exception):
            if self._session_user:
                self._sidebar.set_account(self._session_user)

    def _mark_active(self, key: str) -> None:
        import time

        self._page_last_active[key] = time.time()

    def _should_pause_inactive(self) -> bool:
        return bool(self._db.get_bool("ui_pause_inactive_tabs", True))

    def _should_unload_on_leave(self) -> bool:
        return bool(self._db.get_bool("ui_unload_on_leave", True))

    def _idle_minutes(self) -> int:
        return int(self._db.get_int("ui_unload_idle_min", 5) or 5)

    def _maybe_unload_on_leave(self, key: str) -> None:
        if not self._should_unload_on_leave():
            return
        spec = self._page_specs.get(key)
        if not spec or spec.unload_policy != UnloadPolicy.DESTROY:
            return
        self._unload_page(key)

    def _cleanup_idle_pages(self) -> None:
        if not self._should_unload_on_leave():
            return
        idle_min = self._idle_minutes()
        if idle_min <= 0:
            return
        import time

        now = time.time()
        for key, spec in list(self._page_specs.items()):
            if spec.unload_policy != UnloadPolicy.IDLE:
                continue
            if key == self._current_key:
                continue
            last = self._page_last_active.get(key, 0.0)
            if last and (now - last) >= idle_min * 60:
                self._unload_page(key)

    def _unload_page(self, key: str) -> None:
        page = self._pages.get(key)
        if page is None:
            return
        try:
            if hasattr(page, "on_unload"):
                page.on_unload()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        try:
            self._stack.removeWidget(page)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        page.deleteLater()
        self._pages[key] = None
        self._log_page_state(f"unloaded:{key}")

    def _acquire_services(self, key: str) -> None:
        spec = self._page_specs.get(key)
        if not spec:
            return
        for svc in spec.services:
            self._service_manager.acquire(svc)

    def _release_services(self, key: str) -> None:
        spec = self._page_specs.get(key)
        if not spec:
            return
        for svc in spec.services:
            self._service_manager.release(svc)

    def _log_page_state(self, reason: str) -> None:
        try:
            loaded = [k for k, v in self._pages.items() if v is not None]
            unloaded = [k for k, v in self._pages.items() if v is None]
            logger.info(
                "Page state (%s) current=%s loaded=%s unloaded=%s",
                reason,
                self._current_key,
                loaded,
                unloaded,
            )
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass

    def _build_auth_overlay(self):
        self._auth_overlay = AuthOverlay(self)
        self._login_card = self._auth_overlay.login_card
        self._reset_card = self._auth_overlay.reset_card
        self._auth_stack = self._auth_overlay.stack

        self._login_card.submit.connect(lambda e, p: self._attempt_login(e, p))
        self._login_card.reset_requested.connect(self._show_reset_card)
        self._reset_card.back.connect(self._show_login_card)
        self._reset_card.load_requested.connect(self._load_reset_questions)
        self._reset_card.submit_requested.connect(self._handle_reset_submit)

    def _resize_auth_stack(self, widget):
        self._auth_overlay.resize_stack(widget)

    def _show_reset_card(self):
        self._auth_overlay.show_reset()
        email = self._login_card.email()
        self._reset_card.set_email(email)
        self._reset_card.clear_answers()
        if email:
            self._load_reset_questions(email)

    def _show_login_card(self):
        self._auth_overlay.show_login()

    def _refresh_auth_hint(self):
        try:
            accounts = self._db.get_accounts()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            accounts = []
        if self._db.bootstrap_password_change_required():
            token = self._db.get_setting("bootstrap_token", "")
            if token:
                msg = f"Bootstrap admin: admin@smarteye.local / {token}. Change password in Settings > Accounts."
            else:
                msg = "Bootstrap admin active. Change password in Settings > Accounts."
            self._login_card.set_hint(msg)
            return
        if not accounts:
            self._login_card.set_hint("No accounts yet. Create one in Settings > Accounts.")
        else:
            self._login_card.set_hint("Accounts are managed in Settings > Accounts.")

    def _set_auth_error(self, msg: str):
        self._login_card.set_error(msg)

    def _require_login(self):
        self._stack.setEnabled(False)
        self._sidebar.setEnabled(False)
        self._sidebar.set_access(set(), False)
        self._sidebar.set_account(None)
        self._apply_blur(True)
        self._refresh_auth_hint()
        self._set_auth_error("")
        if self._db.get_bool("remember_login", False):
            self._login_card.set_email(self._db.get_setting("remember_email", ""))
            self._login_card.set_remember(True)
        else:
            self._login_card.set_email("")
            self._login_card.set_remember(False)
        self._resize_auth_stack(self._login_card)
        self._auth_overlay.setGeometry(self.rect())
        self._auth_overlay.show()
        self._auth_overlay.raise_()

    def _enter_trusted_session(self):
        self._session_user = build_trusted_user()
        self._allowed_tabs, self._is_admin = compute_access(self._session_user)
        self._sidebar.setEnabled(True)
        self._stack.setEnabled(True)
        self._sidebar.set_access(self._allowed_tabs, self._is_admin)
        self._sidebar.set_account(self._session_user)
        self._apply_blur(False)
        self._auth_overlay.hide()

    def _attempt_login(self, email=None, password=None):
        email = email if email is not None else self._login_card.email()
        password = password if password is not None else self._login_card.password()
        if not email or not password:
            self._set_auth_error("Enter email and password.")
            return
        email_error = get_email_validation_error(email, allow_internal=True)
        if email_error:
            self._set_auth_error(email_error)
            return
        account = self._db.verify_credentials(email, password)
        if not account:
            self._set_auth_error("Invalid credentials.")
            return
        try:
            self._db.touch_last_login(account["id"])
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass
        self._on_login_success(account)

    def _try_restore_remembered_session(self) -> bool:
        # The retired DB-only automatic session restore is intentionally disabled.
        # "Remember" now only controls whether the email field is prefilled.
        return False

    def _on_login_success(self, account: dict, update_remembered_login: bool = True):
        self._session_user = account
        if self._db.bootstrap_password_change_required(account):
            QMessageBox.warning(
                self,
                "Password change required",
                "The bootstrap admin password must be changed before continuing.",
            )
            self._allowed_tabs = {"settings"}
            self._is_admin = True
            self._sidebar.setEnabled(True)
            self._stack.setEnabled(True)
            self._sidebar.set_access(self._allowed_tabs, self._is_admin)
            self._sidebar.set_account(account)
            self._apply_blur(False)
            self._auth_overlay.hide()
            self._navigate("settings", allow_unauth=True)
            page = self._pages.get("settings")
            if page and hasattr(page, "focus_accounts_tab"):
                page.focus_accounts_tab()
            self._set_auth_error("")
            self._login_card.clear_password()
            return
        self._allowed_tabs, self._is_admin = compute_access(account)
        self._sidebar.setEnabled(True)
        self._stack.setEnabled(True)
        self._sidebar.set_access(self._allowed_tabs, self._is_admin)
        self._sidebar.set_account(account)
        self._apply_blur(False)
        self._auth_overlay.hide()
        target = pick_initial_tab(self._allowed_tabs, self._is_admin, self._pages.keys())
        if target:
            self._navigate(target, allow_unauth=True)
        self._set_auth_error("")
        self._login_card.clear_password()
        if update_remembered_login:
            if self._login_card.remember_me():
                self._db.set_setting("remember_login", True)
                self._db.set_setting("remember_email", account.get("email", ""))
            else:
                self._db.set_setting("remember_login", False)
                self._db.set_setting("remember_email", "")

    def _on_bootstrap_cleared(self):
        if not self._session_user:
            return
        self._allowed_tabs, self._is_admin = compute_access(self._session_user)
        self._sidebar.set_access(self._allowed_tabs, self._is_admin)
        target = pick_initial_tab(self._allowed_tabs, self._is_admin, self._pages.keys())
        if target:
            self._navigate(target, allow_unauth=True)

    def _show_denied(self, key: str):
        label = self._nav_labels.get(key, key.title())
        QMessageBox.warning(self, "Access denied", f"{label} is not enabled for this account.")

    def _logout(self):
        self._session_user = None
        self._allowed_tabs = set()
        self._is_admin = False
        self._sidebar.set_account(None)
        if self._current_key:
            self._release_services(self._current_key)
        self._require_login()

    def _poll_alerts(self):
        try:
            summary = (
                self._db.get_conn()
                .execute(
                    "SELECT COUNT(*) AS cnt, MAX(id) AS max_id "
                    "FROM detection_logs "
                    "WHERE alarm_level>0 AND id>? "
                    "AND COALESCE(rules_triggered, '') NOT LIKE '%\"LivenessFailure\"%'",
                    (self._alert_last_id,),
                )
                .fetchone()
            )
            if not summary or int(summary["cnt"] or 0) <= 0:
                return
            count = int(summary["cnt"] or 0)
            max_id = int(summary["max_id"] or self._alert_last_id)
            self._alert_last_id = max(self._alert_last_id, max_id)
            if not self._db.get_bool("popup_notifications_enabled", True):
                return
            row = (
                self._db.get_conn()
                .execute(
                    "SELECT camera_id, timestamp, rules_triggered "
                    "FROM detection_logs WHERE id=?",
                    (max_id,),
                )
                .fetchone()
            )
            if not row:
                return
            cam_id, ts, rules = row
            subtitle = f"Camera {cam_id} - {ts}"
            if rules:
                subtitle += f" - {rules}"
            if count > 1:
                subtitle = f"{count} new violations. Latest: {subtitle}"
            show_alert(self, "Alert triggered!", subtitle)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            pass

    def _apply_blur(self, enabled: bool):
        try:
            cw = self.centralWidget()
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            return
        if enabled:
            blur = QGraphicsBlurEffect()
            blur.setBlurRadius(12)
            self._blur_effect = blur
            cw.setGraphicsEffect(blur)
        else:
            cw.setGraphicsEffect(None)
            self._blur_effect = None

    def _init_system_tray(self) -> None:
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        tray = QSystemTrayIcon(self)
        tray.setIcon(QIcon(LOGO_ICON_PATH))
        tray.setToolTip("SmartEye")
        menu = QMenu(self)
        restore_action = menu.addAction("Restore")
        quit_action = menu.addAction("Quit")
        restore_action.triggered.connect(self._restore_from_tray)
        quit_action.triggered.connect(self._quit_from_tray)
        tray.activated.connect(self._on_tray_activated)
        tray.setContextMenu(menu)
        tray.show()
        self._tray_icon = tray

    def _on_tray_activated(self, reason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self._restore_from_tray()

    def _restore_from_tray(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def _quit_from_tray(self) -> None:
        self._tray_force_quit = True
        self.close()
        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def _load_reset_questions(self, email: str):
        email = (email or "").strip()
        email_error = get_email_validation_error(email, allow_internal=True)
        if email_error:
            self._reset_card.set_error(email_error)
            return
        row = self._db.get_account_by_email(email)
        if not row:
            self._reset_card.set_error("Email not found.")
            return
        qs = [
            row["sec_q1"] if row["sec_q1"] else "Security question 1",
            row["sec_q2"] if row["sec_q2"] else "Security question 2",
            row["sec_q3"] if row["sec_q3"] else "Security question 3",
        ]
        self._reset_card.set_questions(qs)
        self._reset_card.set_error("")
        self._resize_auth_stack(self._reset_card)

    def _handle_reset_submit(self, email: str, answers: list[str], new_pw: str, confirm: str):
        email = (email or "").strip()
        email_error = get_email_validation_error(email, allow_internal=True)
        if email_error:
            self._reset_card.set_error(email_error)
            return
        if new_pw != confirm:
            self._reset_card.set_error("Passwords do not match.")
            return
        acc = self._db.verify_security_answers(email, answers)
        if not acc:
            self._reset_card.set_error("Answers incorrect.")
            return
        self._db.set_password(acc["id"], new_pw)
        self._reset_card.set_error("Password updated. Sign in.")
        self._reset_card.clear_answers()
        self._show_login_card()

    def resizeEvent(self, event):
        if hasattr(self, "_auth_overlay"):
            self._auth_overlay.setGeometry(self.rect())
        super().resizeEvent(event)

    def closeEvent(self, event):
        if self._is_shutting_down:
            event.accept()
            return

        minimize_to_tray = False
        with contextlib.suppress(Exception):
            minimize_to_tray = bool(self._db.get_bool("minimize_to_tray", False))
        if minimize_to_tray and self._tray_icon is not None and not self._tray_force_quit:
            self.hide()
            event.ignore()
            return

        self._is_shutting_down = True

        with contextlib.suppress(Exception):
            self._alert_timer.stop()
        with contextlib.suppress(Exception):
            self._cleanup_timer.stop()

        with contextlib.suppress(Exception):
            if self._tray_icon is not None:
                self._tray_icon.hide()


        for page in list(self._pages.values()):
            if page is None:
                continue
            with contextlib.suppress(Exception):
                if hasattr(page, "on_unload"):
                    page.on_unload()

        if self._current_key:
            with contextlib.suppress(Exception):
                self._release_services(self._current_key)

        with contextlib.suppress(Exception):
            from backend.camera.camera_manager import get_camera_manager

            get_camera_manager().stop_all()
        with contextlib.suppress(Exception):
            from backend.pipeline.alarm_handler import close_handler

            close_handler()
        with contextlib.suppress(Exception):
            from utils.system_monitor import get_monitor

            get_monitor().stop()
        with contextlib.suppress(Exception):
            from backend.repository import db as _db

            _db.set_setting("window_geometry", bytes(self.saveGeometry().toHex()).decode())
        super().closeEvent(event)

        app = QApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

