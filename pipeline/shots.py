"""Stage: moving shots. Wan 2.2 clip if one exists in outputs/clips/<id>.mp4, else a Ken Burns move over the keyframe.

Each shot is rendered once per aspect ratio, cropped from the centre of the keyframe, at the exact length
the timeline gives it. Cached by (source file hash, motion, duration, size).
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

from . import keyframes as kf_stage
from . import narration as narr_stage
from . import timeline
from .common import OUT, Cache, file_hash, load_storyboard, log_call, run_ffmpeg, select_shots, stable_hash

STAGE = "shots"
DIR = OUT / "shots"
CLIPS = OUT / "clips"  # drop Wan 2.2 outputs here
ZMAX = 0.15

EASE = "(1-cos(PI*on/{D}))/2"


def zoompan_expr(motion: str, frames: int) -> tuple[str, str, str]:
    D = max(frames - 1, 1)
    p = EASE.format(D=D)
    cx, cy = "iw/2-(iw/zoom/2)", "ih/2-(ih/zoom/2)"
    if motion == "push_in":
        return f"1+{ZMAX}*{p}", cx, cy
    if motion == "pull_out":
        return f"1+{ZMAX}-{ZMAX}*{p}", cx, cy
    if motion == "pan_left":
        return f"1+{ZMAX}", f"(iw-iw/zoom)*(1-{p})", cy
    if motion == "pan_right":
        return f"1+{ZMAX}", f"(iw-iw/zoom)*{p}", cy
    if motion == "tilt_up":
        return f"1+{ZMAX}", cx, f"(ih-ih/zoom)*(1-{p})"
    if motion == "tilt_down":
        return f"1+{ZMAX}", cx, f"(ih-ih/zoom)*{p}"
    return f"1.03+0.03*{p}", cx, cy  # static: a slow breath so the frame never looks frozen


def crop_for(w: int, h: int) -> str:
    """Centre crop to the output aspect before any scaling."""
    if w / h >= 1:
        return f"crop=iw:'min(ih,iw*{h}/{w})'"
    return f"crop='min(iw,ih*{w}/{h})':ih"


def render_kenburns(src: Path, dst: Path, motion: str, frames: int, w: int, h: int, fps: int) -> None:
    z, x, y = zoompan_expr(motion, frames)
    sw, sh = int(w * 1.5) // 2 * 2, int(h * 1.5) // 2 * 2
    vf = (f"{crop_for(w, h)},scale={sw}:{sh}:flags=lanczos,"
          f"zoompan=z='{z}':x='{x}':y='{y}':d={frames}:s={w}x{h}:fps={fps},"
          f"format=yuv420p,setsar=1")
    run_ffmpeg(["-i", str(src), "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(dst)])


def render_clip(src: Path, dst: Path, frames: int, w: int, h: int, fps: int) -> None:
    """Use a generated video clip: trim its weak first 0.3 s, crop, scale, hold the last frame if short."""
    vf = (f"trim=start=0.3,setpts=PTS-STARTPTS,fps={fps},{crop_for(w, h)},scale={w}:{h}:flags=lanczos,"
          f"tpad=stop_mode=clone:stop_duration=30,format=yuv420p,setsar=1")
    run_ffmpeg(["-i", str(src), "-vf", vf, "-frames:v", str(frames), "-r", str(fps),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-an", str(dst)])


def aspect_sizes(sb: dict, draft: bool) -> dict[str, tuple[int, int]]:
    out = {}
    for name, a in sb["render"]["aspects"].items():
        w, h = a["width"], a["height"]
        if draft:
            w, h = w // 3 // 2 * 2, h // 3 // 2 * 2
        out[name] = (w, h)
    return out


def run(only: list[str] | None = None, draft: bool = False, offline: bool = False) -> dict[str, dict[str, Path]]:
    sb = load_storyboard()
    narr = narr_stage.run(None, offline, quiet=True)  # cache hits; needed for timing
    keys = kf_stage.run(None, offline, quiet=True)
    tl = {x["id"]: x for x in timeline.build(sb, narr)}
    fps = sb["render"]["fps"]
    cache = Cache(STAGE)
    sizes = aspect_sizes(sb, draft)
    print(f"[{STAGE}] aspects={list(sizes)} draft={draft}")
    out: dict[str, dict[str, Path]] = {a: {} for a in sizes}
    for shot in select_shots(sb, only):
        sid = shot["id"]
        clip = CLIPS / f"{sid}.mp4"
        source = clip if clip.exists() else keys[sid]
        kind = "clip" if clip.exists() else "kenburns"
        for aspect, (w, h) in sizes.items():
            frames = tl[sid]["frames"]
            inputs = {"src": file_hash(source), "kind": kind, "motion": shot["motion"], "frames": frames,
                      "w": w, "h": h, "fps": fps, "zmax": ZMAX}
            h_ = stable_hash(inputs)
            key = f"{aspect}/{sid}"
            dst = DIR / aspect / f"{sid}.mp4"
            hit = cache.hit(key, h_)
            if hit:
                out[aspect][sid] = hit
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            t0 = time.perf_counter()
            if kind == "clip":
                render_clip(source, dst, frames, w, h, fps)
            else:
                render_kenburns(source, dst, shot["motion"], frames, w, h, fps)
            log_call(STAGE, shot=sid, model=f"ffmpeg-{kind}", status="rendered", model_call=False,
                     params={"aspect": aspect, "motion": shot["motion"], "frames": frames, "size": f"{w}x{h}"},
                     input_hash=h_, output=dst, latency_s=time.perf_counter() - t0)
            cache.put(key, h_, dst, "draft" if draft else "final")
            out[aspect][sid] = dst
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", nargs="*")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    run(a.shot, a.draft, a.offline)
