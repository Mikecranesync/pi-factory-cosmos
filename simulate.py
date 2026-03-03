#!/usr/bin/env python3
"""Pi-Factory Simulator — ONE COMMAND entry point.

Usage:
    python simulate.py                                  # Stub mode, no API key
    python simulate.py --nim-key=nvapi-xxx              # Real Cosmos NIM
    python simulate.py --nim-key=nvapi-xxx --telegram   # With Telegram alerts

Starts:
  1. PLCSimulator + DemoCycler (auto-cycles 60s: normal → warning → fault → recovery)
  2. FastAPI tag server on :8080 (background thread)
  3. Optional Telegram bot (background thread)
  4. Simulation loop: tick every 500ms
"""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
import time

import uvicorn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("simulate")

BANNER = r"""
  ____  _       _____          _
 |  _ \(_)     |  ___|_ _  ___| |_ ___  _ __ _   _
 | |_) | |_____| |_ / _` |/ __| __/ _ \| '__| | | |
 |  __/| |_____|  _| (_| | (__| || (_) | |  | |_| |
 |_|   |_|     |_|  \__,_|\___|\__\___/|_|   \__, |
                                               |___/
  Industrial AI Diagnostics — NVIDIA Cosmos Reason 2
"""


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Pi-Factory Simulator")
    p.add_argument("--nim-key", type=str, default="", help="NVIDIA Cosmos NIM API key")
    p.add_argument("--telegram", action="store_true", help="Enable Telegram bot")
    p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    p.add_argument("--cycle", type=int, default=60, help="Demo cycle seconds (default: 60)")
    p.add_argument("--interval", type=int, default=500, help="Tick interval ms (default: 500)")
    return p.parse_args()


def start_server(app, port: int) -> threading.Thread:
    """Start the FastAPI server in a daemon thread."""
    def run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    t = threading.Thread(target=run, daemon=True, name="uvicorn")
    t.start()
    return t


def start_telegram(api_base: str) -> threading.Thread | None:
    """Start the Telegram bot in a daemon thread."""
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token:
        logger.warning("TELEGRAM_BOT_TOKEN not set — Telegram disabled")
        return None

    from pifactory.telegram.bot import PiFactoryBot
    from pifactory.backend.config import Config

    cfg = Config.from_env()

    def run():
        bot = PiFactoryBot(
            token=token,
            api_base=api_base,
            allowed_chat_ids=cfg.allowed_chat_ids,
        )
        tg_app = bot.build_app()

        if chat_id:
            async def fault_check(context):
                await bot.check_and_push(tg_app, chat_id)

            tg_app.job_queue.run_repeating(fault_check, interval=10, first=15)

        logger.info("Telegram bot started")
        tg_app.run_polling(drop_pending_updates=True)

    t = threading.Thread(target=run, daemon=True, name="telegram")
    t.start()
    return t


def main() -> None:
    args = parse_args()

    # Set env vars from CLI args
    if args.nim_key:
        os.environ["NVIDIA_COSMOS_API_KEY"] = args.nim_key
    os.environ["PORT"] = str(args.port)

    # Create config early so banner can show VFD status
    from pifactory.backend.config import Config
    cfg = Config.from_env()

    print(BANNER)

    nim_status = "REAL NIM" if args.nim_key else "STUB (no API key)"
    tg_status = "ENABLED" if args.telegram else "DISABLED"
    vfd_status = f"ENABLED ({cfg.vfd_host}:{cfg.vfd_port})" if cfg.has_vfd else "DISABLED (set VFD_HOST)"

    print(f"  Mode:      Simulation (PLCSimulator + DemoCycler)")
    print(f"  Cosmos:    {nim_status}")
    print(f"  Telegram:  {tg_status}")
    print(f"  VFD:       {vfd_status}")
    print(f"  Cycle:     {args.cycle}s (normal → warning → fault → recovery)")
    print(f"  Dashboard: http://localhost:{args.port}")
    print(f"  API Docs:  http://localhost:{args.port}/docs")
    print(f"  Health:    http://localhost:{args.port}/api/health")
    print()

    # Create shared simulator + cycler FIRST
    from pifactory.simulator.plc_sim import PLCSimulator, DemoCycler
    from pifactory.backend.tag_server import create_app
    sim = PLCSimulator()
    cycler = DemoCycler(sim, cycle_seconds=args.cycle)

    # Belt tachometer (if camera available)
    tachometer = None
    if cfg.video_source:
        from pifactory.cosmos.belt_tachometer import BeltTachometer
        tachometer = BeltTachometer()
        logger.info("Belt tachometer enabled (camera: %s)", cfg.video_source)

    # VFD reader (if VFD_HOST is set)
    vfd_reader = None
    if cfg.has_vfd:
        from pifactory.hardware.vfd_reader import VFDReader
        vfd_reader = VFDReader(
            host=cfg.vfd_host,
            port=cfg.vfd_port,
            slave_id=cfg.vfd_slave_id,
            register_map_path=cfg.vfd_register_map,
            brand=cfg.vfd_brand,
        )
        logger.info("VFD reader enabled (%s:%d)", cfg.vfd_host, cfg.vfd_port)

    # Create FastAPI app with the SAME sim instance
    app = create_app(config=cfg, sim=sim, cycler=cycler, tachometer=tachometer, vfd_reader=vfd_reader)

    # Start server in background thread
    logger.info("Starting tag server on :%d", args.port)
    start_server(app, args.port)

    # Wait for server to be ready
    time.sleep(1.5)

    # Start Telegram bot if requested
    if args.telegram:
        start_telegram(f"http://localhost:{args.port}")

    logger.info("Simulation started — Ctrl+C to stop")

    # Graceful shutdown
    stop = threading.Event()

    def handle_signal(sig, frame):
        logger.info("Shutting down...")
        stop.set()

    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    # Simulation loop — drive the cycler which mutates the shared sim.
    # The tag_server's GET /api/tags calls sim.tick() on the same instance,
    # so dashboard always sees the latest state including phase transitions.
    tick_count = 0

    belt_status = None

    while not stop.is_set():
        snap = cycler.tick(interval_ms=args.interval)
        tick_count += 1

        # Process camera frame through belt tachometer
        if tachometer and cfg.video_source:
            from pifactory.cosmos.frame_capture import capture_frame
            try:
                import cv2
                import numpy as np
            except ImportError:
                cv2 = None  # type: ignore[assignment]
                np = None  # type: ignore[assignment]

            if cv2 is not None:
                jpeg = capture_frame(cfg.video_source)
                if jpeg:
                    frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
                    if frame is not None:
                        belt_status = tachometer.process_frame(frame)

        if tick_count % 20 == 0:  # Every 10 seconds at 500ms interval
            phase = cycler.phase.value
            ec = snap.error_code
            temp = snap.temperature
            cur = snap.motor_current
            logger.info(
                "Phase: %-8s | Err: %d | Temp: %.1f°C | Current: %.1fA",
                phase, ec, temp, cur,
            )
            if tachometer and belt_status:
                logger.info(
                    "Belt: %s | RPM: %.1f | Offset: %dpx",
                    belt_status["status"],
                    belt_status["rpm"],
                    belt_status["tracking_offset_px"],
                )

        stop.wait(args.interval / 1000.0)

    logger.info("Simulation stopped.")


if __name__ == "__main__":
    main()
