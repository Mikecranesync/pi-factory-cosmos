# Pi-Factory: Industrial AI Diagnostics with Cosmos Reason 2

## The Problem

A maintenance technician on a factory floor shouldn't need a laptop, a vendor software license, or an engineering degree to see what their PLC is doing. Today, diagnosing a conveyor jam means: find a laptop, launch proprietary software, connect to the PLC, navigate three menus, interpret cryptic register values, then walk back to the machine. That's 15-30 minutes of downtime for something a human could diagnose in seconds — if they could see the data.

## The Solution

**Pi-Factory** is a Raspberry Pi 4 with an HMS Anybus CompactCom M40 adapter in a DIN-rail enclosure. Plug it into any factory Ethernet switch and it joins the network as a certified PROFINET/Modbus/EtherCAT device — the same way a drive or sensor does. No proprietary software, no vendor login, no laptop.

The Pi reads broadcast PLC tags passively, runs a FastAPI tag server with real-time fault classification (8 fault codes covering emergency stops, overcurrent, overtemperature, jams, sensor failures, and pressure drops), and sends everything to **NVIDIA Cosmos Reason 2** for multimodal AI diagnosis.

## How Cosmos R2 Changes Everything

Cosmos Reason 2 is the key differentiator. Pi-Factory sends both a live camera feed and real-time PLC register data to Cosmos R2 simultaneously. The model cross-references what it *sees* (conveyor belt stopped, parts piled up at the transfer point) with what the instruments *report* (motor current elevated at 6.8A, both photoeye sensors blocked, error code 3).

When vision and sensor data disagree — for example, the solenoid register shows ON but no actuator motion is visible — Cosmos flags the discrepancy, often identifying the actual root cause (stuck actuator, wiring fault) that raw register data alone would miss.

The `<think>` reasoning capability is displayed directly in the dashboard, showing technicians the AI's step-by-step logic: checking motor current against speed, correlating sensor states with conveyor position, evaluating temperature trends. This transparency builds trust — technicians can verify the AI's reasoning matches their experience.

## Mobile-First Access

Results push directly to the technician's phone via a Telegram bot. Commands like `/status` show formatted PLC tags, `/see` triggers a Cosmos R2 analysis, and `/alarms` lists active faults in plain English. The bot auto-pushes alerts when fault severity escalates to critical or emergency.

The production HMI runs FUXA — an open-source industrial SCADA system on the Pi — for the control room touchscreen. But the real interface is the technician's pocket.

## Impact

**MTTR drops from 30 minutes to 30 seconds.** Plug in the Pi-Factory, open Telegram, and every machine on the network is visible. No licenses, no training, no engineering degree. Cosmos Reason 2 turns raw PLC registers and camera feeds into plain-English diagnoses that any technician can act on.

One Pi. Every machine. From anywhere on Earth.
