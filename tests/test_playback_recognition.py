from __future__ import annotations

import numpy as np

from backend.pipeline.detector_manager import DetectorManager


class _FakeFaceModel:
    is_loaded = True

    def identify(self, embedding, threshold=None):
        return {"id": 1, "name": "Alice", "confidence": 0.91}, 0.91


def test_lightweight_playback_identity_attaches_known_face():
    manager = DetectorManager()
    manager._face_model = _FakeFaceModel()
    face = {
        "bbox": [0, 0, 10, 10],
        "embedding": np.ones(4, dtype=np.float32),
        "confidence": 0.5,
    }

    manager.identify_faces_lightweight(-1000, [face])

    assert face["identity"]["name"] == "Alice"
    assert face["confidence"] == 0.91
