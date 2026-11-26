"""Stage: narration. One WAV per shot from Gemini TTS, cached by a hash of (text, voice, style, model)."""
from __future__ import annotations

import argparse
import base64
import time
import wave
from pathlib import Path

import requests

from . import prices
from .common import (OUT, ROOT, Cache, file_hash, run_ffmpeg, RetryableError, env, load_storyboard, log_call, raise_for_http,
                     select_shots, stable_hash, wav_duration, with_retries)

STAGE = "narration"
DIR = OUT / "narration"
API = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
SAMPLE_RATE = 24000  # Gemini TTS returns 16-bit mono PCM at 24 kHz


def write_wav(path: Path, pcm: bytes, rate: int = SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


@with_retries(attempts=3, base_delay=8)
def gemini_tts(text: str, cfg: dict, key: str) -> bytes:
    body = {
        "contents": [{"parts": [{"text": f"{cfg['style_prompt']}: {text}"}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": cfg["voice"]}}},
        },
    }
    try:
        r = requests.post(API.format(model=cfg["model"]), params={"key": key}, json=body, timeout=120)
    except requests.RequestException as e:
        raise RetryableError(str(e)) from e
    raise_for_http(r)
    data = r.json()
    try:
        part = data["candidates"][0]["content"]["parts"][0]["inlineData"]
    except (KeyError, IndexError) as e:
        raise RetryableError(f"no audio in response: {str(data)[:300]}") from e
    return base64.b64decode(part["data"])


def placeholder_pcm(text: str) -> bytes:
    """Silent audio with a length estimated from the text, used with --offline (no API key)."""
    seconds = max(2.0, len(text.split()) / 1.8)
    return b"\x00\x00" * int(seconds * SAMPLE_RATE)


PAUSE = "\n\n... ...\n\n"   # between lines in a batched call, to invite a clear pause


def silences(pcm: bytes, rate: int = SAMPLE_RATE, win_ms: int = 20, thresh: int = 330, min_ms: int = 250):
    """Return [(start_s, end_s)] of runs quieter than thresh (~ -40 dBFS) lasting at least min_ms."""
    import array
    a = array.array("h", pcm)
    n = rate * win_ms // 1000
    quiet = []
    for i in range(0, len(a), n):
        w = a[i:i + n]
        quiet.append(bool(w) and max(abs(x) for x in w) < thresh)
    runs, start = [], None
    for i, q in enumerate(quiet + [False]):
        if q and start is None:
            start = i
        elif not q and start is not None:
            if (i - start) * win_ms >= min_ms:
                runs.append((start * win_ms / 1000, i * win_ms / 1000))
            start = None
    return runs


def split_batch(pcm: bytes, texts: list[str], rate: int = SAMPLE_RATE) -> list[bytes]:
    """Cut one batched recording into len(texts) parts at the silences nearest the expected boundaries.

    Expected boundary = total speech time x cumulative share of characters. Raises if no usable silence is found,
    so a bad split never reaches the film silently.
    """
    total = len(pcm) / 2 / rate
    gaps = silences(pcm, rate)
    inner = [g for g in gaps if 0.3 < g[0] and g[1] < total - 0.3]
    chars = [len(t) for t in texts]
    cuts = []
    for k in range(1, len(texts)):
        expected = total * sum(chars[:k]) / sum(chars)
        cands = [g for g in inner if not cuts or (g[0] + g[1]) / 2 > cuts[-1] + 0.8]
        if not cands:
            raise RuntimeError(f"batch split failed: no silence near {expected:.1f}s (gaps={gaps})")
        best = min(cands, key=lambda g: abs((g[0] + g[1]) / 2 - expected) - 0.6 * (g[1] - g[0]))
        cuts.append((best[0] + best[1]) / 2)
    bounds = [0.0] + cuts + [total]
    parts = []
    for a, b in zip(bounds, bounds[1:]):
        seg = pcm[int(a * rate) * 2:int(b * rate) * 2]
        parts.append(trim_silence(seg, rate))
    return parts


def trim_silence(seg: bytes, rate: int = SAMPLE_RATE, pad_s: float = 0.12) -> bytes:
    gaps = silences(seg, rate, min_ms=60)
    dur = len(seg) / 2 / rate
    a = gaps[0][1] if gaps and gaps[0][0] == 0 else 0.0
    b = gaps[-1][0] if gaps and gaps[-1][1] >= dur - 0.03 else dur
    a, b = max(0.0, a - pad_s), min(dur, b + pad_s)
    return seg[int(a * rate) * 2:int(b * rate) * 2]


def run(only: list[str] | None = None, offline: bool = False, quiet: bool = False) -> dict[str, Path]:
    sb = load_storyboard()
    cfg = sb["models"]["tts"]
    batch_size = max(1, cfg.get("batch_size", 1))
    cache = Cache(STAGE)
    key = env("GEMINI_API_KEY")
    mode = "placeholder" if offline else "real"
    if not quiet:
        print(f"[{STAGE}] {len(select_shots(sb, only))} shots, model={cfg['model']}, voice={cfg['voice']}, "
              f"mode={mode}, batch_size={batch_size}")
    out: dict[str, Path] = {}
    todo = []  # (shot, hash, path) cache misses
    for shot in select_shots(sb, only):
        sid = shot["id"]
        # batch_size is NOT in the hash: a line's audio identity is its own text/voice/model.
        inputs = {"text": shot["narration"], "voice": cfg["voice"], "style": cfg["style_prompt"],
                  "model": cfg["model"], "mode": mode}
        h = stable_hash(inputs)
        path = DIR / f"{sid}.wav"
        src = shot.get("audio_source")
        if src:  # licensed external recording (consent in ETHICS.md): cut, never call TTS
            f = ROOT / src["file"]
            segs = src.get("segments") or [[src["start"], src["end"]]]
            # Hash the path, not the file contents: the full licensed recording is NOT in the public repo
            # (permission covers excerpts only), so a clean clone must hit the cache from the committed excerpts.
            h = stable_hash({"src": src["file"], "segs": segs, "gain": src.get("gain_db", 0)})
            hit = cache.hit(sid, h)
            if not hit and not f.exists():
                raise SystemExit(f"{sid}: audio_source file not found: {src['file']} (and no cached excerpt). "
                                 "The full recording is not distributed; see ETHICS.md.")
            if not hit:
                t0 = time.perf_counter()
                path.parent.mkdir(parents=True, exist_ok=True)
                pcm = b""
                for k, (sa, sb_) in enumerate(segs):
                    piece = path.with_name(f"{sid}_part{k}.wav")
                    run_ffmpeg(["-ss", str(sa), "-to", str(sb_), "-i", str(f), "-ac", "1", "-ar", str(SAMPLE_RATE),
                                "-af", f"volume={src.get('gain_db', 0)}dB,afade=t=in:d=0.05,areverse,afade=t=in:d=0.15,areverse",
                                "-sample_fmt", "s16", str(piece)])
                    with wave.open(str(piece), "rb") as w:
                        pcm += (b"\x00\x00" * int(0.35 * SAMPLE_RATE) if k else b"") + w.readframes(w.getnframes())
                    piece.unlink()
                write_wav(path, pcm)
                log_call(STAGE, shot=sid, model=f"external:{f.name}", status="extracted", model_call=False, input_hash=h,
                         output=path, latency_s=time.perf_counter() - t0,
                         params={"segments": segs}, extra={"audio_s": round(wav_duration(path), 2)})
                cache.put(sid, h, path, "external")
            elif not quiet:
                log_call(STAGE, shot=sid, model=f"external:{f.name}", status="cache_hit", model_call=False, input_hash=h, output=hit)
            out[sid] = path
            continue
        hit = cache.hit(sid, h)
        if hit:
            if not quiet:
                log_call(STAGE, shot=sid, model=cfg["model"], status="cache_hit", model_call=False, input_hash=h, output=hit)
            out[sid] = hit
        else:
            todo.append((shot, h, path))

    if todo and mode == "real" and not key:  # keys are only needed when something is not cached
        raise SystemExit(f"GEMINI_API_KEY missing and {len(todo)} line(s) need TTS. Put it in .env, or use --offline.")
    for i in range(0, len(todo), batch_size if mode == "real" else 1):
        group = todo[i:i + (batch_size if mode == "real" else 1)]
        ids = "+".join(s["id"] for s, _, _ in group)
        t0 = time.perf_counter()
        if mode == "placeholder":
            shot, h, path = group[0]
            write_wav(path, placeholder_pcm(shot["narration"]))
            log_call(STAGE, shot=shot["id"], model="placeholder-silence", status="placeholder", model_call=False,
                     input_hash=h, output=path, latency_s=time.perf_counter() - t0)
            cache.put(shot["id"], h, path, mode)
            out[shot["id"]] = path
            continue
        texts = [s["narration"] for s, _, _ in group]
        try:
            pcm = gemini_tts(PAUSE.join(texts), cfg, key)
            # Sanity check: TTS sometimes returns runaway audio (repeats / babble). ~1.8 words/s measured on
            # clean Amharic takes; reject anything over 2x expected + 3 s instead of letting it into the film.
            got = len(pcm) / 2 / SAMPLE_RATE
            limit = 2 * sum(len(t.split()) for t in texts) / 1.8 + 3
            if got > limit:
                raise RuntimeError(f"runaway TTS audio: {got:.1f}s for {ids}, limit {limit:.1f}s")
            parts = split_batch(pcm, texts) if len(group) > 1 else [pcm]
        except Exception as e:
            log_call(STAGE, shot=ids, model=cfg["model"], status="error", params={"voice": cfg["voice"],
                     "batch": len(group)}, latency_s=time.perf_counter() - t0, error=str(e))
            raise
        total = len(pcm) / 2 / SAMPLE_RATE
        log_call(STAGE, shot=ids, model=cfg["model"], status="ok", params={"voice": cfg["voice"], "batch": len(group)},
                 latency_s=time.perf_counter() - t0, cost_usd=prices.tts_cost(total), extra={"audio_s": round(total, 2)})
        for (shot, h, path), part in zip(group, parts):
            write_wav(path, part)
            dur = wav_duration(path)
            if len(group) > 1:
                log_call(STAGE, shot=shot["id"], model=cfg["model"], status="split", model_call=False, input_hash=h,
                         output=path, extra={"audio_s": round(dur, 2), "batch": ids})
            cache.put(shot["id"], h, path, mode)
            out[shot["id"]] = path
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", nargs="*")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    run(a.shot, a.offline)
