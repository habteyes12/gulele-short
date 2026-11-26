"""Find each shot's narration inside a long licensed recording and write audio_source {start, end} into storyboard.json.

    python -m pipeline.align assets/narration/atronos_full.m4a            # propose + verify all shots
    python -m pipeline.align assets/narration/atronos_full.m4a --shot s05 # one shot

How (the transcription model returns plain text, no timestamps):
1. Locate the shot's target sentence in the chunk transcripts by fuzzy match -> character position.
2. Character position / chunk length x chunk duration -> estimated time.
3. Snap start/end to the narrator's real pauses (silencedetect on the full file).
4. Cut the clip, transcribe it, score similarity to the target; nudge one pause earlier/later and keep the best.
Each verification call is logged to runs.jsonl.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import time
from pathlib import Path

from .common import OUT, ROOT, STORYBOARD, env, log_call, media_duration, run_ffmpeg
from .transcribe import CHUNK_S, MODEL, transcribe_chunk

NONWORD = re.compile(r"[^ሀ-፿\s]")


def norm(t: str) -> str:
    return " ".join(NONWORD.sub(" ", t).split())


def pauses(f: Path, thresh_db: float = -32.0, min_s: float = 0.15) -> list[tuple[float, float]]:
    """Pauses from a 50 ms loudness envelope (speech ~-21 dB, pauses ~-40 dB in this recording).
    Cached next to the transcripts. silencedetect with d=0.3 missed most of the narrator's short breaths."""
    import array, math, subprocess
    from .common import ffmpeg_exe
    cache = OUT / "transcripts" / f.stem / "rms50ms.json"
    if cache.exists():
        db = json.loads(cache.read_text())
    else:
        raw = subprocess.run([ffmpeg_exe(), "-v", "error", "-i", str(f), "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                             capture_output=True).stdout
        x = array.array("h", raw)
        db = [10 * math.log10(sum(v * v for v in x[i:i + 400]) / 400 / 32768 ** 2 + 1e-12) for i in range(0, len(x) - 400, 400)]
        cache.write_text(json.dumps(db))
    out, start = [], None
    for i, v in enumerate(db + [0.0]):
        if v < thresh_db and start is None:
            start = i
        elif v >= thresh_db and start is not None:
            if (i - start) * 0.05 >= min_s:
                out.append((start * 0.05, i * 0.05))
            start = None
    return out


def snap(t: float, gaps: list[tuple[float, float]], side: str, window: float = 2.5) -> float:
    """Nearest pause to t (prefer sentence-length pauses >= 0.35 s). Start -> pause end; end -> pause start."""
    near = [g for g in gaps if abs((g[1] if side == "start" else g[0]) - t) <= window]
    long_ = [g for g in near if g[1] - g[0] >= 0.35]
    pool = long_ or near
    if not pool:
        return t
    g = min(pool, key=lambda g: abs((g[1] if side == "start" else g[0]) - t))
    return g[1] - 0.05 if side == "start" else g[0] + 0.1


def locate(target: str, chunks: list[str]) -> tuple[int, float, float]:
    """Best (chunk index, start fraction, end fraction) for target text using a sliding fuzzy window."""
    tw = norm(target).split()
    best = (0.0, 0, 0.0, 0.0)
    for ci, text in enumerate(chunks):
        words = norm(text).split()
        n = len(tw)
        for i in range(0, max(1, len(words) - n + 1)):
            window = " ".join(words[i:i + n])
            r = difflib.SequenceMatcher(None, " ".join(tw), window).ratio()
            if r > best[0]:
                pre = len(" ".join(words[:i]))
                span = len(window)
                total = len(" ".join(words))
                best = (r, ci, pre / total, (pre + span) / total)
    return best[1], best[2], best[3]


def neighbours(t: float, gaps, side: str) -> list[float]:
    pts = sorted(g[1] - 0.05 for g in gaps) if side == "start" else sorted(g[0] + 0.1 for g in gaps)
    i = min(range(len(pts)), key=lambda k: abs(pts[k] - t))
    return [pts[j] for j in (i - 1, i, i + 1) if 0 <= j < len(pts)]


def verify(f: Path, a: float, b: float, target: str, key: str, sid: str, work: Path) -> tuple[float, str]:
    clip = work / f"{sid}_{a:.2f}_{b:.2f}.mp3"
    if not clip.exists():
        run_ffmpeg(["-ss", f"{a}", "-to", f"{b}", "-i", str(f), "-ac", "1", "-ar", "16000", "-b:a", "48k", str(clip)])
    cache = clip.with_suffix(".txt")
    if cache.exists():
        heard = cache.read_text(encoding="utf-8")
    else:
        t0 = time.perf_counter()
        heard = transcribe_chunk(clip, key)
        cache.write_text(heard, encoding="utf-8")
        log_call("align", shot=sid, model=MODEL, status="ok", latency_s=time.perf_counter() - t0,
                 params={"start": round(a, 2), "end": round(b, 2)})
    return difflib.SequenceMatcher(None, norm(target), norm(heard)).ratio(), heard


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--shot", nargs="*")
    ap.add_argument("--no-verify", action="store_true")
    a = ap.parse_args()
    f = ROOT / a.src
    key = env("GEMINI_API_KEY")
    tdir = OUT / "transcripts" / f.stem
    chunks = [p.read_text(encoding="utf-8") for p in sorted(tdir.glob("chunk*.txt"))]
    total = media_duration(f)
    gaps = pauses(f)
    work = tdir / "align"
    work.mkdir(exist_ok=True)
    sb = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    for shot in sb["shots"]:
        if a.shot and shot["id"] not in a.shot:
            continue
        sid = shot["id"]
        # target = what the narrator should say: the narration text without the "…" ellipsis joins
        parts = [p.strip() for p in shot["narration"].split("…") if p.strip()]
        segs, report = [], []
        for k, part in enumerate(parts):
            ci, fs, fe = locate(part, chunks)
            cdur = min(CHUNK_S, total - ci * CHUNK_S)
            s0 = snap(ci * CHUNK_S + fs * cdur, gaps, "start")
            e0 = snap(ci * CHUNK_S + fe * cdur, gaps, "end")
            best = (s0, e0, 0.0, "")
            if not a.no_verify:
                score, heard = verify(f, s0, e0, part, key, f"{sid}p{k}", work)
                best = (s0, e0, score, heard)
                if score < 0.7:
                    for s_ in neighbours(s0, gaps, "start"):
                        for e_ in neighbours(e0, gaps, "end"):
                            if (s_, e_) == (s0, e0) or e_ - s_ < 1.0 or e_ - s_ > 14:
                                continue
                            sc, hd = verify(f, s_, e_, part, key, f"{sid}p{k}", work)
                            if sc > best[2]:
                                best = (s_, e_, sc, hd)
                            if best[2] >= 0.8:
                                break
                        if best[2] >= 0.8:
                            break
            segs.append([round(best[0], 2), round(best[1], 2)])
            report.append(f"   part{k} {best[0]:7.2f}-{best[1]:7.2f} ({best[1]-best[0]:4.1f}s) match={best[2]:.2f} heard: {norm(best[3])[:110]}")
        shot["audio_source"] = {"file": a.src, "segments": segs}
        print(f"{sid}: {sum(e - s for s, e in segs):4.1f}s")
        print("\n".join(report))
        STORYBOARD.write_text(json.dumps(sb, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
