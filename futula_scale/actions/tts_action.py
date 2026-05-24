"""TTS action — announces weight through speakers using edge-tts + mpg123/aplay."""

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from . import BaseAction


def _find_player() -> list[str] | None:
    """Find the best available audio player command."""
    for name in ["mpg123", "ffplay", "aplay"]:
        path = shutil.which(name)
        if path:
            return path
    return None


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
        self._lock = threading.Lock()

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

        now = time.time()
        if now - self._last_time < self.cooldown:
            return
        if weight_g == self._last_announced_weight:
            return

        self._last_time = now
        self._last_announced_weight = weight_g

        text = self._format_weight(weight_g)
        print(f"[TTSAction] Speaking: {text}", flush=True)

        # Run _speak in a daemon thread to avoid blocking the BLE event loop
        t = threading.Thread(target=self._speak, args=(text,), daemon=True)
        t.start()

    def _speak(self, text: str):
        if not self._lock.acquire(blocking=False):
            print("[TTSAction] Already speaking, skipping", flush=True)
            return
        tmpfile = None
        try:
            fd, tmpfile = tempfile.mkstemp(suffix=".mp3")
            os.close(fd)

            # Generate TTS audio
            cmd = ["edge-tts", "--voice", self.voice, "--text", text,
                   "--write-media", tmpfile]
            r = subprocess.run(cmd, capture_output=True, timeout=15)
            if r.returncode != 0:
                print(f"[TTSAction] edge-tts failed: {r.stderr.decode()[:200]}", flush=True)
                return

            # Play audio
            player = _find_player()
            if not player:
                print("[TTSAction] No audio player found (need mpg123/ffplay/aplay)", flush=True)
                return

            if os.path.basename(player) == "mpg123":
                play_cmd = [player, "-q", tmpfile]
            elif os.path.basename(player) == "ffplay":
                play_cmd = [player, "-nodisp", "-autoexit", "-loglevel", "quiet", tmpfile]
            else:
                # aplay can't play mp3 — convert with sox if available
                sox = shutil.which("sox")
                if sox:
                    wav_file = tmpfile.replace(".mp3", ".wav")
                    subprocess.run([sox, tmpfile, wav_file], capture_output=True, timeout=10)
                    play_cmd = [player, "-q", wav_file]
                else:
                    play_cmd = [player, "-q", tmpfile]

            r = subprocess.run(play_cmd, capture_output=True, timeout=15)
            if r.returncode != 0:
                print(f"[TTSAction] Player failed: {r.stderr.decode()[:200]}", flush=True)

        except Exception as e:
            print(f"[TTSAction] Error: {e}", flush=True)
        finally:
            self._lock.release()
            if tmpfile:
                try:
                    os.unlink(tmpfile)
                    wav = tmpfile.replace(".mp3", ".wav")
                    if os.path.exists(wav):
                        os.unlink(wav)
                except Exception:
                    pass
