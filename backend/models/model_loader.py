import logging
import os
import threading
from datetime import datetime

from backend.models.face_model import FaceModel
from backend.models.onnx_object_model import ONNXObjectModel
from backend.repository import db

_logger = logging.getLogger(__name__)

_face_model: FaceModel | None = None
_face_model_lock = threading.Lock()
_prewarm_thread: threading.Thread | None = None
_object_models: dict[int, ONNXObjectModel] = {}
_object_models_lock = threading.Lock()


def _sync_plugin_classes_from_model(plugin_id: int, model: ONNXObjectModel) -> None:
    try:
        names_map = model.class_names or {}
        if not isinstance(names_map, dict) or not names_map:
            return

        existing_rows = db.get_plugin_classes(plugin_id=plugin_id) or []
        by_index = {}
        for row in existing_rows:
            try:
                by_index[int(row.get("class_index"))] = row
            except Exception:
                continue

        for class_idx, class_name in names_map.items():
            try:
                idx = int(class_idx)
            except Exception:
                continue
            name_txt = str(class_name).strip() or str(idx)
            cur = by_index.get(idx)
            if cur is None:
                db.add_plugin_class(plugin_id, idx, name_txt, name_txt)
                continue

            updates = {}
            if (cur.get("class_name") or "") != name_txt:
                updates["class_name"] = name_txt
            if not (cur.get("display_name") or "").strip():
                updates["display_name"] = name_txt
            if updates:
                db.update_plugin_class(cur["id"], **updates)
    except Exception:
        _logger.debug("Failed to sync plugin classes for plugin %s", plugin_id, exc_info=True)


def get_face_model(wait: bool = False) -> FaceModel:
    global _face_model
    if _face_model is not None and _face_model.is_loaded:
        return _face_model

    if wait and _prewarm_thread is not None and _prewarm_thread.is_alive():
        _prewarm_thread.join()

    with _face_model_lock:
        if _face_model is None:
            _face_model = FaceModel()
        if not _face_model.is_loaded and not _face_model.is_loading:
            _face_model.load_async()

    return _face_model


def load_face_model(model_dir: str = "") -> FaceModel:
    return _load_face_model_internal(model_dir=model_dir, async_load=False)


def load_face_model_async(model_dir: str = "") -> FaceModel:
    return _load_face_model_internal(model_dir=model_dir, async_load=True)


def reload_face_model(model_dir: str = "", cpu_only: bool = False) -> FaceModel:
    global _face_model
    with _face_model_lock:
        if _face_model is None:
            _face_model = FaceModel()
        model = _face_model

    providers = ["CPUExecutionProvider"] if cpu_only else None
    model.reload(model_dir, providers_override=providers)
    return model


def reload_face_model_async(model_dir: str = "", cpu_only: bool = False, callback=None) -> FaceModel:
    global _face_model, _prewarm_thread
    with _face_model_lock:
        if _face_model is None:
            _face_model = FaceModel()
        model = _face_model

    providers = ["CPUExecutionProvider"] if cpu_only else None

    def _async_reload():
        try:
            model.reload(model_dir, providers_override=providers)
            if callback:
                callback(success=True, error=None)
        except Exception as exc:
            _logger.error("Async face model reload failed: %s", exc, exc_info=True)
            if callback:
                callback(success=False, error=str(exc))

    _prewarm_thread = threading.Thread(target=_async_reload, daemon=True, name="FaceModelAsyncReload")
    _prewarm_thread.start()
    return model


def _load_face_model_internal(model_dir: str = "", async_load: bool = False) -> FaceModel:
    global _face_model
    with _face_model_lock:
        if _face_model is None:
            _face_model = FaceModel()
        if not _face_model.is_loaded:
            if async_load:
                _face_model.load_async(model_dir)
            else:
                _face_model.load(model_dir)
    return _face_model


def _load_single_plugin(plugin_row: dict) -> tuple[int, ONNXObjectModel | None]:
    pid = plugin_row["id"]
    try:
        confidence = plugin_row.get("confidence", 0.6)

        weight_path = plugin_row.get("weight_path", "")
        preferred_provider = plugin_row.get("preferred_provider", "auto")
        if weight_path and not os.path.isfile(weight_path):
            msg = f"Model file missing: {weight_path}"
            try:
                db.update_plugin(pid, enabled=0, last_error=msg, last_error_at=datetime.utcnow().isoformat())
            except Exception:
                _logger.debug("Failed to store missing file error for plugin %s", pid, exc_info=True)
            _logger.error(msg)
            return pid, None
        model = ONNXObjectModel(
            weight_path=weight_path,
            confidence=confidence,
            classes=None,
            preferred_provider=preferred_provider,
        )
        model.load()

        if isinstance(model, ONNXObjectModel):
            try:
                if model.using_cpu_fallback:
                    db.update_plugin(
                        pid,
                        last_provider=model.last_provider or "CPUExecutionProvider",
                        last_error=model.last_error or "DML warmup failed; fell back to CPU",
                        last_error_at=datetime.utcnow().isoformat(),
                    )
                else:
                    db.update_plugin(
                        pid,
                        last_provider=model.last_provider or "DmlExecutionProvider",
                        last_error=None,
                        last_error_at=None,
                    )
            except Exception:
                _logger.debug("Failed to persist provider info for plugin %s", pid, exc_info=True)
        return pid, model
    except Exception as e:
        _logger.error("Failed to load plugin %s: %s", pid, e, exc_info=True)
        try:
            db.update_plugin(
                pid,
                enabled=0,
                last_error=str(e),
                last_error_at=datetime.utcnow().isoformat(),
            )
        except Exception:
            _logger.debug("Failed to record plugin load error for %s", pid, exc_info=True)
        return pid, None


def load_plugin(plugin_row: dict) -> ONNXObjectModel:
    pid = plugin_row["id"]
    confidence = plugin_row.get("confidence", 0.6)

    with _object_models_lock:
        existing = _object_models.get(pid)
        if existing is not None and existing.is_loaded:
            existing.confidence = confidence
            return existing

    _, model = _load_single_plugin(plugin_row)
    if model is None:
        return None

    _sync_plugin_classes_from_model(pid, model)

    with _object_models_lock:
        _object_models[pid] = model
    return model


def unload_plugin(plugin_id: int) -> None:
    with _object_models_lock:
        _object_models.pop(plugin_id, None)


def unload_all_plugins() -> None:
    with _object_models_lock:
        _object_models.clear()


def reload_all_plugins(plugin_rows: list[dict] | None = None) -> dict[int, ONNXObjectModel]:
    rows = plugin_rows if plugin_rows is not None else db.get_plugins(enabled_only=True)
    loaded: dict[int, ONNXObjectModel] = {}

    with _object_models_lock:
        _object_models.clear()

    for row in rows or []:
        pid, model = _load_single_plugin(row)
        if model is None:
            continue
        _sync_plugin_classes_from_model(pid, model)
        loaded[pid] = model

    with _object_models_lock:
        _object_models.update(loaded)
        return dict(_object_models)


def get_provider_summary():
    summary = []
    try:
        fm = get_face_model(wait=True)
        if fm and fm.is_loaded:
            prov = ", ".join(fm.providers_used) if fm.providers_used else "CPU"
            summary.append({"name": "Face", "provider": prov, "type": "face"})
    except Exception:
        pass

    with _object_models_lock:
        items = list(_object_models.items())

    for pid, model in items:
        entry = {"name": f"Plugin {pid}", "provider": "CPU", "type": "object", "id": pid}
        try:
            row = db.get_plugin(pid)
            if row and row.get("name"):
                entry["name"] = row["name"]
        except Exception:
            pass

        try:
            if hasattr(model, "provider"):
                entry["provider"] = model.provider
            elif hasattr(model, "using_cpu_fallback") and model.using_cpu_fallback:
                entry["provider"] = "CPU"
            else:
                entry["provider"] = "GPU"
        except Exception:
            pass
        summary.append(entry)
    return summary


def get_loaded_plugins() -> dict[int, ONNXObjectModel]:
    with _object_models_lock:
        return dict(_object_models)
