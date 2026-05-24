# FUTULA Kitchen Scale 5 — BLE GATT Reader

Python daemon that connects to a **FUTULA Kitchen Scale 5** via BLE (Bluetooth Low Energy), decodes weight readings in real-time, and dispatches them to configurable **actions** (TTS, logging, MQTT, HTTP webhooks, or custom).

## Features

- Automatic BLE scanning, connection, and reconnection
- Real-time weight decoding with stability detection
- Pluggable action system — react to weighings however you want
- Built-in actions: **TTS voice announcement**, JSONL logging, MQTT, HTTP webhook
- Custom actions via a simple Python class interface
- systemd service unit included
- Zero external dependencies for core (only `bleak` + `pyyaml`)

## BLE Protocol (Reverse-Engineered)

The scale advertises as **"Kitchen Scale3"** and exposes a custom GATT service:

| Characteristic | UUID | Properties |
|---|---|---|
| Weight data | `0000fff4-...` | notify |
| Command | `0000fff1-...` | write |
| Battery level | `00002a19-...` | read, notify |

**Notification packet** (11 bytes):

```
[0]     0xCA     — header
[1-2]   0x00     — reserved
[3]     XX       — weight in grams (0–255)
[4]     0x00     — reserved
[5-7]   0x00     — reserved
[8]     0x04     — version/flags
[9]     YY       — stability: 0x01 = stable, 0x00 = changing
[10]    ZZ       — XOR checksum of bytes[0:10]
```

Calibrated against a known 222g reference object: `byte[3] = 0xDE = 222`.

## Quick Start

### Install

```bash
pip install -r requirements.txt
pip install -r requirements-optional.txt  # for TTS, MQTT, etc.
```

### Configure

```bash
cp config.example.yaml config.yaml
# Edit MAC address and enable/disable actions
```

### Run

```bash
# Foreground (debugging)
python3 -m futula_scale config.yaml

# As systemd service
sudo cp config.yaml /etc/futula_scale/config.yaml
sudo cp futula-scale.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now futula-scale
```

## Actions

Actions are Python classes that implement `on_weight(weight_g, stable)`. Enable them in `config.yaml`:

### Built-in Actions

#### `tts` — Voice Announcement
Speaks the weight through speakers when it stabilizes. Uses `edge-tts` for synthesis and `aplay`/`mpg123` for playback.

```yaml
actions:
  tts:
    enabled: true
    voice: "ru-RU-DmitryNeural"
    cooldown: 5
    announce_unit: "auto"  # "g", "kg", or "auto"
```

#### `log` — JSONL Logger
Appends every reading to a JSONL file.

```yaml
actions:
  log:
    enabled: true
    path: "/tmp/futula_log.jsonl"
```

#### `mqtt` — MQTT Publish
Publishes stable readings as JSON to an MQTT broker. Requires `paho-mqtt`.

```yaml
actions:
  mqtt:
    enabled: true
    host: "homeassistant.local"
    topic: "futula_scale/weight"
```

#### `webhook` — HTTP Webhook
POSTs stable readings as JSON to an HTTP endpoint.

```yaml
actions:
  webhook:
    enabled: true
    url: "http://homeassistant:8123/api/webhook/futula_scale"
```

### Custom Actions

Create a Python class implementing `BaseAction`:

```python
from futula_scale.actions import BaseAction

class MyAction(BaseAction):
    async def on_weight(self, weight_g: int, stable: bool):
        if stable and weight_g > 0:
            print(f"Weight: {weight_g}g")
```

Register in config:

```yaml
actions:
  mine:
    enabled: true
    class: "my_module:MyAction"
    my_param: "hello"
```

## Hardware

- **Scale**: FUTULA Kitchen Scale 5 (BLE, TI CC2652 chipset)
- **Tested on**: Khadas VIM2 (ARM64, built-in Broadcom BCM43438 Bluetooth)
- **Range**: ~3-5 meters with on-board antenna

## Requirements

- Python 3.10+
- Linux with BlueZ (`bluetooth.service`)
- `bleak` for BLE communication
- `edge-tts` for TTS action (optional)
- ALSA (`aplay`) or `mpg123` for audio playback (optional)

## License

MIT
