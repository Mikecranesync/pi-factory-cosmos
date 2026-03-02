# Pi-Factory — Industrial AI Diagnostics with NVIDIA Cosmos Reason 2

A maintenance technician on a factory floor shouldn't need a laptop, a vendor software license, or an engineering degree to see what their PLC is doing. They need their phone.

**Pi-Factory** is a Raspberry Pi 4 appliance that plugs into any factory ethernet switch, reads PLC tags over standard industrial protocols, runs AI-powered fault diagnosis through [NVIDIA Cosmos Reason 2](https://build.nvidia.com), and pushes results to a technician's phone via Telegram — in under 30 seconds.

## How It Works

```
Factory Ethernet Switch
        |
   Pi-Factory (Pi 4 + HMS Anybus CompactCom)
        |
   Reads broadcast PLC tags (PROFINET / Modbus / EtherCAT)
        |
   FastAPI tag server + fault classifier
        |
   ┌────┴────┐
   |         |
 FUXA HMI   Cosmos R2 NIM API
 (on Pi)     (multimodal: video + tags → diagnosis)
   |         |
   └────┬────┘
        |
   Telegram Bot → technician's phone
```

## Quickstart (Simulation Demo)

```bash
# 1. Clone and install
git clone https://github.com/Mikecranesync/pi-factory-cosmos.git
cd pi-factory-cosmos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Run (stub mode — no API key needed)
python simulate.py

# 3. Open dashboard
# → http://localhost:8080
# → http://localhost:8080/docs (API reference)
```

With a real NIM API key:
```bash
python simulate.py --nim-key=nvapi-your-key-here
```

With Telegram alerts:
```bash
export TELEGRAM_BOT_TOKEN=your-bot-token
export TELEGRAM_CHAT_ID=your-chat-id
python simulate.py --nim-key=nvapi-xxx --telegram
```

## How Cosmos R2 Is Used

Pi-Factory uses NVIDIA Cosmos Reason 2 as a **multimodal industrial reasoning engine**:

1. **Video + PLC Tags → Diagnosis**: Camera feed and real-time tag data are sent together. Cosmos R2 cross-references what it *sees* (conveyor stopped, parts jammed) with what the *instruments report* (motor current elevated, sensors blocked).

2. **`<think>` Reasoning**: Cosmos R2 shows its step-by-step reasoning before giving a diagnosis. The dashboard displays this reasoning panel so technicians (and judges) can see *how* the AI arrived at its conclusion.

3. **Discrepancy Detection**: When video and PLC data disagree (e.g., solenoid register shows ON but no motion visible), Cosmos flags the discrepancy — often revealing the actual root cause.

4. **Parameters**: `temperature=0.6`, `top_p=0.95`, `max_tokens=4096` — tuned for deterministic industrial reasoning, not creative generation.

## Production Hardware

The simulation demo runs on any laptop. The real Pi-Factory is a physical industrial appliance:

| Component | Part | Role |
|-----------|------|------|
| **Computer** | Raspberry Pi 4 (4GB+) | Edge compute, runs tag server + FUXA |
| **Industrial I/O** | [HMS Anybus CompactCom 029860-B](https://www.hms-networks.com/anybus) | SPI-to-GPIO adapter board |
| **Protocol Module** | [CompactCom M40](https://github.com/hms-networks/hms-abcc40) | Certified PROFINET/Modbus/EtherCAT device |
| **Enclosure** | DIN-rail mount | Standard industrial panel mounting |

The Anybus CompactCom makes the Pi appear as a **certified industrial device** on the factory network — the same way a drive, robot, or sensor module does. No proprietary software, no vendor login.

**Hardware mode**: Set `ANYBUS_HARDWARE=true` in `.env`. The tag server imports `hms.abcc40` instead of the simulator. Same API, same dashboard, real tags.

Reference: [hms-networks/abcc-example-raspberrypi](https://github.com/hms-networks/abcc-example-raspberrypi)

## HMI

### Production: FUXA
[FUXA](https://github.com/frangoteam/FUXA) (MIT licensed) is the production HMI — a full-featured industrial SCADA that runs directly on the Pi. Professional-grade, touchscreen-ready, real-time tag binding.

Install: `firstrun.sh` sets up FUXA automatically on a fresh Pi.

<!-- TODO: Add FUXA screenshot -->

### Demo Fallback: Built-in Dashboard
The simulation demo includes a lightweight web dashboard at `http://localhost:8080`. It shows live tags, detected faults, and the Cosmos R2 reasoning panel. This is the **demo fallback** — production runs FUXA.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              Path A: Cookoff Demo                    │
│  simulate.py → PLCSimulator → FastAPI tag_server     │
│                                    → dashboard.py    │
└──────────────────────┬──────────────────────────────┘
                       │
              ┌────────┴────────┐
              │  Cosmos R2 NIM  │   ← multimodal: video + tags
              │  (cloud API)    │
              └────────┬────────┘
                       │
┌──────────────────────┴──────────────────────────────┐
│            Path B: Production Pi-Factory              │
│  Anybus CompactCom M40 → SPI/GPIO → Pi 4             │
│  hms-abcc40 driver → FastAPI tag_server → FUXA HMI   │
└─────────────────────────────────────────────────────┘
              │
        Telegram Bot → technician's phone
```

The same `tag_server.py` runs in both paths. Only the tag source changes (`ANYBUS_HARDWARE=true/false`).

## Project Structure

```
pi-factory-cosmos/
├── simulate.py              # ONE COMMAND entry point
├── pifactory/
│   ├── backend/
│   │   ├── tag_server.py    # FastAPI: /tags, /faults, /diagnose, /combined
│   │   └── config.py        # Env var configuration
│   ├── cosmos/
│   │   ├── reasoner.py      # NIM API client + stub fallback
│   │   ├── prompts.py       # Industrial prompt templates
│   │   └── frame_capture.py # OpenCV fallback chain
│   ├── simulator/
│   │   ├── plc_sim.py       # PLC simulator + DemoCycler
│   │   └── fault_classifier.py  # 8+ fault codes
│   ├── hmi/
│   │   └── dashboard.py     # Demo fallback dashboard
│   ├── telegram/
│   │   ├── bot.py           # python-telegram-bot v20+ async
│   │   ├── tag_map.json     # Tag display metadata
│   │   └── alarms.json      # Fault code descriptions
│   └── setup/
│       ├── firstrun.sh      # Pi deployment script
│       ├── pifactory.service # systemd: tag server
│       └── telegram.service  # systemd: telegram bot
├── demo/
│   └── sample_tags.json     # Realistic fault snapshot
├── docs/
│   ├── architecture.md      # Dual-path architecture
│   ├── quickstart.md        # Technician setup card
│   └── cookoff_submission.md # 500-word submission
├── requirements.txt
├── .env.example
└── LICENSE                  # Apache 2.0
```

## API Reference

Start the server and visit `http://localhost:8080/docs` for interactive OpenAPI documentation.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/tags` | GET | Latest PLC tag snapshot |
| `/api/faults` | GET | Detected faults with severity |
| `/api/diagnose` | POST | AI diagnosis via Cosmos R2 |
| `/api/combined` | GET | Tags + faults + last diagnosis |
| `/api/health` | GET | Service health check |
| `/` | GET | Demo dashboard |
| `/docs` | GET | OpenAPI interactive docs |

## Telegram Commands

| Command | Description |
|---------|-------------|
| `/status` | Current PLC tag summary |
| `/see` | Trigger Cosmos R2 analysis |
| `/alarms` | List active faults |
| `/conflicts` | Show tag anomalies |
| `/help` | Command reference |

Auto-pushes alerts on critical/emergency fault transitions.

## Impact

| Before Pi-Factory | After Pi-Factory |
|---|---|
| Open laptop, launch vendor software, connect to PLC, navigate menus | Glance at phone |
| 15-30 min to diagnose a fault | 30 seconds |
| Requires engineering degree | Requires ability to read |
| One machine per license | Every machine on the network |

**MTTR: 30 minutes → 30 seconds.**

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Built With

- [NVIDIA Cosmos Reason 2](https://build.nvidia.com) — multimodal AI reasoning
- [HMS Anybus CompactCom](https://www.hms-networks.com/anybus) — industrial protocol gateway
- [FUXA](https://github.com/frangoteam/FUXA) — open-source SCADA/HMI
- [FastAPI](https://fastapi.tiangolo.com) — async Python API framework
- [python-telegram-bot](https://python-telegram-bot.org) — Telegram integration
