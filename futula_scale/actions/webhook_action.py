"""HTTP webhook action — sends weight to an HTTP endpoint."""

import json
import time

from . import BaseAction


class WebhookAction(BaseAction):
    """Sends stable weight readings to an HTTP endpoint as JSON POST.

    Config keys:
        url: webhook URL (required)
        method: HTTP method (default: "POST")
        headers: additional headers dict (optional)
        cooldown: minimum seconds between requests (default: 2)
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.url = config.get("url")
        self.method = config.get("method", "POST")
        self.headers = config.get("headers", {})
        self.cooldown = config.get("cooldown", 2)
        self._last_time = 0.0

    async def on_weight(self, weight_g: int, stable: bool):
        if not self.url or not stable:
            return

        now = time.time()
        if now - self._last_time < self.cooldown:
            return
        self._last_time = now

        import urllib.request
        payload = json.dumps({"weight_g": weight_g, "ts": now}).encode()
        req = urllib.request.Request(
            self.url, data=payload, method=self.method,
            headers={"Content-Type": "application/json", **self.headers},
        )
        try:
            urllib.request.urlopen(req, timeout=5)
        except Exception as e:
            print(f"[WebhookAction] Error: {e}", flush=True)
