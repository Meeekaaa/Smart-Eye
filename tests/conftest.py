from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.repository import db  # noqa: E402


@pytest.fixture()
def temp_db(tmp_path):
    db.close()
    db.init(str(tmp_path / "smart_eye_test.db"))
    try:
        yield db
    finally:
        db.close()
