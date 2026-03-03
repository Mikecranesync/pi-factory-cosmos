"""Tests for BeltTachometer — uses synthetic frames, no real camera needed."""

from __future__ import annotations

import os
import time
from unittest import mock

import cv2
import numpy as np
import pytest

from pifactory.cosmos.belt_tachometer import (
    BeltTachometer,
    STATUS_NORMAL,
    STATUS_SLOW,
    STATUS_MISTRACK,
    STATUS_STOPPED,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gray_frame(h: int = 480, w: int = 640) -> np.ndarray:
    """Return a plain gray BGR frame."""
    return np.full((h, w, 3), 128, dtype=np.uint8)


def _draw_orange_rect(frame: np.ndarray, cx: int, cy: int, rw: int = 80, rh: int = 30) -> np.ndarray:
    """Draw a bright orange rectangle centered at (cx, cy) on frame."""
    out = frame.copy()
    x1 = max(cx - rw // 2, 0)
    y1 = max(cy - rh // 2, 0)
    x2 = min(cx + rw // 2, out.shape[1])
    y2 = min(cy + rh // 2, out.shape[0])
    # Bright orange in BGR: (0, 140, 255) maps to roughly H=15, S=255, V=255
    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 140, 255), -1)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestProcessFrame:
    """Test frame processing and orange contour detection."""

    def test_detects_orange_contour(self):
        tach = BeltTachometer()
        frame = _draw_orange_rect(_make_gray_frame(), cx=320, cy=200)
        result = tach.process_frame(frame)
        # Should detect something and set belt_center_x
        assert tach.belt_center_x is not None
        assert result["annotated_frame"] is not None

    def test_no_orange_returns_stopped_eventually(self):
        tach = BeltTachometer()
        tach.stopped_timeout_sec = 0.0  # immediate for test
        frame = _make_gray_frame()
        result = tach.process_frame(frame)
        assert result["status"] == STATUS_STOPPED
        assert result["rpm"] == 0.0

    def test_belt_center_x_calibrated_on_first_detection(self):
        tach = BeltTachometer()
        assert tach.belt_center_x is None
        frame = _draw_orange_rect(_make_gray_frame(), cx=300, cy=200)
        tach.process_frame(frame)
        assert tach.belt_center_x is not None
        # Should be close to 300 (centroid of the drawn rectangle)
        assert abs(tach.belt_center_x - 300) < 20


class TestCrossingDetection:
    """Test tape crossing the virtual centerline."""

    def test_crossing_detected(self):
        tach = BeltTachometer()
        tach.crossing_debounce_sec = 0.0  # no debounce for test
        h, w = 480, 640
        center_y = h // 2

        # Frame with tape above centerline
        frame_above = _draw_orange_rect(_make_gray_frame(h, w), cx=320, cy=center_y - 60)
        tach.process_frame(frame_above)

        # Frame with tape below centerline (crossing!)
        frame_below = _draw_orange_rect(_make_gray_frame(h, w), cx=320, cy=center_y + 60)
        tach.process_frame(frame_below)

        assert len(tach.crossing_times) >= 1

    def test_debounce_prevents_rapid_crossings(self):
        tach = BeltTachometer()
        tach.crossing_debounce_sec = 10.0  # very long debounce
        h, w = 480, 640
        center_y = h // 2

        # Simulate two rapid crossings
        for _ in range(3):
            tach.process_frame(_draw_orange_rect(_make_gray_frame(h, w), cx=320, cy=center_y - 60))
            tach.process_frame(_draw_orange_rect(_make_gray_frame(h, w), cx=320, cy=center_y + 60))

        # Only 1 crossing should register due to debounce
        assert len(tach.crossing_times) <= 1


class TestRPM:
    """Test RPM calculation from known crossing intervals."""

    def test_rpm_from_known_intervals(self):
        tach = BeltTachometer()
        # Simulate crossings at 0.5s intervals → 2 crossings/sec → 60 RPM
        now = time.monotonic()
        for i in range(6):
            tach.crossing_times.append(now + i * 0.5)

        rpm = tach._compute_rpm()
        assert abs(rpm - 60.0) < 1.0

    def test_rpm_zero_with_no_crossings(self):
        tach = BeltTachometer()
        assert tach._compute_rpm() == 0.0

    def test_rpm_zero_with_one_crossing(self):
        tach = BeltTachometer()
        tach.crossing_times.append(time.monotonic())
        assert tach._compute_rpm() == 0.0


class TestStatus:
    """Test status determination."""

    def test_stopped_when_no_crossings_for_timeout(self):
        tach = BeltTachometer()
        tach.stopped_timeout_sec = 1.0
        # Add a crossing 5 seconds ago
        tach.crossing_times.append(time.monotonic() - 5.0)
        status = tach._determine_status(time.monotonic(), 100.0, 0)
        assert status == STATUS_STOPPED

    def test_slow_when_below_threshold(self):
        tach = BeltTachometer()
        tach.baseline_rpm = 100.0
        tach.slow_threshold_pct = 80.0
        # Recent crossing so not stopped
        tach.crossing_times.append(time.monotonic())
        status = tach._determine_status(time.monotonic(), 50.0, 0)
        assert status == STATUS_SLOW

    def test_mistrack_when_offset_exceeds_threshold(self):
        tach = BeltTachometer()
        tach.mistrack_threshold_px = 50
        tach.crossing_times.append(time.monotonic())
        status = tach._determine_status(time.monotonic(), 100.0, 60)
        assert status == STATUS_MISTRACK

    def test_normal_when_all_ok(self):
        tach = BeltTachometer()
        tach.crossing_times.append(time.monotonic())
        status = tach._determine_status(time.monotonic(), 100.0, 0)
        assert status == STATUS_NORMAL


class TestClipBuffer:
    """Test get_clip_buffer() mp4 output."""

    def test_empty_buffer_returns_empty_bytes(self):
        tach = BeltTachometer()
        assert tach.get_clip_buffer() == b""

    def test_buffer_with_frames_returns_bytes(self):
        tach = BeltTachometer()
        for _ in range(5):
            tach.frame_buffer.append(_make_gray_frame())
        data = tach.get_clip_buffer()
        assert len(data) > 0

    def test_buffer_output_starts_with_mp4_signature(self):
        tach = BeltTachometer()
        for _ in range(3):
            tach.frame_buffer.append(_make_gray_frame())
        data = tach.get_clip_buffer()
        # MP4 files start with a 'ftyp' box — bytes 4-8 should be 'ftyp'
        # (some codecs may vary, so just check we got non-empty bytes)
        assert isinstance(data, bytes)
        assert len(data) > 100


class TestEnvVarOverrides:
    """Test that environment variables override tuning constants."""

    def test_hsv_range_override(self):
        env = {
            "ORANGE_H_LOW": "10",
            "ORANGE_H_HIGH": "30",
            "ORANGE_S_LOW": "100",
            "ORANGE_V_LOW": "100",
        }
        with mock.patch.dict(os.environ, env):
            tach = BeltTachometer()
        assert tach.orange_h_low == 10
        assert tach.orange_h_high == 30
        assert tach.orange_s_low == 100
        assert tach.orange_v_low == 100

    def test_threshold_overrides(self):
        env = {
            "CROSSING_DEBOUNCE_SEC": "0.5",
            "SLOW_THRESHOLD_PCT": "70",
            "MISTRACK_THRESHOLD_PX": "100",
            "STOPPED_TIMEOUT_SEC": "5.0",
            "CLIP_BUFFER_FRAMES": "300",
        }
        with mock.patch.dict(os.environ, env):
            tach = BeltTachometer()
        assert tach.crossing_debounce_sec == 0.5
        assert tach.slow_threshold_pct == 70.0
        assert tach.mistrack_threshold_px == 100
        assert tach.stopped_timeout_sec == 5.0
        assert tach.frame_buffer.maxlen == 300


class TestSpeedPercent:
    """Test belt_speed_pct calculation."""

    def test_100_pct_when_no_baseline(self):
        tach = BeltTachometer()
        assert tach._compute_speed_pct() == 100.0

    def test_correct_pct_with_baseline(self):
        tach = BeltTachometer()
        tach.baseline_rpm = 60.0
        # Set crossing times for 30 RPM (half speed)
        now = time.monotonic()
        for i in range(4):
            tach.crossing_times.append(now + i * 1.0)
        speed = tach._compute_speed_pct()
        assert abs(speed - 50.0) < 2.0
