#!/usr/bin/env bash

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$ROOT/.venv/Scripts/python.exe"
ENTRY="$ROOT/main.py"
OUT_DIR="$ROOT/build"
DIST_NAME="SmartEye"

JOBS="${SMARTEYE_JOBS:-}"
LTO="${SMARTEYE_LTO:-yes}"
MAX_DIST_MB="${SMARTEYE_MAX_DIST_MB:-3072}"
NUITKA_VERSION="${SMARTEYE_NUITKA_VERSION:-2.7.11}"
ICON_PATH="frontend/assets/icons/icon.ico"

if [[ -z "$JOBS" ]]; then
    JOBS="2"
fi

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'; BLD='\033[1m'; RST='\033[0m'
info()  { echo -e "${GRN}[INFO]${RST}  $*"; }
warn()  { echo -e "${YLW}[WARN]${RST}  $*"; }
error() { echo -e "${RED}[ERR ]${RST}  $*" >&2; }

if [[ ! -f "$PYTHON" ]]; then
    error "venv Python not found: $PYTHON"
    error "Make sure the Smart-Eye venv exists first."
    exit 1
fi

if [[ ! -f "$ENTRY" ]]; then
    error "Entry point not found: $ENTRY"
    exit 1
fi

APP_VERSION=$("$PYTHON" -c "import json; d=json.load(open('app_info.json')); print(d['version'])" 2>/dev/null || echo "")
if [[ -z "$APP_VERSION" ]]; then
    error "Could not read version from app_info.json"
    exit 1
fi
if [[ ! "$APP_VERSION" =~ ^[0-9]+\.[0-9]+ ]]; then
    error "Version '$APP_VERSION' in app_info.json does not match expected format (e.g. 1.0 or 1.0.0)"
    exit 1
fi

FREE_MB=$(powershell.exe -NoProfile -Command \
    "(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory / 1024" 2>/dev/null \
    | tr -d '[:space:]' || echo "0")
FREE_MB=${FREE_MB%.*}

echo -e "${BLD}=== Smart Eye v${APP_VERSION} - Safe Nuitka Build ===${RST}"
info "Python   : $PYTHON"
info "Entry    : $ENTRY"
info "Output   : $OUT_DIR"
info "Jobs     : ${JOBS:-auto}"
info "LTO      : $LTO"
info "Free RAM : ~${FREE_MB} MB"
echo ""

if (( FREE_MB > 0 && FREE_MB < 3500 )); then
    warn "Less than 3.5 GB free RAM detected."
    warn "Close other applications before continuing."
    warn "Consider increasing the Windows page file to at least 16 GB."
    read -rp "Press Enter to continue anyway, or Ctrl-C to abort..."
    echo ""
fi

"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install -r "$ROOT/requirements.txt"
"$PYTHON" -m pip install --upgrade setuptools
"$PYTHON" -m pip show setuptools >/dev/null 2>&1 || true
"$PYTHON" -m pip install --upgrade ordered-set zstandard "nuitka==$NUITKA_VERSION"

NUITKA_VER=$("$PYTHON" -m nuitka --version 2>&1 | head -1)
info "Nuitka   : $NUITKA_VER"
echo ""

info "Removing duplicate top-level insightface path (workflow parity)..."
PY_PREFIX=$("$PYTHON" -c "import sys; print(sys.prefix)")
TOP_LEVEL_INSIGHTFACE="$PY_PREFIX/insightface"
if [[ -d "$TOP_LEVEL_INSIGHTFACE" ]]; then
    warn "Removing duplicate package path: $TOP_LEVEL_INSIGHTFACE"
    rm -rf "$TOP_LEVEL_INSIGHTFACE"
    info "Done."
else
    info "No duplicate top-level insightface path detected."
fi
"$PYTHON" -c "import insightface, sys; print('Python prefix:', sys.prefix); print('insightface module:', insightface.__file__)"
echo ""

if [[ ! -d "$ROOT/data/models" && -n "${MODEL_BUNDLE_URL:-}" ]]; then
    info "MODEL_BUNDLE_URL set - downloading model bundle..."
    "$PYTHON" - <<'PY'
import os
import pathlib
import tempfile
import urllib.request
import zipfile

root = pathlib.Path(".").resolve()
url = os.environ.get("MODEL_BUNDLE_URL", "").strip()
if url:
    models_dir = root / "data" / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        tmp_path = pathlib.Path(tmp.name)
    try:
        urllib.request.urlretrieve(url, tmp_path)
        with zipfile.ZipFile(tmp_path, "r") as zf:
            zf.extractall(models_dir)
        print(f"[ok] model bundle extracted to {models_dir}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
else:
    print("[info] MODEL_BUNDLE_URL not set; skipping model download")
PY
elif [[ ! -d "$ROOT/data/models" ]]; then
    info "MODEL_BUNDLE_URL not set; skipping model download"
else
    info "data/models already exists - skipping model download"
fi
echo ""

info "Collecting PySide6 plugins for packaging..."
PYSIDE_PLUGINS_SRC=$("$PYTHON" -c "import PySide6, os; print(os.path.join(os.path.dirname(PySide6.__file__), 'plugins'))" 2>/dev/null || echo "")
PYSIDE_PLUGINS_DST="$ROOT/frontend/pyside6_plugins"
if [[ -n "$PYSIDE_PLUGINS_SRC" && -d "$PYSIDE_PLUGINS_SRC" ]]; then
    rm -rf "$PYSIDE_PLUGINS_DST"
    cp -r "$PYSIDE_PLUGINS_SRC" "$PYSIDE_PLUGINS_DST"
    info "PySide6 plugins copied to frontend/pyside6_plugins"
else
    warn "PySide6 plugins path not found: $PYSIDE_PLUGINS_SRC"
fi
echo ""

info "Staging scientific runtime libs (scipy.libs, numpy.libs)..."
BUILD_ASSETS_DIR="$ROOT/build_assets"
mkdir -p "$BUILD_ASSETS_DIR"
"$PYTHON" - <<'PY'
import importlib.util
import pathlib
import shutil

root = pathlib.Path(".").resolve()
out_root = root / "build_assets"
out_root.mkdir(exist_ok=True)

def stage_lib_dir(pkg_name: str):
    spec = importlib.util.find_spec(pkg_name)
    if not spec or not spec.origin:
        print(f"[warn] could not resolve {pkg_name}")
        return
    pkg_dir = pathlib.Path(spec.origin).resolve().parent
    libs_dir = pkg_dir.parent / f"{pkg_name}.libs"
    if not libs_dir.exists():
        print(f"[info] no {pkg_name}.libs at {libs_dir}")
        return
    dst = out_root / f"{pkg_name}.libs"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(libs_dir, dst)
    print(f"[ok] staged {libs_dir} -> {dst}")

stage_lib_dir("scipy")
stage_lib_dir("numpy")
PY
echo ""

HAS_OBJ_MODEL=false
if [[ -f "$ROOT/data/models/Obj-Detection.onnx" ]]; then
    HAS_OBJ_MODEL=true
    info "Object model detected: data/models/Obj-Detection.onnx"
fi

rm -rf "$OUT_DIR"

warn "Compilation can take a long time on resource-limited machines."
warn "Do NOT open heavy applications while building."
echo ""

cd "$ROOT"

NUITKA_ARGS=(
    --standalone
    --output-dir="$OUT_DIR"
    --output-filename="$DIST_NAME"
    --lto="$LTO"
    --windows-console-mode=disable
    --windows-icon-from-ico="$ICON_PATH"
    --enable-plugin=pyside6
    --include-package=psutil
    --include-package=PySide6
    --include-package=shiboken6
    --include-package=reportlab
    --include-package=requests
    --include-package=pyqtgraph
    --include-package=onnx
    --include-package=onnxruntime
    --include-package=insightface
    --include-package=GPUtil
    --include-package=wmi
    --include-package=backend
    --include-package=frontend
    --include-package=utils
    --include-package=streamlink
    --include-package=numpy
    --include-package=scipy
    --include-package=skimage
    --include-package=albumentations
    --include-module=scipy._cyutility
    --include-module=scipy._lib._ccallback_c
    --include-package-data=reportlab
    --include-package-data=pyqtgraph
    --include-package-data=insightface
    --include-package-data=onnxruntime
    --include-package-data=streamlink
    --include-package-data=numpy
    --include-package-data=scipy
    --include-package-data=skimage
    --include-package-data=albumentations
    --include-data-dir="frontend/assets=frontend/assets"
    --include-data-dir="frontend/pyside6_plugins=PySide6/plugins"
    --include-data-file="app_info.json=app_info.json"
    --include-data-file="backend/database/schema.sql=backend/database/schema.sql"
    --nofollow-import-to=numpy.distutils
    --nofollow-import-to=numpy.random.tests
    --nofollow-import-to=numpy.random.tests.test_extending
    --nofollow-import-to=scipy.tests
    --nofollow-import-to=scipy.stats.tests
    --nofollow-import-to=scipy.stats.tests.test_censored_data
    --nofollow-import-to=scipy.stats.tests.test_continuous
    --nofollow-import-to=sympy.polys.polyquinticconst
    --nofollow-import-to=trio.testing
    --nofollow-import-to=PySide6.QtWebEngine
    --nofollow-import-to=PySide6.QtWebEngineWidgets
    --nofollow-import-to=PySide6.QtWebEngineCore
    --nofollow-import-to=PySide6.Qt3DCore
    --nofollow-import-to=PySide6.Qt3DRender
    --nofollow-import-to=PySide6.Qt3DInput
    --nofollow-import-to=PySide6.Qt3DLogic
    --nofollow-import-to=PySide6.Qt3DAnimation
    --nofollow-import-to=PySide6.Qt3DExtras
    --nofollow-import-to=PySide6.QtCharts
    --nofollow-import-to=PySide6.QtDataVisualization
    --nofollow-import-to=PySide6.QtLocation
    --nofollow-import-to=PySide6.QtPositioning
    --nofollow-import-to=PySide6.QtRemoteObjects
    --nofollow-import-to=PySide6.QtSensors
    --nofollow-import-to=PySide6.QtSerialPort
    --nofollow-import-to=PySide6.QtTextToSpeech
    --nofollow-import-to=PySide6.QtBluetooth
    --nofollow-import-to=PySide6.QtNfc
    --nofollow-import-to=onnxruntime.training
    --nofollow-import-to=onnxruntime.tools
    --nofollow-import-to=onnx.backend.test
    --nofollow-import-to=cv2.samples
    --nofollow-import-to=pyqtgraph.tests
    --nofollow-import-to=pyqtgraph.opengl
    --nofollow-import-to=pyqtgraph.exporters
    --nofollow-import-to=unittest
    --nofollow-import-to=test
    --nofollow-import-to=distutils
    --nofollow-import-to=setuptools
    --nofollow-import-to=pkg_resources
    --nofollow-import-to=pip
    --nofollow-import-to=doctest
    --noinclude-data-files=qt6webenginecore.dll
    --noinclude-data-files=qt6webenginequick.dll
    --noinclude-data-files=qt6quick.dll
    --noinclude-data-files=qt6quick3d.dll
    --noinclude-data-files=qt6quick3druntimerender.dll
    --noinclude-data-files=qt6quick3dutils.dll
    --noinclude-data-files=qt6quickcontrols2.dll
    --noinclude-data-files=qt6quickshapes.dll
    --noinclude-data-files=qt6quicktemplates2.dll
    --noinclude-data-files=qt6quicktest.dll
    --noinclude-data-files=qt6quickwidgets.dll
    --noinclude-data-files=qt6qml.dll
    --noinclude-data-files=qt6qmlmeta.dll
    --noinclude-data-files=qt6qmlmodels.dll
    --noinclude-data-files=qt6qmlworkerscript.dll
    --noinclude-data-files=qt6scxml.dll
    --noinclude-data-files=qt6spatialaudio.dll
    --noinclude-data-files=skimage/data/*
    --noinclude-data-files=pyqtgraph/examples/*
    --assume-yes-for-downloads
    --show-scons
)

if [[ -n "$JOBS" ]]; then
    NUITKA_ARGS+=(--jobs="$JOBS")
fi

if [[ -d "$ROOT/build_assets/scipy.libs" ]]; then
    NUITKA_ARGS+=(--include-data-dir="build_assets/scipy.libs=scipy.libs")
fi

if [[ -d "$ROOT/build_assets/numpy.libs" ]]; then
    NUITKA_ARGS+=(--include-data-dir="build_assets/numpy.libs=numpy.libs")
fi

if [[ "$HAS_OBJ_MODEL" == true ]]; then
    NUITKA_ARGS+=(--include-data-file="data/models/Obj-Detection.onnx=data/models/Obj-Detection.onnx")
fi

"$PYTHON" -m nuitka "${NUITKA_ARGS[@]}" "$ENTRY"

DIST_DIR="$OUT_DIR/main.dist"
EXE="$DIST_DIR/${DIST_NAME}.exe"

echo ""
echo -e "${BLD}=== Build finished ===${RST}"

if [[ -f "$EXE" ]]; then
    SIZE=$(du -sh "$EXE" 2>/dev/null | cut -f1)
    info "Executable : $EXE  ($SIZE)"
    info "Dist folder: $DIST_DIR"
    echo ""

    info "To run: start \"\" \"$EXE\""
    echo ""

    DIST_MB=$(du -sm "$DIST_DIR" | cut -f1)
    if (( DIST_MB > MAX_DIST_MB )); then
        error "Dist folder is ${DIST_MB} MB, over limit ${MAX_DIST_MB} MB."
        error "Rebuild without models (default) or lower dependency footprint."
        exit 2
    fi
    info "Dist size  : ${DIST_MB} MB (limit: ${MAX_DIST_MB} MB)"
    info "Version    : v${APP_VERSION}"
    echo ""

    ARCHIVE_NAME="SmartEye-v${APP_VERSION}-main-dist.7z"
    read -rp "Create 7z archive '$ARCHIVE_NAME'? [y/N] " zip_ans
    if [[ "${zip_ans,,}" == "y" ]]; then
        SEVENZIP=""
        for candidate in \
            "/c/Program Files/7-Zip/7z.exe" \
            "/c/Program Files (x86)/7-Zip/7z.exe" \
            "$(command -v 7z 2>/dev/null || true)" \
            "$(command -v 7za 2>/dev/null || true)"; do
            if [[ -n "$candidate" && -x "$candidate" ]]; then
                SEVENZIP="$candidate"
                break
            fi
        done

        if [[ -n "$SEVENZIP" ]]; then
            "$SEVENZIP" a -t7z -m0=lzma2 -mx=9 -mmt=on -ms=on "$OUT_DIR/$ARCHIVE_NAME" "$DIST_DIR/"*
            info "Archive created: $OUT_DIR/$ARCHIVE_NAME"
        else
            warn "7-Zip not found, falling back to zip..."
            ARCHIVE_NAME="SmartEye-v${APP_VERSION}-main-dist.zip"
            (cd "$DIST_DIR" && zip -r "$OUT_DIR/$ARCHIVE_NAME" .)
            info "Archive created: $OUT_DIR/$ARCHIVE_NAME"
        fi
    fi
    echo ""

    BUILD_CACHE="$OUT_DIR/main.build"
    if [[ -d "$BUILD_CACHE" ]]; then
        read -rp "Delete intermediate build cache ($BUILD_CACHE)? [y/N] " ans
        if [[ "${ans,,}" == "y" ]]; then
            rm -rf "$BUILD_CACHE"
            info "Build cache deleted."
        fi
    fi
else
    error "${DIST_NAME}.exe not found - check the Nuitka output above for errors."
    exit 1
fi
