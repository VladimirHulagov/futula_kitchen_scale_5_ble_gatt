#!/usr/bin/env python3
"""FUTULA Kitchen Scale 5 BLE GATT daemon.

Connects to a FUTULA kitchen scale via BLE, reads weight notifications,
and dispatches them to configurable actions (TTS, log, MQTT, webhook, etc.).

Usage:
    python3 -m futula_scale [config.yaml]

If no config file is specified, looks for:
    ./config.yaml
    /etc/futula_scale/config.yaml
"""

from __future__ import annotations

import asyncio
import importlib
import os
import signal
import sys
import yaml

from bleak import BleakClient, BleakScanner

# ---------------------------------------------------------------------------
# Protocol constants (FUTULA Kitchen Scale 5, BLE GATT)
# ---------------------------------------------------------------------------
MAC_DEFAULT = "CF:E7:1E:16:04:1A"
NOTIFY_UUID = "0000fff4-0000-1000-8000-00805f9b34fb"
WRITE_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"
BATTERY_UUID = "00002a19-0000-1000-8000-00805f9b34fb"
HEADER_BYTE = 0xCA
MIN_PACKET_LEN = 11

# ---------------------------------------------------------------------------
# Built-in action registry
# ---------------------------------------------------------------------------
BUILTIN_ACTIONS = {
    "log": "futula_scale.actions.log_action:LogAction",
    "tts": "futula_scale.actions.tts_action:TTSAction",
    "mqtt": "futula_scale.actions.mqtt_action:MQTTAction",
    "webhook": "futula_scale.actions.webhook_action:WebhookAction",
}


def load_action_class(dotted_path: str):
    """Load an action class from a 'module.path:ClassName' string."""
    module_path, class_name = dotted_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def parse_packet(data: bytes) -> dict | None:
    """Parse a FUTULA Kitchen Scale 5 BLE notification packet.

    Packet format (11 bytes):
        [0]    0xCA header
        [1-2]  0x00 0x00
        [3]    Weight in grams (0-255)
        [4]    Reserved
        [5-7]  0x00 0x00 0x00
        [8]    0x04
        [9]    Stability flag: 0x01=stable, 0x00=changing
        [10]   XOR checksum of bytes[0:10]

    Returns dict with weight_g and stable, or None if invalid.
    """
    if len(data) < MIN_PACKET_LEN or data[0] != HEADER_BYTE:
        return None

    # Verify XOR checksum
    checksum = 0
    for i in range(10):
        checksum ^= data[i]
    if checksum != data[10]:
        return None

    return {
        "weight_g": data[3],
        "stable": data[9] == 0x01,
    }


class FutulaDaemon:
    """BLE daemon that connects to FUTULA scale and dispatches actions."""

    def __init__(self, config: dict):
        self.mac = config.get("mac", MAC_DEFAULT).upper()
        self.scan_timeout = config.get("scan_timeout", 10)
        self.connect_timeout = config.get("connect_timeout", 15)
        self.reconnect_delay = config.get("reconnect_delay", 5)
        self.running = True
        self.actions: list = []
        self._load_actions(config.get("actions", {}))

    def _load_actions(self, actions_config: dict):
        for action_name, action_config in actions_config.items():
            if not action_config.get("enabled", True):
                continue

            # Resolve class path
            class_path = action_config.get("class")
            if not class_path:
                class_path = BUILTIN_ACTIONS.get(action_name)
            if not class_path:
                print(f"Unknown action '{action_name}', skipping", flush=True)
                continue

            try:
                cls = load_action_class(class_path)
                instance = cls(action_config)
                self.actions.append(instance)
                print(f"Loaded action: {action_name} ({class_path})", flush=True)
            except Exception as e:
                print(f"Failed to load action '{action_name}': {e}", flush=True)

    async def _dispatch(self, weight_g: int, stable: bool):
        for action in self.actions:
            try:
                await action.on_weight(weight_g, stable)
            except Exception as e:
                print(f"Action error: {e}", flush=True)

    def _notification_handler(self, sender, data):
        parsed = parse_packet(bytes(data))
        if parsed is None:
            return
        weight_g = parsed["weight_g"]
        stable = parsed["stable"]
        flag = "STABLE" if stable else "..."
        print(f"[{flag}] {weight_g}g", flush=True)
        # Dispatch in the event loop (bleak calls this from a BLE thread)
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            loop.call_soon_threadsafe(
                lambda w=weight_g, s=stable: asyncio.ensure_future(self._dispatch(w, s))
            )

    async def _connect_and_listen(self, device):
        async with BleakClient(device, timeout=self.connect_timeout) as client:
            print(f"Connected to {self.mac}!", flush=True)

            # Read battery
            try:
                batt = await client.read_gatt_char(BATTERY_UUID)
                print(f"Battery: {int.from_bytes(batt, 'little')}%", flush=True)
            except Exception:
                pass

            # Subscribe to weight notifications
            await client.start_notify(NOTIFY_UUID, self._notification_handler)
            print("Listening for weight data...", flush=True)

            # Wait until disconnected (scale sleeps)
            while client.is_connected and self.running:
                await asyncio.sleep(1)

            await client.stop_notify(NOTIFY_UUID)
            print("Scale disconnected", flush=True)

    async def run(self):
        """Main loop: scan, connect, listen, reconnect."""
        print(f"FUTULA Scale Daemon v1.0", flush=True)
        print(f"MAC: {self.mac}", flush=True)
        print(f"Actions: {len(self.actions)} loaded", flush=True)

        # Start lifecycle hooks
        for action in self.actions:
            action.on_start()

        try:
            while self.running:
                try:
                    # Continuous scan — detect as fast as possible
                    print(f"Scanning for scale...", flush=True)
                    target = await BleakScanner.find_device_by_address(
                        self.mac, timeout=30.0
                    )

                    if target:
                        print(f"Found: {self.mac}", flush=True)
                        await self._connect_and_listen(target)
                    else:
                        print("Scale not found after 30s", flush=True)

                except Exception as e:
                    print(f"Error: {e}", flush=True)

                if self.running:
                    print(f"Retrying in {self.reconnect_delay}s...", flush=True)
                    await asyncio.sleep(self.reconnect_delay)

        finally:
            for action in self.actions:
                try:
                    action.on_stop()
                except Exception:
                    pass
            print("Daemon stopped", flush=True)

    def stop(self):
        self.running = False


def load_config(path: str | None) -> dict:
    """Load YAML config, searching default locations if path not given."""
    search_paths = [path] if path else []
    if not path:
        search_paths = [
            os.path.join(os.getcwd(), "config.yaml"),
            "/etc/futula_scale/config.yaml",
        ]

    for p in search_paths:
        if p and os.path.exists(p):
            with open(p) as f:
                return yaml.safe_load(f) or {}
    return {}


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else None
    config = load_config(config_path)

    daemon = FutulaDaemon(config)

    loop = asyncio.get_event_loop()

    def _signal_handler():
        print("\nShutting down...", flush=True)
        daemon.stop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _signal_handler)

    loop.run_until_complete(daemon.run())


if __name__ == "__main__":
    main()
