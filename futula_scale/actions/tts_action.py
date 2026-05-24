"""TTS action — announces weight through speakers using edge-tts + aplay."""

import asyncio
import os
import subprocess
import tempfile

from . import BaseAction


class TTSAction(BaseAction):
    """Speaks the weight through speakers when it stabilizes.

    Config keys:
        voice: edge-tts voice name (default: "ru-RU-DmitryNeural")
        volume: edge-tts volume string (default: "+50%")
        device: ALSA audio device for aplay (default: "default")
        cooldown: minimum seconds between announcements (default: 5)
        announce_unit: "g", "kg", or "auto" (default: "auto")
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self.voice = config.get("voice", "ru-RU-DmitryNeural")
        self.volume = config.get("volume", "+50%")
        self.device = config.get("device", "default")
        self.cooldown = config.get("cooldown", 5)
        self.announce_unit = config.get("announce_unit", "auto")
        self._last_announced_weight = None
        self._last_time = 0.0
        self._speaking = False

    def _format_weight(self, weight_g: int) -> str:
        if self.announce_unit == "kg" or (self.announce_unit == "auto" and weight_g >= 1000):
            kg = weight_g / 1000
            if kg == int(kg):
                return f"{int(kg)} килограмм"
            return f"{kg:.1f} килограмма".replace(".", " целых и ")
        return f"{weight_g} грамм"

    async def on_weight(self, weight_g: int, stable: bool):
        if not stable or weight_g == 0:
            return

        import time
        now = time.time()
        if now - self._last_time < self.cooldown:
            return
        if weight_g == self._last_announced_weight:
            return

        self._last_time = now
        self._last_announced_weight = weight_g

        text = self._format_weight(weight_g)

        # Run in thread to not block the BLE event loop
        asyncio.get_event_loop().run_in_executor(None, self._speak, text)

    def _speak(self, text: str):
        if self._speaking:
            return
        self._speaking = True
        try:
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                tmpfile = f.name

            # Generate TTS audio
            cmd = ["edge-tts", "--voice", self.voice, "--text", text, "--write-media", tmpfile]
            subprocess.run(cmd, check=True, capture_output=True, timeout=10)

            # Play via aplay (pipe through ffmpeg or mpg123 if available)
            if os.path.exists("/usr/bin/mpg123"):
                play_cmd = ["mpg123", "-a", self.device, "-q", tmpfile]
            elif os.path.exists("/usr/bin/ffplay"):
                play_cmd = ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", tmpfile]
            else:
                # Try aplay (won't work with mp3, but worth trying if wav)
                play_cmd = ["aplay", "-D", self.device, "-q", tmpfile]

            subprocess.run(play_cmd, capture_output=True, timeout=15)
        except Exception as e:
            print(f"[TTSAction] Error: {e}", flush=True)
        finally:
            self._speaking = False
            try:
                os.unlink(tmpfile)
            except Exception:
                pass
