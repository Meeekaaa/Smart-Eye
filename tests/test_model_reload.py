from __future__ import annotations


def test_face_model_reload_clears_cached_providers(monkeypatch):
    from backend.models import face_model

    face_model._cached_model_name = "buffalo_s"
    face_model._cached_providers = ["DmlExecutionProvider"]

    def fake_load_internal(self, model_dir="", providers_override=None):
        self._loaded = True

    monkeypatch.setattr(face_model.FaceModel, "_load_internal", fake_load_internal)
    model = face_model.FaceModel()
    model.reload()

    assert face_model._cached_model_name is None
    assert face_model._cached_providers is None
    assert model.is_loaded


def test_reload_all_plugins_replaces_cached_sessions(monkeypatch):
    from backend.models import model_loader

    class FakeModel:
        def __init__(self, marker):
            self.marker = marker
            self.is_loaded = True
            self.class_names = {}

    model_loader.unload_all_plugins()
    model_loader._object_models[99] = FakeModel("old")

    def fake_load_single(row):
        return row["id"], FakeModel(row["name"])

    monkeypatch.setattr(model_loader, "_load_single_plugin", fake_load_single)
    monkeypatch.setattr(model_loader, "_sync_plugin_classes_from_model", lambda plugin_id, model: None)

    loaded = model_loader.reload_all_plugins([{"id": 1, "name": "new"}])

    assert set(loaded) == {1}
    assert loaded[1].marker == "new"
    assert 99 not in loaded
