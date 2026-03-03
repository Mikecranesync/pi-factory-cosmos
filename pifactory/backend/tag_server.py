"""Pi-Factory Tag Server — FastAPI backend serving PLC tags, faults, and Cosmos AI.

Endpoints:
  GET  /api/tags       — latest tag snapshot (PLC + VFD merged)
  GET  /api/faults     — detected faults from current tags
  POST /api/diagnose   — AI-powered diagnosis (Cosmos R2 or stub)
  GET  /api/combined   — single call: tags + faults + conflicts + last diagnosis
  GET  /api/health     — service health
  GET  /api/vfd/status — VFD-only live tags
  GET  /api/conflicts  — VFD cross-reference conflict checks
  GET  /docs           — auto-generated OpenAPI docs
  GET  /               — demo dashboard (fallback HMI)

Hardware switch (ANYBUS_HARDWARE env var):
  false (default) → PLCSimulator (in-memory fake tags)
  true            → hms.abcc40 AnybusDriver (real fieldbus hardware)
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any

import asyncio

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

from pifactory.backend.config import Config
from pifactory.simulator.plc_sim import PLCSimulator, TagSnapshot, DemoCycler
from pifactory.simulator.fault_classifier import detect_faults, FaultSeverity
from pifactory.cosmos.reasoner import CosmosReasoner, CosmosInsight
from pifactory.cosmos.prompts import build_diagnosis_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class DiagnoseRequest(BaseModel):
    question: str = "Why is this equipment stopped?"


class DiagnoseResponse(BaseModel):
    question: str
    answer: str
    thinking: str = ""
    faults_detected: list[str]
    model: str
    confidence: float = 0.0
    latency_ms: int
    timestamp: str


class HealthResponse(BaseModel):
    status: str
    service: str
    hardware_mode: bool
    nim_available: bool
    uptime_seconds: int


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app(
    config: Config | None = None,
    sim: PLCSimulator | None = None,
    cycler: DemoCycler | None = None,
    tachometer: Any | None = None,
    vfd_reader: Any | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    cfg = config or Config.from_env()
    _sim = sim or PLCSimulator()
    _cycler = cycler or DemoCycler(_sim)

    # Tag source: hardware or simulator
    tag_source = _resolve_tag_source(cfg, _sim)

    reasoner = CosmosReasoner(
        api_key=cfg.nvidia_api_key,
        base_url=cfg.cosmos_base_url,
        model=cfg.cosmos_model,
        fallback_model=cfg.cosmos_fallback,
        temperature=cfg.cosmos_temperature,
        top_p=cfg.cosmos_top_p,
        max_tokens=cfg.cosmos_max_tokens,
    )

    app = FastAPI(
        title="Pi-Factory",
        version="2.0.0",
        description="Industrial tag server with Cosmos R2 AI diagnosis",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Shared state
    _state: dict[str, Any] = {
        "last_tags": {},
        "last_vfd_tags": {},
        "last_insight": None,
        "start_time": time.monotonic(),
        "cycler": _cycler,
        "sim": _sim,
        "tachometer": tachometer,
        "vfd_reader": vfd_reader,
    }

    # Background VFD polling
    @app.on_event("startup")
    async def start_vfd_polling():
        vfd = _state.get("vfd_reader")
        if vfd is None:
            return
        logger.info("Starting VFD polling (%.1fs interval)", cfg.vfd_poll_interval_sec)

        async def poll_loop():
            while True:
                try:
                    _state["last_vfd_tags"] = await vfd.read_all_tags()
                except Exception:
                    logger.exception("VFD poll error")
                await asyncio.sleep(cfg.vfd_poll_interval_sec)

        asyncio.create_task(poll_loop())

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @app.get("/api/tags")
    async def get_tags():
        """Return latest tag snapshot (PLC + VFD merged)."""
        snap = tag_source()
        _state["last_tags"] = snap.to_dict() if isinstance(snap, TagSnapshot) else snap
        result = dict(_state["last_tags"])
        vfd = _state.get("last_vfd_tags")
        if vfd:
            result.update(vfd)
        return result

    @app.get("/api/faults")
    async def get_faults():
        """Detect faults from current tags (PLC + VFD + belt merged)."""
        tags = _state.get("last_tags") or (tag_source()).to_dict()
        _state["last_tags"] = tags if isinstance(tags, dict) else tags.to_dict()
        merged = dict(_state["last_tags"])
        vfd = _state.get("last_vfd_tags")
        if vfd:
            merged.update(vfd)
        # Inject belt tags for cross-reference
        tach = _state.get("tachometer")
        if tach is not None:
            reading = tach._last_reading
            merged["belt_rpm"] = reading.get("rpm", 0.0)
            merged["belt_vision_status"] = reading.get("status", "")
        faults = detect_faults(merged)
        return {
            "faults": [
                {
                    "code": f.fault_code,
                    "severity": f.severity.value,
                    "title": f.title,
                    "description": f.description,
                    "causes": f.likely_causes,
                    "checks": f.suggested_checks,
                }
                for f in faults
            ],
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

    @app.post("/api/diagnose", response_model=DiagnoseResponse)
    async def diagnose(req: DiagnoseRequest):
        """AI-powered fault diagnosis via Cosmos R2."""
        t0 = time.time()

        tags = _state.get("last_tags") or {}
        if not tags:
            snap = tag_source()
            tags = snap.to_dict() if isinstance(snap, TagSnapshot) else snap
            _state["last_tags"] = tags

        faults = detect_faults(tags)
        node_id = tags.get("node_id", "pi-factory")

        try:
            insight = await reasoner.analyze(
                incident_id=f"DIAG-{int(time.time())}",
                node_id=node_id,
                tags=tags,
                context=f"Technician question: {req.question}",
            )
            _state["last_insight"] = insight

            answer = f"{insight.summary}\n\nRoot Cause: {insight.root_cause}"
            if insight.suggested_checks:
                answer += "\n\nSuggested Checks:\n"
                for c in insight.suggested_checks[:5]:
                    answer += f"  - {c}\n"

            return DiagnoseResponse(
                question=req.question,
                answer=answer,
                thinking=insight.thinking,
                faults_detected=[f.fault_code for f in faults if f.severity != FaultSeverity.INFO],
                model=insight.cosmos_model,
                confidence=insight.confidence,
                latency_ms=int((time.time() - t0) * 1000),
                timestamp=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            )
        except Exception as e:
            logger.exception("Diagnosis error")
            from pifactory.simulator.fault_classifier import format_diagnosis_for_technician
            fallback = "\n\n".join(format_diagnosis_for_technician(f) for f in faults)
            return DiagnoseResponse(
                question=req.question,
                answer=f"AI unavailable. Rule-based:\n\n{fallback}",
                faults_detected=[f.fault_code for f in faults if f.severity != FaultSeverity.INFO],
                model="rule-based",
                latency_ms=int((time.time() - t0) * 1000),
                timestamp=datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            )

    @app.get("/api/combined")
    async def combined():
        """Single call: tags + VFD + faults + conflicts + last diagnosis."""
        tags = _state.get("last_tags") or (tag_source()).to_dict()
        _state["last_tags"] = tags if isinstance(tags, dict) else tags
        vfd_tags = _state.get("last_vfd_tags", {})

        # Merge all for fault detection
        merged = dict(tags)
        if vfd_tags:
            merged.update(vfd_tags)
        tach = _state.get("tachometer")
        if tach is not None:
            reading = tach._last_reading
            merged["belt_rpm"] = reading.get("rpm", 0.0)
            merged["belt_vision_status"] = reading.get("status", "")

        faults = detect_faults(merged)
        conflicts = [
            {"code": f.fault_code, "severity": f.severity.value, "title": f.title,
             "description": f.description}
            for f in faults if f.fault_code.startswith("V")
        ]
        insight = _state.get("last_insight")

        return {
            "tags": tags,
            "vfd_tags": vfd_tags,
            "faults": [
                {"code": f.fault_code, "severity": f.severity.value, "title": f.title}
                for f in faults
            ],
            "conflicts": conflicts,
            "last_diagnosis": {
                "summary": insight.summary if insight else None,
                "thinking": insight.thinking if insight else None,
                "confidence": insight.confidence if insight else None,
                "model": insight.cosmos_model if insight else None,
            },
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

    @app.get("/api/health", response_model=HealthResponse)
    async def health():
        return HealthResponse(
            status="ok",
            service="pi-factory",
            hardware_mode=cfg.anybus_hardware,
            nim_available=reasoner.is_available,
            uptime_seconds=int(time.monotonic() - _state["start_time"]),
        )

    @app.get("/", response_class=HTMLResponse)
    async def dashboard():
        """Serve the demo fallback dashboard."""
        from pifactory.hmi.dashboard import render_dashboard
        return render_dashboard()

    # ------------------------------------------------------------------
    # Camera endpoints
    # ------------------------------------------------------------------

    @app.get("/api/camera/frame")
    async def camera_frame():
        """Return a single JPEG snapshot from the configured video source."""
        from pifactory.cosmos.frame_capture import capture_frame

        if not cfg.video_source:
            return Response(content=b"No video source configured", status_code=503)
        jpeg = capture_frame(cfg.video_source)
        if jpeg is None:
            return Response(content=b"Failed to capture frame", status_code=503)
        return Response(content=jpeg, media_type="image/jpeg")

    @app.get("/api/camera/stream")
    async def camera_stream():
        """MJPEG streaming endpoint — multipart boundary push at ~10 fps."""
        from pifactory.cosmos.frame_capture import capture_stream

        if not cfg.video_source:
            return Response(content=b"No video source configured", status_code=503)

        async def mjpeg_generator():
            for frame in capture_stream(cfg.video_source, fps=10):
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
                )
                await asyncio.sleep(0)  # yield control to event loop

        return StreamingResponse(
            mjpeg_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    @app.get("/camera", response_class=HTMLResponse)
    async def camera_page():
        """Serve the live webcam page."""
        from pifactory.hmi.camera_page import render_camera_page
        return render_camera_page()

    # ------------------------------------------------------------------
    # Belt tachometer endpoints
    # ------------------------------------------------------------------

    @app.get("/api/belt/status")
    async def belt_status():
        """Return latest belt tachometer reading (no Cosmos call)."""
        tach = _state.get("tachometer")
        if tach is None:
            return Response(content=b"No belt tachometer configured", status_code=503)

        reading = tach._last_reading
        result = {
            "rpm": reading.get("rpm", 0.0),
            "speed_pct": reading.get("belt_speed_pct", 0.0),
            "offset_px": reading.get("tracking_offset_px", 0),
            "status": reading.get("status", "STOPPED"),
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

        # Include annotated frame as base64 if available
        frame = reading.get("annotated_frame")
        if frame is not None:
            try:
                import cv2
                _, buf = cv2.imencode(".jpg", frame)
                import base64
                result["annotated_frame_b64"] = base64.b64encode(buf.tobytes()).decode()
            except Exception:
                pass

        return result

    @app.post("/api/belt/diagnose")
    async def belt_diagnose():
        """Trigger Cosmos R2 video diagnosis of the belt."""
        tach = _state.get("tachometer")
        if tach is None:
            return Response(content=b"No belt tachometer configured", status_code=503)

        reading = tach._last_reading

        # If belt is normal, skip the expensive Cosmos call
        if reading.get("status") == "NORMAL":
            return {
                "tachometer": {
                    "rpm": reading.get("rpm", 0.0),
                    "speed_pct": reading.get("belt_speed_pct", 0.0),
                    "offset_px": reading.get("tracking_offset_px", 0),
                    "status": "NORMAL",
                },
                "cosmos": None,
                "tags": _state.get("last_tags", {}),
                "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            }

        # Get clip and run diagnosis
        clip = tach.get_clip_buffer()
        tags = _state.get("last_tags") or {}
        if not tags:
            snap = tag_source()
            tags = snap.to_dict() if isinstance(snap, TagSnapshot) else snap
            _state["last_tags"] = tags

        tach_dict = {
            "rpm": reading.get("rpm", 0.0),
            "belt_speed_pct": reading.get("belt_speed_pct", 0.0),
            "tracking_offset_px": reading.get("tracking_offset_px", 0),
            "status": reading.get("status", "STOPPED"),
        }

        cosmos_result = await reasoner.diagnose_belt_video(clip, tags, tach_dict)

        return {
            "tachometer": tach_dict,
            "cosmos": cosmos_result,
            "tags": tags,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

    @app.get("/api/belt/stream")
    async def belt_stream():
        """MJPEG stream of annotated belt frames with tachometer overlay."""
        tach = _state.get("tachometer")
        if tach is None:
            return Response(content=b"No belt tachometer configured", status_code=503)

        if not cfg.video_source:
            return Response(content=b"No video source configured", status_code=503)

        from pifactory.cosmos.frame_capture import capture_stream

        async def mjpeg_generator():
            try:
                import cv2
                import numpy as np
            except ImportError:
                return

            for jpeg in capture_stream(cfg.video_source, fps=10):
                frame = cv2.imdecode(
                    np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR
                )
                if frame is not None:
                    reading = tach.process_frame(frame)
                    annotated = reading.get("annotated_frame")
                    if annotated is not None:
                        _, buf = cv2.imencode(".jpg", annotated)
                        jpeg = buf.tobytes()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
                )
                await asyncio.sleep(0)

        return StreamingResponse(
            mjpeg_generator(),
            media_type="multipart/x-mixed-replace; boundary=frame",
        )

    # ------------------------------------------------------------------
    # VFD endpoints
    # ------------------------------------------------------------------

    @app.get("/api/vfd/status")
    async def vfd_status():
        """Return VFD-only live tags."""
        vfd = _state.get("vfd_reader")
        if vfd is None:
            return Response(content=b"No VFD configured - set VFD_HOST", status_code=503)
        tags = _state.get("last_vfd_tags", {})
        if not tags:
            tags = await vfd.read_all_tags()
            _state["last_vfd_tags"] = tags
        return tags

    @app.get("/api/conflicts")
    async def conflicts():
        """Return VFD cross-reference conflict checks (V001-V006)."""
        tags = _state.get("last_tags") or {}
        vfd_tags = _state.get("last_vfd_tags", {})
        merged = dict(tags)
        if vfd_tags:
            merged.update(vfd_tags)
        tach = _state.get("tachometer")
        if tach is not None:
            reading = tach._last_reading
            merged["belt_rpm"] = reading.get("rpm", 0.0)
            merged["belt_vision_status"] = reading.get("status", "")

        faults = detect_faults(merged)
        vfd_conflicts = [
            {
                "code": f.fault_code,
                "severity": f.severity.value,
                "title": f.title,
                "description": f.description,
                "causes": f.likely_causes,
                "checks": f.suggested_checks,
            }
            for f in faults if f.fault_code.startswith("V")
        ]
        return {
            "conflicts": vfd_conflicts,
            "timestamp": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
        }

    return app


# ---------------------------------------------------------------------------
# Tag source resolution
# ---------------------------------------------------------------------------

def _resolve_tag_source(cfg: Config, sim: PLCSimulator):
    """Return a callable that produces tag snapshots."""
    if cfg.anybus_hardware:
        try:
            from hms.abcc40 import AnybusDriver  # type: ignore[import-not-found]
            driver = AnybusDriver()
            logger.info("Anybus hardware mode: reading real fieldbus tags")
            return driver.read_tags
        except ImportError:
            logger.warning(
                "ANYBUS_HARDWARE=true but hms.abcc40 not installed — falling back to simulator"
            )
    logger.info("Simulation mode: using PLCSimulator")
    return sim.tick
