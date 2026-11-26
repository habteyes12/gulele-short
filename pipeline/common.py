"""Shared helpers: storyboard loading + validation, content-hash cache, run logging, retries, ffmpeg."""
from __future__ import annotations

import functools
import hashlib
import json
import os
import shutil
import subprocess
import time
import uuid
import wave
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

ROOT = Path(__file__).resolve().parent.parent
STORYBOARD = ROOT / (os.environ.get("PIPELINE_STORYBOARD") or "storyboard.json")
SCHEMA = ROOT / "schema" / "storyboard.schema.json"
OUT = ROOT / "outputs"
CACHE_DIR = OUT / "cache"
RUNS = ROOT / "runs.jsonl"

RUN_ID = os.environ.get("PIPELINE_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:4]

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except ImportError:  # dotenv is optional; env vars still work
    pass


# ---------------------------------------------------------------- storyboard
def load_storyboard(path: Path = STORYBOARD) -> dict:
    """Load storyboard.json and validate it against the JSON Schema. Raises on any error."""
    data = json.loads(path.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.path))
    if errors:
        msg = "\n".join(f"  - {'/'.join(map(str, e.path)) or '<root>'}: {e.message}" for e in errors)
        raise SystemExit(f"storyboard.json failed schema validation:\n{msg}")
    ids = [s["id"] for s in data["shots"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("storyboard.json: shot ids must be unique")
    for s in data["shots"]:
        for c in s["characters"]:
            if c not in data["characters"]:
                raise SystemExit(f"storyboard.json: shot {s['id']} uses unknown character '{c}'")
    for cue in data["music"].get("cues", []):
        if cue["at_shot"] not in ids:
            raise SystemExit(f"storyboard.json: music cue points at unknown shot '{cue['at_shot']}'")
    return data


def select_shots(sb: dict, only: list[str] | None) -> list[dict]:
    if not only:
        return sb["shots"]
    return [s for s in sb["shots"] if s["id"] in only]


# ---------------------------------------------------------------- hashing / cache
def stable_hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


class Cache:
    """Per-stage manifest: key -> {hash, output, mode}. A step is skipped when its input hash is unchanged and the output exists."""

    def __init__(self, stage: str):
        self.stage = stage
        self.path = CACHE_DIR / f"{stage}.json"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.data = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def hit(self, key: str, h: str) -> Path | None:
        entry = self.data.get(key)
        if entry and entry["hash"] == h and (ROOT / entry["output"]).exists():
            return ROOT / entry["output"]
        return None

    def put(self, key: str, h: str, output: Path, mode: str = "real") -> None:
        self.data[key] = {"hash": h, "output": output.relative_to(ROOT).as_posix(), "mode": mode,
                          "updated": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")

    def mode(self, key: str) -> str | None:
        return self.data.get(key, {}).get("mode")


# ---------------------------------------------------------------- logging
def log_call(stage: str, *, shot: str | None, model: str, status: str, params: dict | None = None,
             seed: int | None = None, latency_s: float | None = None, input_hash: str | None = None,
             output: Path | None = None, model_call: bool = True, cost_usd: float | None = None,
             error: str | None = None, extra: dict | None = None) -> None:
    """Append one line to runs.jsonl. Every model call (and every cache hit / placeholder) is logged."""
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": RUN_ID,
        "stage": stage,
        "shot": shot,
        "model": model,
        "model_call": model_call,
        "status": status,
        "params": params or {},
        "seed": seed,
        "latency_s": round(latency_s, 3) if latency_s is not None else None,
        "cost_usd_list_equiv": cost_usd,
        "input_hash": input_hash,
        "output": output.relative_to(ROOT).as_posix() if output else None,
    }
    if error:
        rec["error"] = error[:500]
    if extra:
        rec.update(extra)
    with open(RUNS, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tag = "CALL" if model_call and status == "ok" else status.upper()
    print(f"  [{stage}] {shot or '-':4} {tag:11} {model} {'' if latency_s is None else f'{latency_s:.1f}s'}")


# ---------------------------------------------------------------- retries
class RetryableError(Exception):
    pass


def with_retries(attempts: int = 3, base_delay: float = 4.0):
    """Retry on RetryableError (429, 5xx, timeouts) with exponential backoff."""

    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last = None
            for i in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except RetryableError as e:
                    last = e
                    if i == attempts:
                        break
                    delay = base_delay * (2 ** (i - 1))
                    print(f"    retry {i}/{attempts - 1} in {delay:.0f}s: {e}")
                    time.sleep(delay)
            raise last

        return wrapper

    return deco


def raise_for_http(resp) -> None:
    if resp.status_code == 429 and ("per day" in resp.text.lower() or "daily free allocation" in resp.text.lower()):
        # Daily free-tier quota: retrying only burns time (and may count). Fail fast with the real reason.
        raise RuntimeError(f"HTTP 429 DAILY QUOTA exhausted for this model; switch model or wait. {resp.text[:400]}")
    if resp.status_code == 429 or resp.status_code >= 500:
        raise RetryableError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")


# ---------------------------------------------------------------- ffmpeg / audio
def ffmpeg_exe() -> str:
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError as e:
        raise SystemExit("ffmpeg not found. Install it, or `pip install imageio-ffmpeg`.") from e


def run_ffmpeg(args: list[str], cwd: Path | None = None, capture: bool = False) -> str:
    cmd = [ffmpeg_exe(), "-hide_banner", "-y", "-loglevel", "info" if capture else "error"] + args
    res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if res.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({res.returncode}):\n{' '.join(cmd)}\n{res.stderr[-2000:]}")
    return res.stderr


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def media_duration(path: Path) -> float:
    if path.suffix.lower() == ".wav":
        return wav_duration(path)
    err = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True,
                         encoding="utf-8", errors="replace").stderr
    for line in err.splitlines():
        line = line.strip()
        if line.startswith("Duration:"):
            hms = line.split(",")[0].split()[1]
            h, m, s = hms.split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"could not read duration of {path}")


def env(name: str) -> str | None:
    v = os.environ.get(name)
    return v.strip() if v and v.strip() else None
