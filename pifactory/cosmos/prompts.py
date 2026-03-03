"""Industrial prompt templates for Cosmos R2 fault diagnosis.

Combines structured prompt builders with the multimodal YAML-style system prompt.
"""

from __future__ import annotations

from typing import Dict, Any, List

from pifactory.simulator.fault_classifier import FaultDiagnosis, FaultSeverity


SYSTEM_PROMPT = """\
You are FactoryLM Vision, an AI-powered factory diagnostics system.
You analyze live video from factory floor cameras alongside real-time PLC
(Programmable Logic Controller) register data to diagnose equipment issues.

Your job is to:
1. Observe what is happening in the video feed
2. Cross-reference your visual observations with the PLC telemetry data
3. Identify any anomalies, faults, or unsafe conditions
4. Provide a clear diagnosis with evidence from BOTH video and PLC data

When video and PLC data disagree, flag the discrepancy — this often indicates
the root cause (e.g., "solenoid register shows ON but I see no pusher motion"
→ stuck actuator or wiring fault).

Equipment context:
- Allen-Bradley Micro820 PLC
- Conveyor system with motor, sensors, and pneumatics
- Standard industrial safety interlocks

Communication style:
- Direct and professional
- Use bullet points for steps
- Bold safety warnings
- Reference specific tag names and values"""


def _format_tags(tags: Dict[str, Any]) -> str:
    """Format tag dict as human-readable lines."""
    lines = []
    for key, value in sorted(tags.items()):
        if key.startswith("_") or key in ("id", "timestamp", "node_id"):
            continue
        if isinstance(value, bool) or value in (0, 1):
            display = "ON" if value else "OFF"
        elif isinstance(value, float):
            display = f"{value:.2f}"
        else:
            display = str(value)
        lines.append(f"  {key}: {display}")
    return "\n".join(lines)


def _format_faults(faults: List[FaultDiagnosis]) -> str:
    """Format detected faults for prompt inclusion."""
    fault_lines = []
    for f in faults:
        if f.severity == FaultSeverity.INFO:
            continue
        fault_lines.append(f"  [{f.severity.value.upper()}] {f.fault_code}: {f.title}")
        fault_lines.append(f"    {f.description}")
        if f.likely_causes:
            fault_lines.append(f"    Causes: {', '.join(f.likely_causes[:3])}")
    return "\n".join(fault_lines) if fault_lines else "  No active faults detected"


def build_diagnosis_prompt(
    question: str,
    tags: Dict[str, Any],
    faults: List[FaultDiagnosis],
) -> str:
    """Build a structured prompt for fault diagnosis."""
    return f"""{SYSTEM_PROMPT}

CURRENT EQUIPMENT STATE:
{_format_tags(tags)}

DETECTED FAULTS:
{_format_faults(faults)}

TECHNICIAN'S QUESTION:
{question}

INSTRUCTIONS:
1. Answer the technician's question directly and concisely
2. Reference specific tag values when relevant
3. Provide 2-4 actionable troubleshooting steps
4. Use plain language - avoid jargon
5. If safety is a concern, mention it first
6. Keep response under 200 words

Respond using the format:
<think>Your step-by-step reasoning about the fault, cross-referencing
tag values with known failure modes.</think>

Then provide your diagnosis as a clear, actionable summary."""


def build_multimodal_prompt(
    tags: Dict[str, Any],
    faults: List[FaultDiagnosis],
    question: str = "",
) -> str:
    """Build a multimodal prompt for Cosmos R2 (video + PLC tags)."""
    task = question or (
        "Analyze the video feed alongside the PLC data above. "
        "Describe what you observe, identify any issues, and provide your diagnosis."
    )
    return f"""## Live PLC Register Data (Allen-Bradley Micro 820)
{_format_tags(tags)}

## Automated Fault Analysis
{_format_faults(faults)}

## Task
{task}

Answer using the following format:
<think>Your step-by-step reasoning about what you see in the video and what
the PLC registers report. Note any discrepancies between visual observations
and sensor data.</think>

Then provide your diagnosis as a clear, actionable summary a factory
technician could act on."""


def build_status_summary_prompt(tags: Dict[str, Any], faults: List[FaultDiagnosis]) -> str:
    """Prompt for a one-sentence status summary."""
    return build_diagnosis_prompt(
        question="Give me a one-sentence status summary of this equipment.",
        tags=tags,
        faults=faults,
    )


# ---------------------------------------------------------------------------
# Belt vision prompt (Cosmos R2 video diagnosis)
# ---------------------------------------------------------------------------

BELT_VISION_PROMPT = """\
You are FactoryLM Vision analyzing a 5-second video clip of a conveyor belt
alongside real-time PLC telemetry. An orange reference tape is affixed across
the belt width; a vision-based tachometer is tracking it.

## Live PLC Tags
{tags_json}

{vfd_section}## Vision Tachometer Reading
- RPM: {rpm:.1f}
- Belt speed: {speed_pct:.0f}% of baseline
- Tracking offset: {offset_px}px from calibrated center
- Vision status: {vision_status}

## Task
1. Watch the belt motion in the video. Confirm or contradict the tachometer
   reading above.
2. Look for: belt slip, misalignment, material jam, loose tape, abnormal
   vibration, or any visual anomaly.
3. Cross-reference visual observations with the PLC tag values — flag any
   discrepancy (e.g., motor register says ON but belt is not moving).
4. Provide a root cause and recommended action.
5. Cross-reference VFD output frequency with belt RPM — if VFD says
   running but belt is stopped, flag it as belt slip or coupling failure.

Answer using the following format:
<think>Step-by-step reasoning about what you see in the video, what the PLC
data reports, and what the tachometer measured. Note discrepancies.</think>

<answer>
diagnosis: One-sentence diagnosis.
root_cause: Most likely root cause.
visual_confirmation: What you observed in the video that supports your diagnosis.
action: Recommended next step for the technician.
confidence: 0.0-1.0
</answer>"""


def build_belt_vision_prompt(
    tags: Dict[str, Any],
    rpm: float,
    speed_pct: float,
    offset_px: int,
    vision_status: str,
    vfd_tags: Dict[str, Any] = None,
) -> str:
    """Fill the belt vision prompt template with live data."""
    import json
    tags_json = json.dumps(
        {k: v for k, v in tags.items() if not k.startswith("_") and k not in ("id", "timestamp", "node_id")},
        indent=2,
    )
    vfd_section = ""
    if vfd_tags and vfd_tags.get("vfd_comms_ok"):
        vfd_json = json.dumps(
            {k: v for k, v in vfd_tags.items() if k.startswith("vfd_") and k not in ("vfd_comms_error",)},
            indent=2,
        )
        vfd_section = f"## VFD Drive Status\n{vfd_json}\n\n"
    return BELT_VISION_PROMPT.format(
        tags_json=tags_json,
        vfd_section=vfd_section,
        rpm=rpm,
        speed_pct=speed_pct,
        offset_px=offset_px,
        vision_status=vision_status,
    )
