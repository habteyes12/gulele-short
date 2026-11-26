"""Transcribe a long external narration with timestamps, so shots can point at exact [start, end] ranges.

    python -m pipeline.transcribe assets/narration/atronos_gulele.m4a

Splits the file into 4-minute chunks (mono 16 kHz MP3), sends each to gemini-3.5-transcribe and asks for
sentence-level timestamps. Writes outputs/transcripts/<name>.json (absolute seconds) and a readable .txt.
Every call is logged to runs.jsonl. Already-transcribed chunks are cached.
"""
from __future__ import annotations

import base64
import json
import re
import sys
import time
from pathlib import Path

import requests

from .common import OUT, ROOT, RetryableError, env, log_call, media_duration, raise_for_http, run_ffmpeg, with_retries

MODEL = "gemini-3.5-transcribe"
CHUNK_S = 240
PROMPT = ("Transcribe this Amharic audiobook audio exactly, in Ge'ez script. Output one line per sentence in the form "
          "[mm:ss.s-mm:ss.s] sentence, with times relative to the start of this clip. Do not translate or summarise.")
LINE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\s*-\s*(\d+):(\d+(?:\.\d+)?)\]\s*(.+)")


FALLBACKS = [MODEL, "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.8-flash"]
_dead: set[str] = set()


def transcribe_chunk(mp3: Path, key: str) -> str:
    """Try each model in FALLBACKS; a model whose daily free quota is exhausted is skipped for the rest of the run."""
    last = None
    for m in FALLBACKS:
        if m in _dead:
            continue
        try:
            return _transcribe(mp3, key, m)
        except RuntimeError as e:
            last = e
            if "DAILY QUOTA" in str(e) or "HTTP 404" in str(e):
                print(f"    {m}: {'daily quota' if 'DAILY' in str(e) else 'not available'} -> next model")
                _dead.add(m)
                continue
            raise
        except RetryableError as e:  # e.g. 503 high demand after retries
            last = e
            _dead.add(m)
            continue
    raise last


@with_retries(attempts=3, base_delay=15)
def _transcribe(mp3: Path, key: str, model: str) -> str:
    body = {"contents": [{"parts": [{"text": PROMPT},
                                    {"inlineData": {"mimeType": "audio/mp3", "data": base64.b64encode(mp3.read_bytes()).decode()}}]}]}
    try:
        r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                          params={"key": key}, json=body, timeout=300)
    except requests.RequestException as e:
        raise RetryableError(str(e)) from e
    raise_for_http(r)
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def main(src: str) -> None:
    key = env("GEMINI_API_KEY")
    f = ROOT / src
    total = media_duration(f)
    work = OUT / "transcripts" / f.stem
    work.mkdir(parents=True, exist_ok=True)
    segments = []
    for i, start in enumerate(range(0, int(total) + 1, CHUNK_S)):
        txt = work / f"chunk{i:02}.txt"
        if not txt.exists():
            mp3 = work / f"chunk{i:02}.mp3"
            run_ffmpeg(["-ss", str(start), "-t", str(CHUNK_S), "-i", str(f), "-ac", "1", "-ar", "16000", "-b:a", "48k", str(mp3)])
            t0 = time.perf_counter()
            try:
                out = transcribe_chunk(mp3, key)
            except Exception as e:
                log_call("transcribe", shot=f"chunk{i:02}", model=MODEL, status="error", latency_s=time.perf_counter() - t0, error=str(e))
                raise
            txt.write_text(out, encoding="utf-8")
            log_call("transcribe", shot=f"chunk{i:02}", model=MODEL, status="ok", latency_s=time.perf_counter() - t0,
                     params={"chunk_start_s": start, "chunk_s": CHUNK_S}, output=txt)
        for line in txt.read_text(encoding="utf-8").splitlines():
            m = LINE.search(line)
            if m:
                a = int(m[1]) * 60 + float(m[2]) + start
                b = int(m[3]) * 60 + float(m[4]) + start
                segments.append({"start": round(a, 2), "end": round(b, 2), "text": m[5].strip()})
    (OUT / "transcripts" / f"{f.stem}.json").write_text(json.dumps(segments, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(OUT / "transcripts" / f"{f.stem}.txt", "w", encoding="utf-8") as fh:
        for s in segments:
            fh.write(f"{s['start']:7.2f}-{s['end']:7.2f}  {s['text']}\n")
    print(f"{len(segments)} segments, {total:.0f}s audio -> outputs/transcripts/{f.stem}.txt")


if __name__ == "__main__":
    main(sys.argv[1])
