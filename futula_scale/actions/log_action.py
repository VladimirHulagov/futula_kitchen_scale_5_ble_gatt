"""Log action — writes weight readings to JSONL file."""

import json
import os
import time

from . import BaseAction


class LogAction(BaseAction):
    """Logs all weight notifications to a JSONL file.

    Config keys:
        path: path to JSONL log file (default: "/tmp/futula_log.jsonl")
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.path = config.get("path", "/tmp/futula_log.jsonl")

    async def on_weight(self, weight_g: int, stable: bool):
        entry = {
            "ts": time.time(),
            "weight_g": weight_g,
            "stable": stable,
        }
        with open(self.path, "a") as f:
            f.write(json.dumps(entry) + "\n")
