"""MQTT action — publishes weight to MQTT broker."""

import json
import time

from . import BaseAction


class MQTTAction(BaseAction):
    """Publishes stable weight readings to an MQTT broker.

    Config keys:
        host: MQTT broker hostname (default: "localhost")
        port: MQTT broker port (default: 1883)
        topic: MQTT topic (default: "futula_scale/weight")
        username: MQTT username (optional)
        password: MQTT password (optional)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.host = config.get("host", "localhost")
        self.port = config.get("port", 1883)
        self.topic = config.get("topic", "futula_scale/weight")
        self.username = config.get("username")
        self.password = config.get("password")
        self._client = None

    def on_start(self):
        try:
            import paho.mqtt.client as mqtt
            self._client = mqtt.Client()
            if self.username:
                self._client.username_pw_set(self.username, self.password or "")
            self._client.connect(self.host, self.port, 60)
            self._client.loop_start()
            print(f"[MQTTAction] Connected to {self.host}:{self.port}", flush=True)
        except ImportError:
            print("[MQTTAction] paho-mqtt not installed, skipping", flush=True)
            self._client = None
        except Exception as e:
            print(f"[MQTTAction] Connection failed: {e}", flush=True)
            self._client = None

    def on_stop(self):
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()

    async def on_weight(self, weight_g: int, stable: bool):
        if not self._client or not stable:
            return
        payload = json.dumps({"weight_g": weight_g, "ts": time.time()})
        self._client.publish(self.topic, payload)
