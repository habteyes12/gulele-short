"""Stage: music. Uses the ACE-Step track named in storyboard.music.chosen; falls back to a quiet generated pad.

ACE-Step runs on a Kaggle/Colab GPU (see notebooks/acestep_kaggle.py). Put the candidates in
outputs/music/candidates/, listen to them under the narration, then set music.chosen to the winner.
"""
from __future__ import annotations

import argparse
import time

from .common import OUT, ROOT, Cache, file_hash, load_storyboard, log_call, run_ffmpeg, stable_hash

STAGE = "music"
DIR = OUT / "music"


def run(offline: bool = False):
    sb = load_storyboard()
    m = sb["music"]
    cache = Cache(STAGE)
    DIR.mkdir(parents=True, exist_ok=True)
    dst = DIR / f"score_{int(m.get('duration_s', 95))}s.wav"
    chosen = ROOT / m["chosen"] if m.get("chosen") else None
    if chosen and not chosen.exists():
        raise SystemExit(f"music.chosen points at {m['chosen']} but the file does not exist")
    duration = m.get("duration_s", 95)
    inputs = {"src": file_hash(chosen) if chosen else "placeholder-pad-v1", "duration": duration}
    h = stable_hash(inputs)
    hit = cache.hit(dst.stem, h)
    if hit:
        log_call(STAGE, shot=None, model=m.get("model", "?"), status="cache_hit", model_call=False, input_hash=h, output=hit)
        return hit
    t0 = time.perf_counter()
    if chosen:
        # The ACE-Step call itself happened on the GPU and is logged by the notebook; here we only conform the file.
        run_ffmpeg(["-i", str(chosen), "-ac", "2", "-ar", "48000", "-t", str(duration), str(dst)])
        log_call(STAGE, shot=None, model=m.get("model", "ACE-Step"), status="conformed", model_call=False,
                 input_hash=h, output=dst, latency_s=time.perf_counter() - t0, extra={"source": m["chosen"]})
        mode = "real"
    else:
        # Placeholder: soft C-minor drone with slow tremolo plus filtered brown noise. Temp track only.
        expr = ("0.10*sin(2*PI*130.81*t)*(0.7+0.3*sin(2*PI*0.11*t))"
                "+0.07*sin(2*PI*155.56*t)*(0.7+0.3*sin(2*PI*0.07*t))"
                "+0.06*sin(2*PI*196.00*t)*(0.7+0.3*sin(2*PI*0.05*t))")
        run_ffmpeg(["-f", "lavfi", "-i", f"aevalsrc='{expr}|{expr}':s=48000:d={duration}",
                    "-f", "lavfi", "-i", f"anoisesrc=color=brown:amplitude=0.02:d={duration}:r=48000",
                    "-filter_complex", "[1]lowpass=f=400,pan=stereo|c0=c0|c1=c0[n];[0][n]amix=inputs=2:normalize=0,"
                    "afade=t=in:d=2,afade=t=out:st=" + str(duration - 4) + ":d=4[a]",
                    "-map", "[a]", str(dst)])
        log_call(STAGE, shot=None, model="placeholder-pad", status="placeholder", model_call=False, input_hash=h,
                 output=dst, latency_s=time.perf_counter() - t0)
        mode = "placeholder"
    cache.put(dst.stem, h, dst, mode)
    return dst


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true")
    run(ap.parse_args().offline)
