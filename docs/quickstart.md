# Pi-Factory Quickstart

## For the Cookoff Demo (Any Laptop)

### Step 1: Clone and Install
```bash
git clone https://github.com/Mikecranesync/pi-factory-cosmos.git
cd pi-factory-cosmos
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Run
```bash
# No API key needed — stub mode works out of the box
python simulate.py

# With real Cosmos R2 reasoning:
python simulate.py --nim-key=nvapi-your-key-here
```

### Step 3: Open
- Dashboard: http://localhost:8080
- API Docs: http://localhost:8080/docs
- Health: http://localhost:8080/api/health

The simulator auto-cycles through normal → warning → fault → recovery every 60 seconds.

---

## For the Real Pi-Factory (Raspberry Pi 4)

### What You Need
- Raspberry Pi 4 (4GB+ RAM)
- HMS Anybus CompactCom 029860-B (SPI adapter board)
- CompactCom M40 module (PROFINET, Modbus, or EtherCAT)
- DIN-rail enclosure
- Ethernet cable to factory switch
- MicroSD card with Raspberry Pi OS

### Step 1: Flash
Flash Raspberry Pi OS Lite (64-bit) to the SD card. Enable SSH.

### Step 2: First Run
```bash
# SSH into the Pi
ssh pi@<pi-ip-address>

# Clone and run first-run setup
git clone https://github.com/Mikecranesync/pi-factory-cosmos.git
cd pi-factory-cosmos
sudo ./pifactory/setup/firstrun.sh
```

The script will:
- Install Python dependencies in a virtual environment
- Install FUXA HMI via npm
- Prompt for your NIM API key and Telegram token
- Save configuration to `/etc/pifactory/config.env`
- Enable systemd services (tag server + Telegram bot)
- The Pi boots into a working Pi-Factory on next restart

### Step 3: Plug In
Connect the Ethernet cable from the Anybus CompactCom to the factory switch. The Pi-Factory appears as a certified industrial device on the network.

### Step 4: Access
- FUXA HMI: `http://<pi-ip>:1880`
- Tag API: `http://<pi-ip>:8080/api/tags`
- Telegram: Send `/status` to your bot

---

## Telegram Setup

1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Send `/newbot` and follow the prompts
3. Copy the bot token
4. Send a message to your new bot, then get your chat ID:
   ```bash
   curl https://api.telegram.org/bot<TOKEN>/getUpdates | python3 -m json.tool
   ```
5. Set environment variables:
   ```bash
   export TELEGRAM_BOT_TOKEN=your-token
   export TELEGRAM_CHAT_ID=your-chat-id
   ```

## Getting a Cosmos NIM API Key

1. Go to [build.nvidia.com](https://build.nvidia.com)
2. Find Cosmos Reason 2
3. Click "Get API Key"
4. Copy the `nvapi-...` key
