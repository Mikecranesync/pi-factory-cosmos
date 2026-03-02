# Pi-Factory Field Technician Guide

## What Is Pi-Factory?

Pi-Factory is a small box (Raspberry Pi) that plugs into your factory network and reads your PLC data automatically. It shows you what every machine is doing — on your phone, in plain English, without opening a laptop or launching any vendor software.

When something goes wrong, Pi-Factory:
1. Detects the fault instantly using built-in rules
2. Sends an AI system (NVIDIA Cosmos) both the sensor data AND a camera feed
3. Gets back a plain-English diagnosis with step-by-step checks
4. Pushes it to your phone via Telegram

You don't install anything on the PLC. You don't need Connected Components Workbench, RSLogix, or any vendor license. You just plug in the box and open Telegram.

---

## How to Access Pi-Factory

You have three ways to see your equipment status:

| Method | When to Use | How |
|--------|-------------|-----|
| **Telegram** (recommended) | Anywhere — floor, break room, home | Open Telegram, message the Pi-Factory bot |
| **Web Dashboard** | At a workstation or on your phone browser | Go to `http://<pi-ip>:8080` |
| **FUXA HMI** | Control room touchscreen | Go to `http://<pi-ip>:1880` |

Your plant engineer will give you the Pi-Factory's IP address and the Telegram bot link during setup.

---

## Telegram Commands

Open the Pi-Factory bot in Telegram and type any of these:

### /status — "What's happening right now?"

Shows a formatted summary of every PLC tag:

```
PLC Status:

  Motor: ON
  Motor Speed: 60%
  Motor Current: 3.2A
  Temperature: 34.5°C
  Pressure: 98PSI
  Conveyor: ON
  Sensor 1 (Entry): OFF
  Sensor 2 (Exit): OFF
```

Use this as your first check when you walk up to a machine. Compare what the screen says to what you see physically. If they don't match, you found the problem.

### /see — "What does the AI think?"

Triggers a full AI analysis. Pi-Factory sends the current sensor data (and camera feed if available) to NVIDIA Cosmos Reason 2, which cross-references what the instruments say with what the camera sees.

You'll get back something like:

```
Conveyor jam detected. Material flow interrupted.

Root Cause: Physical obstruction in conveyor path

Suggested Checks:
  - Clear jammed material from conveyor path
  - Inspect photoeye sensors for alignment
  - Check conveyor belt tracking
  - Verify guide rail spacing

Model: nvidia/cosmos-reason2-8b | 2300ms | Confidence: 88%
```

The **confidence percentage** tells you how sure the AI is. Above 80% is high confidence. Below 50% means it's guessing — use your own judgment.

### /alarms — "What's broken?"

Lists every active fault with severity:

```
Active Alarms (2):

  [CRITICAL] C001: Conveyor Jam Detected
    Both part sensors are active simultaneously. Product flow is blocked.
  [WARNING] T002: Elevated Temperature
    Temperature (72.3°C) is above normal (65°C). Monitor closely.
```

Severity levels:
- **EMERGENCY** — Safety issue. Do not restart without safety review.
- **CRITICAL** — Equipment stopped or at risk. Needs attention now.
- **WARNING** — Degraded but still running. Plan to address soon.
- **INFO** — Normal operation. Nothing to do.

### /conflicts — "Is the data making sense?"

Checks for contradictions in the sensor data. These often point to the real root cause:

```
Tag Conflicts:

  - Conveyor marked RUNNING but speed is 0 — possible jam or VFD fault
```

If the motor register says ON but current is near zero, the contactor probably failed. If the conveyor says RUNNING but speed is zero, it's jammed. Pi-Factory catches these automatically.

### /help — "What can I type?"

Shows the command list.

---

## Automatic Alerts

You don't always have to ask. Pi-Factory watches for fault transitions and **pushes alerts to your phone automatically** when something goes critical or emergency:

```
ALERT: Conveyor Jam Detected
Both part sensors are active simultaneously. Product flow is blocked.
```

You'll get notified within seconds of a fault condition appearing.

---

## Web Dashboard

Open `http://<pi-ip>:8080` in any browser (phone or desktop).

### What You See

The dashboard has three sections:

**1. Live I/O Status (top left)**
Every PLC tag, color-coded:
- Green = running / healthy
- Yellow = warning range
- Red = critical / fault
- Gray = stopped / off

Updates every 2 seconds automatically.

**2. Detected Faults (top right)**
Active fault cards with severity badge. Same information as `/alarms` in Telegram.

**3. Cosmos R2 Diagnosis (bottom)**
Type a question in plain English and hit "Diagnose":
- "Why is this stopped?"
- "What should I check first?"
- "Is the motor overloaded?"
- "Give me a quick status check"

The AI will respond with:
- **Reasoning panel** (green box) — shows the AI's step-by-step thinking
- **Diagnosis** — the actual answer with suggested checks
- **Confidence bar** — visual gauge of how sure the AI is
- **Latency** — how long the AI took to respond

---

## Understanding the Tags

These are the values Pi-Factory reads from your PLC:

| Tag | What It Means | Normal Range | Watch Out |
|-----|---------------|-------------|-----------|
| **Motor** | Is the motor energized? | ON when running | OFF unexpectedly = check starter |
| **Motor Speed** | How fast (% of max) | 40-80% typical | 0% when motor is ON = stall |
| **Motor Current** | Electrical load (amps) | 1.5-4.5A | >5.0A = overload, check for jam |
| **Temperature** | Motor/enclosure temp | 20-55°C | >65°C = warning, >80°C = shut down |
| **Pressure** | Pneumatic supply | 80-120 PSI | <60 PSI = actuators won't work |
| **Conveyor** | Is belt moving? | ON when running | ON but speed=0 = jam |
| **Sensor 1 (Entry)** | Part at entry photoeye | Toggles ON/OFF | Stuck ON = part jammed at entry |
| **Sensor 2 (Exit)** | Part at exit photoeye | Toggles ON/OFF | Both sensors ON at once = jam |

---

## Fault Code Reference

When something goes wrong, the PLC sets an error code. Here's what each one means and what to do:

### Code 0 — No Fault
Everything is running normally. No action needed.

### Code 1 — Motor Overload
**What happened:** Motor is drawing too much current (over 5.0 amps).
**What to do:**
1. Check the conveyor for jammed material or obstructions
2. Feel the motor housing — if it's hot, let it cool before restarting
3. Check belt tension — too tight causes excess load
4. Inspect motor bearings — listen for grinding
5. Check the thermal overload relay on the starter

### Code 2 — Temperature High
**What happened:** Motor or enclosure temperature is above 80°C.
**What to do:**
1. Check if the cooling fan is running
2. Clear any blocked vents or air filters
3. Check ambient temperature — is HVAC working?
4. Reduce motor speed/load if possible
5. Do NOT restart until temperature drops below 60°C

### Code 3 — Conveyor Jam
**What happened:** Product is stuck. Both entry and exit sensors are blocked.
**What to do:**
1. Look at the conveyor — find the jammed product
2. Clear it by hand (follow lockout/tagout if reaching into mechanism)
3. Check downstream — is the next station full/stopped?
4. Verify photoeye sensors are aligned after clearing
5. Check guide rails — a shifted rail can cause repeat jams

### Code 4 — Sensor Failure
**What happened:** A photoeye sensor is not responding or giving erratic readings.
**What to do:**
1. Check the sensor indicator light — is it lit?
2. Inspect wiring at the sensor and at the PLC terminal
3. Clean the sensor lens (dust and debris cause false readings)
4. Try blocking the sensor with your hand — does the indicator change?
5. If nothing works, replace the sensor

### Code 5 — Communication Loss
**What happened:** The PLC lost contact with a networked device.
**What to do:**
1. Check Ethernet cables — are they plugged in firmly?
2. Look at the network switch — are the link lights on?
3. Check if the downstream device has power
4. Try unplugging and re-plugging the Ethernet cable
5. If the problem persists, contact your controls engineer

### Code 6 — VFD Fault
**What happened:** The variable frequency drive tripped.
**What to do:**
1. Look at the VFD display — it shows a specific fault code
2. Write down the VFD fault code for your controls engineer
3. Common VFD faults: overcurrent (OC), overvoltage (OV), overtemperature (OH)
4. Try resetting the VFD by cycling its power (if safe to do so)
5. If it trips again immediately, do not keep resetting — call engineering

### Code 7 — Low Pressure
**What happened:** Pneumatic supply pressure dropped below operating threshold.
**What to do:**
1. Check the main air compressor — is it running?
2. Listen for air leaks near cylinders and valves
3. Check the regulator and filter near the machine
4. Verify the compressor tank pressure gauge
5. If you hear a big leak, shut off air to that branch and report it

### Code 8 — E-Stop Active
**What happened:** Someone pressed the emergency stop, or a safety interlock tripped.
**What to do:**
1. **STOP. Look around.** Make sure the area is safe.
2. Find out why the E-stop was pressed — ask anyone nearby
3. Inspect the machine for visible damage
4. Once safe, twist the E-stop to release it
5. Clear faults on the HMI/PLC, then restart in the correct sequence

---

## When to Call Engineering

Pi-Factory helps you handle most routine faults. Call your controls engineer when:

- The same fault keeps coming back after you clear it (3+ times in a shift)
- You see **VFD fault codes** you don't recognize
- The AI confidence is below 50% and you're not sure either
- `/conflicts` shows contradictions you can't explain physically
- Any **EMERGENCY** severity fault involving safety interlocks
- Communication loss that doesn't resolve with cable checks

---

## Quick Reference Card

Print this and tape it to the panel:

```
╔══════════════════════════════════════════╗
║         PI-FACTORY QUICK REFERENCE       ║
╠══════════════════════════════════════════╣
║                                          ║
║  TELEGRAM COMMANDS:                      ║
║    /status    — see all tag values       ║
║    /see       — AI diagnosis             ║
║    /alarms    — active faults            ║
║    /conflicts — data contradictions      ║
║    /help      — command list             ║
║                                          ║
║  WEB DASHBOARD:                          ║
║    http://<pi-ip>:8080                   ║
║                                          ║
║  FAULT SEVERITY:                         ║
║    EMERGENCY — safety issue, don't       ║
║                restart without review    ║
║    CRITICAL  — stopped, fix now          ║
║    WARNING   — degraded, plan to fix     ║
║    INFO      — all clear                 ║
║                                          ║
║  COMMON ERROR CODES:                     ║
║    1 = Motor overload (check for jams)   ║
║    2 = Temp high (check cooling)         ║
║    3 = Conveyor jam (clear obstruction)  ║
║    4 = Sensor failure (check wiring)     ║
║    5 = Comms loss (check cables)         ║
║    8 = E-Stop (verify area is safe)      ║
║                                          ║
║  CURRENT LIMITS:                         ║
║    Motor current > 5.0A = OVERLOAD       ║
║    Temperature > 65°C = WARNING          ║
║    Temperature > 80°C = CRITICAL         ║
║    Pressure < 60 PSI = LOW               ║
║                                          ║
╚══════════════════════════════════════════╝
```

---

## Frequently Asked Questions

**Q: Do I need to install anything on my phone?**
A: Just Telegram (free from app store). No other apps needed.

**Q: Does Pi-Factory change anything on the PLC?**
A: No. It only reads data. It cannot write to the PLC, start motors, or change any settings. It is read-only.

**Q: What if the AI gives a wrong diagnosis?**
A: The AI is a second opinion, not a replacement for your experience. Always verify physically. If the confidence is low (<50%), trust your own judgment.

**Q: What if Pi-Factory itself goes offline?**
A: Your machines keep running normally. Pi-Factory is a monitoring tool only — it doesn't control anything. If it goes offline, you just lose visibility until it's back.

**Q: Can I use this from home?**
A: If your plant has VPN or Tailscale set up, yes. The Telegram bot works from anywhere with internet. Ask your IT department.

**Q: How often does it check the PLC?**
A: Every 2 seconds for dashboard display. The fault classifier runs on every check. The AI analysis runs on demand (when you type `/see`) or automatically when a new critical fault appears.
