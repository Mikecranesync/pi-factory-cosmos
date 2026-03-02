"""Pi-Factory Tag Server — FastAPI backend serving PLC tags, faults, and Cosmos AI.

Endpoints:
  GET  /api/tags      — latest tag snapshot
  GET  /api/faults    — detected faults from current tags
  POST /api/diagnose  — AI-powered diagnosis (Cosmos R2 or stub)
  GET  /api/combined  — single call: tags + faults + last diagnosis
  GET  /api/health    — service health
  GET  /docs          — auto-generated OpenAPI docs
  GET  /              — demo dashboard (fallback HMI)

Hardware switch (ANYBUS_HARDWARE env var):
  false (default) → PLCSimulator (in-memory fake tags)
  true            → hms.abcc40 AnybusDriver (real fieldbus hardware)
"""

from __future__ import annotations

import datetime
import logging
import time
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
        version="1.0.0",
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
        "last_insight": None,
        "start_time": time.monotonic(),
        "cycler": _cycler,
        "sim": _sim,
    }

    # ------------------------------------------------------------------
    # Endpoints
    # ------------------------------------------------------------------

    @app.get("/api/tags")
    async def get_tags():
        """Return latest tag snapshot."""
        snap = tag_source()
        _state["last_tags"] = snap.to_dict() if isinstance(snap, TagSnapshot) else snap
        return _state["last_tags"]

    @app.get("/api/faults")
    async def get_faults():
        """Detect faults from current tags."""
        tags = _state.get("last_tags") or (tag_source()).to_dict()
        _state["last_tags"] = tags if isinstance(tags, dict) else tags.to_dict()
        faults = detect_faults(_state["last_tags"])
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
        """Single call: tags + faults + last diagnosis."""
        tags = _state.get("last_tags") or (tag_source()).to_dict()
        _state["last_tags"] = tags if isinstance(tags, dict) else tags
        faults = detect_faults(tags)
        insight = _state.get("last_insight")

        return {
            "tags": tags,
            "faults": [
                {"code": f.fault_code, "severity": f.severity.value, "title": f.title}
                for f in faults
            ],
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
