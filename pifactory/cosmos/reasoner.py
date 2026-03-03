"""Cosmos Reason 2 NIM API client for Pi-Factory.

Merges client + models into a single module. Uses httpx.AsyncClient for
non-blocking calls. Gracefully falls back to stub responses when no API key.
Parses <think> blocks from Cosmos R2 reasoning output.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime
import json
import logging
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class CosmosInsight:
    """Result of a Cosmos Reason 2 analysis."""
    incident_id: str
    node_id: str
    timestamp: datetime.datetime
    summary: str = ""
    root_cause: str = ""
    confidence: float = 0.0
    reasoning: str = ""
    thinking: str = ""
    suggested_checks: list[str] = dataclasses.field(default_factory=list)
    video_url: str = ""
    cosmos_model: str = "nvidia/cosmos-reason2-8b"


def parse_think_blocks(text: str) -> tuple[str, str]:
    """Extract <think>...</think> reasoning from model output.

    Returns (thinking, answer) where thinking is the content inside <think>
    tags and answer is everything else.
    """
    pattern = re.compile(r"<think>(.*?)</think>", re.DOTALL)
    matches = pattern.findall(text)
    thinking = "\n".join(m.strip() for m in matches)
    answer = pattern.sub("", text).strip()
    return thinking, answer


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class CosmosReasoner:
    """Async HTTP client for NVIDIA Cosmos Reason 2 NIM API."""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/cosmos-reason2-8b",
        fallback_model: str = "meta/llama-3.1-70b-instruct",
        temperature: float = 0.6,
        top_p: float = 0.95,
        max_tokens: int = 4096,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.fallback_model = fallback_model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self._use_fallback = False

    @property
    def is_available(self) -> bool:
        return bool(self.api_key)

    @property
    def active_model(self) -> str:
        return self.fallback_model if self._use_fallback else self.model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(
        self,
        incident_id: str,
        node_id: str,
        tags: dict,
        video_url: str = "",
        context: str = "",
    ) -> CosmosInsight:
        """Analyze an industrial fault. Uses NIM API if key is set, else stub."""
        if self.api_key:
            return await self._analyze_real(incident_id, node_id, tags, video_url, context)
        logger.info("CosmosReasoner: no API key — returning stub for %s", incident_id)
        return self._stub(incident_id, node_id, tags, video_url)

    async def diagnose_belt_video(
        self,
        clip_bytes: bytes,
        tags: dict,
        tachometer: dict,
    ) -> dict:
        """Diagnose belt issues using a video clip + PLC tags via Cosmos R2.

        Args:
            clip_bytes: Raw mp4 bytes from BeltTachometer.get_clip_buffer()
            tags: Current PLC tag snapshot dict
            tachometer: {rpm, belt_speed_pct, tracking_offset_px, status}

        Returns:
            {reasoning, diagnosis, root_cause, visual_confirmation,
             action, confidence, latency_ms}
        """
        from pifactory.cosmos.prompts import build_belt_vision_prompt

        t0 = time.monotonic()

        if not self.api_key:
            logger.info("CosmosReasoner: no API key — returning belt stub")
            return self._belt_stub(tachometer, t0)

        prompt = build_belt_vision_prompt(
            tags=tags,
            rpm=tachometer.get("rpm", 0.0),
            speed_pct=tachometer.get("belt_speed_pct", 100.0),
            offset_px=tachometer.get("tracking_offset_px", 0),
            vision_status=tachometer.get("status", "NORMAL"),
        )

        b64_video = base64.b64encode(clip_bytes).decode("utf-8")
        video_url = f"data:video/mp4;base64,{b64_video}"

        content: list[dict] = [
            {"type": "text", "text": prompt},
            {"type": "video_url", "video_url": {"url": video_url}},
        ]

        model = self.active_model
        try:
            async with httpx.AsyncClient(timeout=90.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": content}],
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "max_tokens": self.max_tokens,
                        "extra_body": {
                            "media_io_kwargs": {"video": {"fps": 3.0}},
                        },
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw = data["choices"][0]["message"]["content"]
            thinking, answer = parse_think_blocks(raw)

            # Parse <answer> block
            parsed = self._parse_belt_answer(answer)
            latency_ms = int((time.monotonic() - t0) * 1000)

            return {
                "reasoning": thinking,
                "diagnosis": parsed.get("diagnosis", answer[:200]),
                "root_cause": parsed.get("root_cause", "See full response"),
                "visual_confirmation": parsed.get("visual_confirmation", ""),
                "action": parsed.get("action", ""),
                "confidence": float(parsed.get("confidence", 0.5)),
                "latency_ms": latency_ms,
            }

        except Exception:
            logger.exception("Belt video diagnosis failed — falling back to stub")
            return self._belt_stub(tachometer, t0)

    # ------------------------------------------------------------------
    # Real API call
    # ------------------------------------------------------------------

    async def _analyze_real(
        self,
        incident_id: str,
        node_id: str,
        tags: dict,
        video_url: str,
        context: str,
    ) -> CosmosInsight:
        model = self.active_model
        logger.info("CosmosReasoner: calling %s for %s", model, incident_id)

        tag_json = json.dumps(tags, indent=2)
        prompt = (
            "Analyze this industrial equipment fault. Provide a diagnosis.\n\n"
            f"Equipment Node: {node_id}\n"
            f"Incident ID: {incident_id}\n\n"
            f"Current Tag Values:\n{tag_json}\n\n"
            f"Additional Context: {context or 'None provided'}\n\n"
            "Respond using the following format:\n"
            "<think>Your step-by-step reasoning about the fault, cross-referencing "
            "tag values with known failure modes.</think>\n\n"
            "Then provide:\n"
            "1. A brief summary of the fault\n"
            "2. The most likely root cause\n"
            "3. Your confidence level (0-1)\n"
            "4. Suggested checks/fixes (as a list)\n\n"
            "Format your final answer as JSON with keys: summary, root_cause, "
            "confidence, suggested_checks"
        )

        content: list[dict] = [{"type": "text", "text": prompt}]
        if video_url:
            content.append({"type": "video_url", "video_url": {"url": video_url}})

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": content}],
                        "temperature": self.temperature,
                        "top_p": self.top_p,
                        "max_tokens": self.max_tokens,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            raw = data["choices"][0]["message"]["content"]
            thinking, answer = parse_think_blocks(raw)

            # Parse JSON from answer
            parsed = self._extract_json(answer)

            return CosmosInsight(
                incident_id=incident_id,
                node_id=node_id,
                timestamp=datetime.datetime.now(tz=datetime.timezone.utc),
                summary=parsed.get("summary", answer[:200]),
                root_cause=parsed.get("root_cause", "See full response"),
                confidence=float(parsed.get("confidence", 0.5)),
                reasoning=answer,
                thinking=thinking,
                suggested_checks=parsed.get("suggested_checks", []),
                video_url=video_url,
                cosmos_model=model,
            )

        except httpx.HTTPStatusError as e:
            logger.error("NIM API HTTP %s: %s", e.response.status_code, e.response.text[:200])
            if e.response.status_code == 404 and not self._use_fallback:
                logger.info("Switching to fallback model: %s", self.fallback_model)
                self._use_fallback = True
                return await self._analyze_real(incident_id, node_id, tags, video_url, context)
            return self._stub(incident_id, node_id, tags, video_url)
        except Exception:
            logger.exception("NIM API error")
            return self._stub(incident_id, node_id, tags, video_url)

    # ------------------------------------------------------------------
    # JSON extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Try to pull a JSON object from model output."""
        # Strip markdown code fences
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------------
    # Stub responses (no API key or fallback)
    # ------------------------------------------------------------------

    def _stub(
        self,
        incident_id: str,
        node_id: str,
        tags: dict,
        video_url: str,
    ) -> CosmosInsight:
        fault_type = tags.get("error_code", 0)
        if fault_type == 0 and tags.get("e_stop"):
            fault_type = -1

        stubs = {
            -1: {
                "summary": "Emergency stop activated. All motion halted.",
                "root_cause": "Operator or safety system triggered e-stop",
                "confidence": 0.95,
                "thinking": (
                    "E-stop signal is active. Checking motor state: stopped. "
                    "Conveyor: stopped. This is consistent with a deliberate e-stop activation. "
                    "No overcurrent or overtemperature preceding the event."
                ),
                "reasoning": "E-stop active — all motors de-energized. Manual or automated safety response.",
                "checks": [
                    "Identify who pressed the e-stop and why",
                    "Inspect work area for safety hazards",
                    "Check for jammed material or mechanical failure",
                    "Reset e-stop, verify safe conditions, restart in sequence",
                ],
            },
            0: {
                "summary": "No active fault. System operating within normal parameters.",
                "root_cause": "N/A — no fault present",
                "confidence": 0.95,
                "thinking": "All tag values within expected ranges. Motor current nominal, temperature stable, pressure adequate.",
                "reasoning": "All parameters nominal.",
                "checks": ["Continue normal monitoring"],
            },
            1: {
                "summary": "Motor overload detected. Current draw exceeds rated capacity.",
                "root_cause": "Mechanical binding or excessive load on motor shaft",
                "confidence": 0.82,
                "thinking": (
                    f"Motor current at {tags.get('motor_current', 'N/A')}A exceeds "
                    f"expected range for speed {tags.get('motor_speed', 'N/A')}%. "
                    "Pattern consistent with mechanical resistance — jammed workpiece or bearing degradation."
                ),
                "reasoning": "Overcurrent indicates mechanical loading beyond motor rating.",
                "checks": [
                    "Inspect motor shaft for mechanical binding",
                    "Check conveyor belt alignment and tension",
                    "Verify motor bearings with vibration analysis",
                    "Review motor nameplate amps vs measured current",
                ],
            },
            2: {
                "summary": "High temperature alarm. Exceeding safe threshold.",
                "root_cause": "Insufficient cooling or sustained high-load operation",
                "confidence": 0.78,
                "thinking": (
                    f"Temperature at {tags.get('temperature', 'N/A')}°C. "
                    "Thermal runaway pattern suggests cooling system degradation."
                ),
                "reasoning": "Temperature exceeds safe operating range.",
                "checks": [
                    "Check cooling fan operation",
                    "Inspect air filters for blockage",
                    "Verify ambient temperature in enclosure",
                    "Check thermal paste on heat sinks",
                ],
            },
            3: {
                "summary": "Conveyor jam detected. Material flow interrupted.",
                "root_cause": "Physical obstruction in conveyor path",
                "confidence": 0.88,
                "thinking": (
                    "Both photoeye sensors showing sustained blockage. Belt speed dropped to "
                    "zero while motor remains energized — classic jam signature. Motor current "
                    "elevated from stall torque."
                ),
                "reasoning": "Sensor blockage + zero belt speed + elevated current = conveyor jam.",
                "checks": [
                    "Clear jammed material from conveyor path",
                    "Inspect photoeye sensors for alignment",
                    "Check conveyor belt tracking",
                    "Verify guide rail spacing",
                ],
            },
            4: {
                "summary": "Sensor failure detected. Photoeye not responding.",
                "root_cause": "Sensor wiring fault or component failure",
                "confidence": 0.72,
                "thinking": "Sensor readings inconsistent with physical process state. Likely wiring issue or end-of-life sensor.",
                "reasoning": "Flat-line or erratic sensor values.",
                "checks": [
                    "Check sensor wiring connections",
                    "Verify sensor supply voltage",
                    "Test sensor with known target",
                    "Replace sensor if beyond calibration",
                ],
            },
            5: {
                "summary": "Communication loss with downstream device.",
                "root_cause": "Network or fieldbus interruption",
                "confidence": 0.75,
                "thinking": "Communication timeout detected. Cable fault, switch failure, or device power loss.",
                "reasoning": "Fieldbus communication timeout.",
                "checks": [
                    "Check Ethernet cable connections",
                    "Verify network switch status",
                    "Ping downstream device",
                    "Check device power supply",
                ],
            },
        }

        resp = stubs.get(fault_type, stubs[0])

        return CosmosInsight(
            incident_id=incident_id,
            node_id=node_id,
            timestamp=datetime.datetime.now(tz=datetime.timezone.utc),
            summary=resp["summary"],
            root_cause=resp["root_cause"],
            confidence=resp["confidence"],
            reasoning=resp["reasoning"],
            thinking=resp["thinking"],
            suggested_checks=resp["checks"],
            video_url=video_url,
            cosmos_model=self.model + " (stub)",
        )

    def _belt_stub(self, tachometer: dict, t0: float) -> dict:
        """Return a stub belt diagnosis based on tachometer status."""
        status = tachometer.get("status", "NORMAL")
        stubs = {
            "NORMAL": {
                "diagnosis": "Belt running within normal parameters.",
                "root_cause": "N/A — no fault present",
                "visual_confirmation": "Orange tape crossing centerline at steady interval.",
                "action": "Continue normal monitoring.",
                "confidence": 0.95,
            },
            "SLOW": {
                "diagnosis": "Belt speed degraded below 80% of baseline.",
                "root_cause": "Possible VFD frequency drop, belt slip, or increased load",
                "visual_confirmation": "Orange tape crossings slower than baseline interval.",
                "action": "Check VFD output frequency, belt tension, and load.",
                "confidence": 0.75,
            },
            "MISTRACK": {
                "diagnosis": "Belt tracking misaligned — tape drifting from center.",
                "root_cause": "Belt tension imbalance or roller misalignment",
                "visual_confirmation": "Orange tape centroid offset >50px from calibrated center.",
                "action": "Inspect belt tension and roller alignment. Adjust tracking.",
                "confidence": 0.70,
            },
            "STOPPED": {
                "diagnosis": "Belt stopped — no tape crossing detected for >3 seconds.",
                "root_cause": "Motor de-energized, VFD fault, or mechanical jam",
                "visual_confirmation": "No motion detected in video. Orange tape stationary.",
                "action": "Check motor contactor, VFD status, and E-stop circuit.",
                "confidence": 0.90,
            },
        }
        resp = stubs.get(status, stubs["NORMAL"])
        latency_ms = int((time.monotonic() - t0) * 1000)
        return {
            "reasoning": f"Stub diagnosis based on tachometer status: {status}",
            "diagnosis": resp["diagnosis"],
            "root_cause": resp["root_cause"],
            "visual_confirmation": resp["visual_confirmation"],
            "action": resp["action"],
            "confidence": resp["confidence"],
            "latency_ms": latency_ms,
        }

    @staticmethod
    def _parse_belt_answer(text: str) -> dict:
        """Parse the <answer> block from belt diagnosis output."""
        answer_match = re.search(r"<answer>(.*?)</answer>", text, re.DOTALL)
        block = answer_match.group(1) if answer_match else text

        result: dict = {}
        for line in block.strip().splitlines():
            line = line.strip()
            if ":" in line:
                key, _, value = line.partition(":")
                key = key.strip().lower().replace(" ", "_")
                result[key] = value.strip()
        return result
