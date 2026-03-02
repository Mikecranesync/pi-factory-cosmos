"""Pi-Factory Telegram Bot — python-telegram-bot v20+ async handlers.

Commands:
  /status   — current PLC tag summary
  /see      — trigger Cosmos R2 analysis (video + tags)
  /alarms   — list active faults
  /conflicts— show tag conflicts or anomalies
  /help     — command reference

Auto-pushes fault alerts on severity transitions.
Auth filter via ALLOWED_CHAT_IDS env var.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

logger = logging.getLogger(__name__)

# Load alarm descriptions
_ALARMS_PATH = Path(__file__).parent / "alarms.json"
_ALARMS: dict[str, str] = {}
if _ALARMS_PATH.exists():
    _ALARMS = json.loads(_ALARMS_PATH.read_text())

_TAG_MAP_PATH = Path(__file__).parent / "tag_map.json"
_TAG_MAP: dict = {}
if _TAG_MAP_PATH.exists():
    _TAG_MAP = json.loads(_TAG_MAP_PATH.read_text())


class PiFactoryBot:
    """Wraps python-telegram-bot v20+ Application with Pi-Factory commands."""

    def __init__(
        self,
        token: str,
        api_base: str = "http://localhost:8080",
        allowed_chat_ids: list[str] | None = None,
    ) -> None:
        self.token = token
        self.api_base = api_base
        self.allowed_ids = set(allowed_chat_ids or [])
        self._prev_severity: str | None = None

    def _authorized(self, update: Update) -> bool:
        if not self.allowed_ids:
            return True
        chat_id = str(update.effective_chat.id)
        return chat_id in self.allowed_ids

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        await update.message.reply_text(
            "Pi-Factory Bot\n\n"
            "Commands:\n"
            "/status  — PLC tag summary\n"
            "/see     — AI diagnosis (Cosmos R2)\n"
            "/alarms  — active faults\n"
            "/conflicts — tag anomalies\n"
            "/help    — this message"
        )

    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await self.cmd_start(update, ctx)

    async def cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        tags = await self._fetch("/api/tags")
        if not tags or "error" in tags:
            await update.message.reply_text("Could not fetch tags from Pi-Factory.")
            return

        lines = ["PLC Status:\n"]
        for key, meta in _TAG_MAP.items():
            val = tags.get(key)
            if val is None:
                continue
            label = meta.get("label", key)
            unit = meta.get("unit", "")
            if meta.get("type") == "bool":
                display = "ON" if val else "OFF"
            elif meta.get("type") == "float":
                display = f"{float(val):.1f}{unit}"
            else:
                display = f"{val}{unit}"
            lines.append(f"  {label}: {display}")

        ec = tags.get("error_code", 0)
        if ec:
            lines.append(f"\nFault: {_ALARMS.get(str(ec), f'Code {ec}')}")

        await update.message.reply_text("\n".join(lines))

    async def cmd_see(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        await update.message.reply_text("Analyzing with Cosmos R2...")

        data = await self._post("/api/diagnose", {"question": "What is happening right now?"})
        if not data:
            await update.message.reply_text("Diagnosis unavailable.")
            return

        msg = data.get("answer", "No response")
        thinking = data.get("thinking", "")
        model = data.get("model", "unknown")
        latency = data.get("latency_ms", 0)
        conf = data.get("confidence", 0)

        reply = f"{msg}\n\nModel: {model} | {latency}ms | Confidence: {conf:.0%}"
        if thinking:
            reply = f"Reasoning:\n{thinking[:500]}\n\n{reply}"

        await update.message.reply_text(reply[:4000])

    async def cmd_alarms(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        data = await self._fetch("/api/faults")
        if not data:
            await update.message.reply_text("Could not fetch faults.")
            return

        faults = data.get("faults", [])
        active = [f for f in faults if f.get("severity") != "info"]

        if not active:
            await update.message.reply_text("No active alarms. System OK.")
            return

        lines = [f"Active Alarms ({len(active)}):\n"]
        for f in active:
            sev = f.get("severity", "").upper()
            lines.append(f"  [{sev}] {f.get('code')}: {f.get('title')}")
            lines.append(f"    {f.get('description', '')}")
        await update.message.reply_text("\n".join(lines))

    async def cmd_conflicts(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._authorized(update):
            return
        tags = await self._fetch("/api/tags")
        if not tags or "error" in tags:
            await update.message.reply_text("Could not fetch tags.")
            return

        conflicts = []
        if tags.get("motor_running") and tags.get("motor_current", 0) < 0.1:
            conflicts.append("Motor marked RUNNING but current is near zero — check contactor")
        if tags.get("conveyor_running") and tags.get("conveyor_speed", 0) == 0:
            conflicts.append("Conveyor marked RUNNING but speed is 0 — possible jam or VFD fault")
        if not tags.get("e_stop") and not tags.get("motor_running") and tags.get("error_code", 0) == 0:
            conflicts.append("Motor stopped with no E-stop and no error — check start permissive")

        if not conflicts:
            await update.message.reply_text("No conflicts detected. Tags are consistent.")
        else:
            await update.message.reply_text("Tag Conflicts:\n\n" + "\n".join(f"  - {c}" for c in conflicts))

    # ------------------------------------------------------------------
    # Background fault monitor
    # ------------------------------------------------------------------

    async def check_and_push(self, app: Application, chat_id: str) -> None:
        """Called periodically to push alerts on fault transitions."""
        data = await self._fetch("/api/faults")
        if not data:
            return

        faults = data.get("faults", [])
        active = [f for f in faults if f.get("severity") != "info"]
        current = active[0].get("severity") if active else "ok"

        if current != self._prev_severity and current in ("critical", "emergency"):
            msg = f"ALERT: {active[0].get('title', 'Fault detected')}\n{active[0].get('description', '')}"
            try:
                await app.bot.send_message(chat_id=chat_id, text=msg)
            except Exception:
                logger.exception("Failed to push alert")

        self._prev_severity = current

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _fetch(self, path: str) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(f"{self.api_base}{path}")
                r.raise_for_status()
                return r.json()
        except Exception:
            logger.exception("API fetch failed: %s", path)
            return None

    async def _post(self, path: str, body: dict) -> dict | None:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                r = await client.post(f"{self.api_base}{path}", json=body)
                r.raise_for_status()
                return r.json()
        except Exception:
            logger.exception("API post failed: %s", path)
            return None

    # ------------------------------------------------------------------
    # Build application
    # ------------------------------------------------------------------

    def build_app(self) -> Application:
        """Build the python-telegram-bot Application with all handlers."""
        app = Application.builder().token(self.token).build()
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("see", self.cmd_see))
        app.add_handler(CommandHandler("alarms", self.cmd_alarms))
        app.add_handler(CommandHandler("conflicts", self.cmd_conflicts))
        return app
