import contextlib
import logging
import os
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime

import cv2
from PySide6.QtCore import QTimer, qInstallMessageHandler
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from backend.repository import db

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
LATEST_LOG = LOG_DIR / "smarteye.latest.log"
SUBDIRS = ["snapshots", "faces", "heatmaps", "backups", "models"]


def _set_process_priority():
    with contextlib.suppress(Exception):
        import psutil

        p = psutil.Process()
        with contextlib.suppress(Exception):
            p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
        with contextlib.suppress(Exception):
            p.nice(10)
        return
    with contextlib.suppress(Exception):
        import ctypes

        handle = ctypes.windll.kernel32.GetCurrentProcess()
        ctypes.windll.kernel32.SetPriorityClass(handle, 0x4000)


def _configure_logging():
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    debug_flag = os.environ.get("SMARTEYE_DEBUG", "0").lower() in ("1", "true", "yes")
    ts = datetime.now().strftime("smarteye-%Y%m%d-%H%M%S.log")
    session_log = LOG_DIR / ts

    root_logger = logging.getLogger()
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    level = logging.DEBUG if debug_flag else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s")

    session_handler = RotatingFileHandler(session_log, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    latest_handler = RotatingFileHandler(LATEST_LOG, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    stream = logging.StreamHandler()

    for h in (session_handler, latest_handler, stream):
        h.setFormatter(fmt)
        h.setLevel(level)
        root_logger.addHandler(h)

    root_logger.setLevel(level)
    logging.captureWarnings(True)

    logging.getLogger("backend.pipeline.detector_manager").setLevel(logging.INFO)
    return root_logger


def _log_uncaught_exception(exc_type, exc_value, exc_traceback):
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.getLogger().exception("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


def _thread_excepthook(args):
    logging.getLogger().exception("Uncaught thread exception: %s", args)


def _qt_message_handler(mode, context, message):
    with contextlib.suppress(Exception):
        if "QFont::setPointSize" in message:
            return
        if "setGeometry" in message:
            return
    try:
        logging.getLogger("qt").warning(message)
    except Exception:
        with contextlib.suppress(Exception):
            sys.stderr.write(message + "\n")


def _init_directories():
    for sub in SUBDIRS:
        DATA_DIR.joinpath(sub).mkdir(parents=True, exist_ok=True)


def _suppress_ort_logging():
    with contextlib.suppress(Exception):
        os.environ.setdefault("ORT_LOG_LEVEL", "WARNING")
        import onnxruntime as _ort

        with contextlib.suppress(Exception):
            _ort.set_default_logger_severity(3)
        logging.getLogger("onnxruntime").setLevel(logging.WARNING)


def main():
    os.chdir(BASE_DIR)
    _set_process_priority()
    _configure_logging()
    sys.excepthook = _log_uncaught_exception
    with contextlib.suppress(Exception):
        threading.excepthook = _thread_excepthook
    qInstallMessageHandler(_qt_message_handler)
    with contextlib.suppress(Exception):
        cv2.setNumThreads(1)
    with contextlib.suppress(Exception):
        cv2.ocl.setUseOpenCL(False)
    _init_directories()
    db.init(str(DATA_DIR / "smarteye.db"))
    db.ensure_default_account()
    _suppress_ort_logging()
    try:
        from utils.resource_limiter import apply_limits

        apply_limits(
            db.get_bool("limit_resources", False),
            db.get_int("max_cpu_cores", db.get_int("max_threads", 2) or 2) or 2,
            db.get_int("max_ram_mb", 4096) or 4096,
        )
    except Exception:
        pass
    from utils.system_monitor import get_monitor

    monitor = get_monitor()
    monitor.start()
    from frontend.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName("SmartEye")
    app.setOrganizationName("SmartEye")

    from frontend.widgets.press_animation_filter import install_press_animations

    try:
        install_press_animations(app, press_opacity=0.88)
    except Exception:
        pass
    try:
        from frontend.widgets.combobox_popup import setup_combobox_popup_behavior

        setup_combobox_popup_behavior(app)
    except Exception:
        pass

    font = QFont("Segoe UI", 10)
    app.setFont(font)
    from frontend.app_theme import get_theme

    app.setStyleSheet(get_theme())
    try:
        from frontend.dialogs import patch_messagebox

        patch_messagebox()
    except Exception:
        pass
    window = MainWindow()
    window.show()
    try:
        import ctypes

        hwnd = int(window.winId())
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int))
    except Exception:
        pass
    if db.get_bool("auto_start_cameras", False):
        from backend.camera.camera_manager import get_camera_manager

        QTimer.singleShot(150, get_camera_manager().start_all_enabled)
    exit_code = app.exec()
    monitor.stop()
    try:
        from backend.camera.camera_manager import get_camera_manager

        get_camera_manager().stop_all()
    except Exception:
        pass
    db.close()
    sys.exit(exit_code)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback

        traceback.print_exc()
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            with open(LATEST_LOG, "a", encoding="utf-8") as f:
                f.write("\n=== Unhandled exception ===\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        raise
