from __future__ import annotations

import os
from datetime import datetime

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from frontend.pages.playback._page import _snapshot_epoch


def test_snapshot_epoch_accepts_database_datetime(tmp_path):
    path = tmp_path / "snapshot.jpg"
    path.write_bytes(b"img")

    actual = _snapshot_epoch("2026-06-01 12:39:21", str(path))

    assert actual == int(datetime(2026, 6, 1, 12, 39, 21).timestamp())


def test_snapshot_epoch_falls_back_to_file_time(tmp_path):
    path = tmp_path / "snapshot.jpg"
    path.write_bytes(b"img")
    os.utime(path, (1234, 1234))

    assert _snapshot_epoch("not a timestamp", str(path)) == 1234
