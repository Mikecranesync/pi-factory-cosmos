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
