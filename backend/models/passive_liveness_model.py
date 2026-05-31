import logging
import math
import os

import cv2
import numpy as np

from backend.repository import db
from utils import config

_logger = logging.getLogger(__name__)


def _normalize_provider_preference(raw: str | None) -> str:
    val = str(raw or "auto").strip().lower()
    aliases = {
        "nvidia": "cuda",
        "gpu": "auto",
        "directml": "dml",
    }
    val = aliases.get(val, val)
    return val if val in ("auto", "cuda", "dml", "rocm", "coreml", "openvino", "cpu") else "auto"


def _provider_preference() -> str:
    env_pref = os.getenv("SMARTEYE_ONNX_PROVIDER", "").strip()
    if env_pref:
        return _normalize_provider_preference(env_pref)
    try:
        pref = db.get_setting("liveness_onnx_provider_preference", None)
        if pref is None:
            pref = db.get_setting("face_onnx_provider_preference", None)
        if pref is None:
            pref = db.get_setting("onnx_provider_preference", "auto")
        return _normalize_provider_preference(pref)
    except Exception:
        return "auto"


def _select_providers():
    try:
        import onnxruntime as ort

        available = ort.get_available_providers() or []
    except Exception:
        return ["CPUExecutionProvider"]

    pref = _provider_preference()
    gpu_allowed = bool(config.gpu_enabled())
    pref_map = {
        "cuda": "CUDAExecutionProvider",
        "dml": "DmlExecutionProvider",
        "rocm": "ROCMExecutionProvider",
        "coreml": "CoreMLExecutionProvider",
        "openvino": "OpenVINOExecutionProvider",
    }

    providers = []
    if gpu_allowed and pref not in ("auto", "cpu"):
        mapped = pref_map.get(pref, pref)
        if mapped in available and mapped != "CPUExecutionProvider":
            providers.append(mapped)
    if gpu_allowed and not providers and pref != "cpu":
        for provider in (
            "CUDAExecutionProvider",
            "DmlExecutionProvider",
            "ROCMExecutionProvider",
            "CoreMLExecutionProvider",
            "OpenVINOExecutionProvider",
        ):
            if provider in available:
                providers.append(provider)
                break
    if "CPUExecutionProvider" in available or not providers:
        providers.append("CPUExecutionProvider")
    return providers


def _softmax(values: np.ndarray) -> np.ndarray:
    vals = values.astype(np.float32)
    vals = vals - np.max(vals)
    exp = np.exp(vals)
    denom = float(np.sum(exp))
    return exp / denom if denom > 0 else exp


class PassiveLivenessModel:
    def __init__(self, model_path: str):
        self._model_path = model_path
        self._session = None
        self._input_name = ""
        self._input_shape = (80, 80)
        self._input_layout = "nchw"
        self._loaded = False
        self._last_error: str | None = None

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    @property
    def last_error(self) -> str | None:
        return self._last_error

    def load(self) -> bool:
        if self._loaded:
            return True
        self._last_error = None
        if not self._model_path or not os.path.isfile(self._model_path):
            self._last_error = "model file not found"
            return False
        try:
            import onnxruntime as ort

            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = 2
            options.inter_op_num_threads = 1
            options.log_severity_level = 3
            self._session = ort.InferenceSession(self._model_path, sess_options=options, providers=_select_providers())
            inputs = self._session.get_inputs()
            if not inputs:
                raise RuntimeError("ONNX model has no inputs")
            inp = inputs[0]
            self._input_name = inp.name
            shape = list(inp.shape or [])
            if len(shape) == 4:
                if shape[1] in (1, 3):
                    self._input_layout = "nchw"
                    h = int(shape[2]) if isinstance(shape[2], int) else 80
                    w = int(shape[3]) if isinstance(shape[3], int) else 80
                else:
                    self._input_layout = "nhwc"
                    h = int(shape[1]) if isinstance(shape[1], int) else 80
                    w = int(shape[2]) if isinstance(shape[2], int) else 80
                self._input_shape = (max(16, w), max(16, h))
            self._loaded = True
            return True
        except Exception as exc:
            self._last_error = str(exc)
            self._loaded = False
            _logger.warning("Passive liveness model load failed path=%s error=%s", self._model_path, exc, exc_info=True)
            return False

    def predict(self, frame, bbox) -> float | None:
        if not self.load() or self._session is None:
            return None
        try:
            x1, y1, x2, y2 = [int(v) for v in bbox]
            h, w = frame.shape[:2]
            bw = max(1, x2 - x1)
            bh = max(1, y2 - y1)
            try:
                crop_scale = float(db.get_setting("liveness_passive_crop_scale", 2.7) or 2.7)
            except Exception:
                crop_scale = 2.7
            crop_scale = max(1.0, min(4.5, crop_scale))
            cx = x1 + (bw / 2.0)
            cy = y1 + (bh / 2.0)
            crop_w = bw * crop_scale
            crop_h = bh * crop_scale
            x1 = max(0, int(round(cx - crop_w / 2.0)))
            y1 = max(0, int(round(cy - crop_h / 2.0)))
            x2 = min(w, int(round(cx + crop_w / 2.0)))
            y2 = min(h, int(round(cy + crop_h / 2.0)))
            if x2 <= x1 or y2 <= y1:
                return None
            crop = frame[y1:y2, x1:x2]
            inp_w, inp_h = self._input_shape
            crop = cv2.resize(crop, (inp_w, inp_h), interpolation=cv2.INTER_LINEAR)
            try:
                color_order = str(db.get_setting("liveness_passive_color_order", "bgr") or "bgr").strip().lower()
            except Exception:
                color_order = "bgr"
            if color_order == "rgb":
                crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            crop = crop.astype(np.float32)
            norm = str(db.get_setting("liveness_passive_normalization", "raw") or "raw").strip().lower()
            if norm in ("raw", "none", "0_255"):
                pass
            elif norm in ("minus_one_one", "-1_1"):
                crop = (crop / 127.5) - 1.0
            elif norm == "imagenet":
                crop = crop / 255.0
                crop = (crop - np.array([0.485, 0.456, 0.406], dtype=np.float32)) / np.array(
                    [0.229, 0.224, 0.225], dtype=np.float32
                )
            else:
                crop = crop / 255.0
            if self._input_layout == "nchw":
                input_tensor = np.transpose(crop, (2, 0, 1))[None, ...].astype(np.float32)
            else:
                input_tensor = crop[None, ...].astype(np.float32)
            outputs = self._session.run(None, {self._input_name: input_tensor})
            if not outputs:
                return None
            values = np.asarray(outputs[0]).reshape(-1).astype(np.float32)
            if values.size == 0:
                return None
            if values.size == 1:
                raw = float(values[0])
                if raw < 0.0 or raw > 1.0:
                    raw = 1.0 / (1.0 + math.exp(-max(-50.0, min(50.0, raw))))
                return max(0.0, min(1.0, raw))
            probs = _softmax(values)
            try:
                real_idx = int(db.get_setting("liveness_passive_real_class_index", 1) or 1)
            except Exception:
                real_idx = 1
            real_idx = max(0, min(real_idx, int(probs.size) - 1))
            return float(probs[real_idx])
        except Exception:
            _logger.debug("Passive liveness inference failed", exc_info=True)
            return None


_MODEL_CACHE: dict[str, PassiveLivenessModel] = {}


def get_passive_liveness_model(model_path: str) -> PassiveLivenessModel | None:
    path = str(model_path or "").strip()
    if not path:
        return None
    model = _MODEL_CACHE.get(path)
    if model is None:
        model = PassiveLivenessModel(path)
        _MODEL_CACHE[path] = model
    return model
