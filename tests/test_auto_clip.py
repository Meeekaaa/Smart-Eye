from __future__ import annotations

import numpy as np

from backend.camera.camera_thread import CameraThread
from backend.camera.playback_thread import PlaybackThread


def test_live_clip_window_ends_at_violation_timestamp():
    thread = CameraThread(1, "0")
    thread._clip_seconds = 5

    for idx in range(8):
        frame = np.full((2, 2, 3), idx, dtype=np.uint8)
        thread._append_clip_frame(frame, float(idx))

    selected = thread._clip_window_frames(event_ts=5.0)

    assert [int(frame[0, 0, 0]) for _ts, frame in selected] == [0, 1, 2, 3, 4, 5]


def test_live_clip_buffer_keeps_latency_slack_for_late_inference_result():
    thread = CameraThread(1, "0")
    thread._clip_seconds = 5

    for idx in range(9):
        frame = np.full((2, 2, 3), idx, dtype=np.uint8)
        thread._append_clip_frame(frame, float(idx))

    selected = thread._clip_window_frames(event_ts=3.0)

    assert [int(frame[0, 0, 0]) for _ts, frame in selected] == [0, 1, 2, 3]


def test_playback_clip_window_ends_at_violation_frame():
    thread = PlaybackThread("missing.mp4")
    for idx in range(10):
        thread._frame_buffer.append((idx, np.full((2, 2, 3), idx, dtype=np.uint8)))

    selected = thread._buffered_clip_frames(fps=2.0, event_frame_idx=6)

    assert [int(frame[0, 0, 0]) for frame in selected] == [0, 1, 2, 3, 4, 5, 6]


def test_disabling_playback_autoclip_does_not_clear_rolling_buffer():
    thread = PlaybackThread("missing.mp4")
    thread._frame_buffer.append((1, np.zeros((2, 2, 3), dtype=np.uint8)))

    thread.set_record_enabled(False)

    assert len(thread._frame_buffer) == 1
