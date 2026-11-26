"""Smoke test: call each provider once, log latency to runs.jsonl, and list the TTS models your key can see.

    python -m pipeline.smoke
"""
from __future__ import annotations

import time

import requests

from .common import OUT, env, load_storyboard, log_call
from .keyframes import cf_generate, save_image
from .narration import gemini_tts, write_wav


def main() -> None:
    sb = load_storyboard()
    key = env("GEMINI_API_KEY")
    if key:
        r = requests.get("https://generativelanguage.googleapis.com/v1beta/models", params={"key": key, "pageSize": 200},
                         timeout=30)
        names = [m["name"].removeprefix("models/") for m in r.json().get("models", [])]
        tts = [n for n in names if "tts" in n]
        print("TTS models visible to this key:", tts or "none")
        if sb["models"]["tts"]["model"] not in names:
            print(f"  WARNING: storyboard model '{sb['models']['tts']['model']}' not in list. Edit models.tts.model.")
        t0 = time.perf_counter()
        try:
            pcm = gemini_tts("ሰላም። ይህ የድምፅ ሙከራ ነው።", sb["models"]["tts"], key)
            p = OUT / "smoke" / "tts.wav"
            write_wav(p, pcm)
            log_call("smoke", shot=None, model=sb["models"]["tts"]["model"], status="ok", latency_s=time.perf_counter() - t0, output=p)
        except Exception as e:
            log_call("smoke", shot=None, model=sb["models"]["tts"]["model"], status="error", latency_s=time.perf_counter() - t0, error=str(e))
    else:
        print("GEMINI_API_KEY not set - skipping TTS")

    acc, tok = env("CLOUDFLARE_ACCOUNT_ID"), env("CLOUDFLARE_API_TOKEN")
    if acc and tok:
        t0 = time.perf_counter()
        cfg = sb["models"]["image"]
        try:
            data = cf_generate("a single eucalyptus tree on a hill at dawn, " + sb["style"]["block"], 7, cfg, acc, tok, [])
            p = OUT / "smoke" / "image.png"
            save_image(p, data)
            log_call("smoke", shot=None, model=cfg["model"], status="ok", latency_s=time.perf_counter() - t0, output=p)
        except Exception as e:
            log_call("smoke", shot=None, model=cfg["model"], status="error", latency_s=time.perf_counter() - t0, error=str(e))
    else:
        print("Cloudflare credentials not set - skipping image")


if __name__ == "__main__":
    main()
