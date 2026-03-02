"""Frame capture with OpenCV fallback chain: USB cam → RTSP → file → None.

Returns a single JPEG frame as bytes, or None if no source is available.
"""

from __future__ import annotations

import base64
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def capture_frame(source: str = "") -> bytes | None:
    """Capture a single frame from the best available video source.

    Fallback chain:
      1. If source is a digit ("0", "1") → USB camera
      2. If source starts with "rtsp://" → RTSP stream
      3. If source is a file path → read first frame from video file
      4. Empty string → return None (no video)
    """
    if not source:
        return None

    try:
        import cv2
    except ImportError:
        logger.warning("opencv-python-headless not installed — frame capture disabled")
        return None

    cap = None
    try:
        if source.isdigit():
            cap = cv2.VideoCapture(int(source))
        elif source.startswith("rtsp://") or source.startswith("http"):
            cap = cv2.VideoCapture(source)
        elif Path(source).is_file():
            cap = cv2.VideoCapture(str(source))
        else:
            logger.warning("Unknown video source: %s", source)
            return None

        if not cap.isOpened():
            logger.warning("Failed to open video source: %s", source)
            return None

        ret, frame = cap.read()
        if not ret or frame is None:
            logger.warning("Failed to read frame from: %s", source)
            return None

        _, buf = cv2.imencode(".jpg", frame)
        return buf.tobytes()

    except Exception:
        logger.exception("Frame capture error for source: %s", source)
        return None
    finally:
        if cap is not None:
            cap.release()


def frame_to_data_url(frame_bytes: bytes) -> str:
    """Convert JPEG bytes to a data URL for API submission."""
    b64 = base64.b64encode(frame_bytes).decode("utf-8")
    return f"data:image/jpeg;base64,{b64}"
