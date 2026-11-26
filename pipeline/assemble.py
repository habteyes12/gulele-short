"""Stage: assembly. Deterministic (FFmpeg only, no model calls), so it always reruns from the cached stems.

Audio: narration placed at each shot's voice_start, music under it, sidechain ducking, two-pass loudnorm to -14 LUFS / -1 dBTP.
Picture: shot clips + title overlay + burned-in English subtitles + AI end card, once per aspect ratio.
Also writes the radio cut (black screen + mix) used for the first audience test.
"""
from __future__ import annotations

import argparse
import json
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import music as music_stage
from . import narration as narr_stage
from . import shots as shots_stage
from . import timeline
from .common import OUT, load_storyboard, log_call, run_ffmpeg

STAGE = "assemble"
DIR = OUT / "final"
SR = 48000

ETHIOPIC_FONTS = ["ebrimabd.ttf", "ebrima.ttf", "nyala.ttf", "/usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf",
                  "/usr/share/fonts/opentype/noto/NotoSansEthiopic-Bold.ttf", "NotoSansEthiopic-Regular.ttf"]
LATIN_FONTS = ["arial.ttf", "segoeui.ttf", "DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def font(candidates: list[str], size: int):
    for c in candidates:
        try:
            return ImageFont.truetype(c, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


# ---------------------------------------------------------------- subtitles
def srt_time(t: float) -> str:
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def write_srt(sb: dict, tl: list[dict], wrap: int, path: Path) -> None:
    """One cue per shot, split into chunks of at most two lines; chunks share the voice time by length."""
    by_id = {s["id"]: s for s in sb["shots"]}
    cues = []
    for x in tl:
        lines = textwrap.wrap(by_id[x["id"]]["subtitle"], wrap)
        chunks = ["\n".join(lines[i:i + 2]) for i in range(0, len(lines), 2)]
        total_chars = sum(len(c) for c in chunks)
        t = x["voice_start"]
        span = max(x["voice_duration"], 1.5)
        for c in chunks:
            d = span * len(c) / total_chars
            cues.append((t, t + d, c))
            t += d
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, text) in enumerate(cues, 1):
            f.write(f"{i}\n{srt_time(a)} --> {srt_time(b)}\n{text}\n\n")


# ---------------------------------------------------------------- cards
def title_png(sb: dict, w: int, h: int, path: Path) -> None:
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = min(w, h)
    cy = int(h * 0.30)
    big, mid, small = font(ETHIOPIC_FONTS, int(s * 0.11)), font(LATIN_FONTS, int(s * 0.045)), font(LATIN_FONTS, int(s * 0.028))
    for text, f, y in [(sb["title"]["native"], big, cy), (sb["title"]["english"], mid, cy + int(s * 0.10)),
                       (sb["title"].get("credit", ""), small, cy + int(s * 0.16))]:
        d.text((w // 2 + 3, y + 3), text, font=f, fill=(0, 0, 0, 170), anchor="mm")
        d.text((w // 2, y), text, font=f, fill=(250, 240, 220, 255), anchor="mm")
    img.save(path)


def end_card_png(sb: dict, w: int, h: int, path: Path) -> None:
    img = Image.new("RGB", (w, h), (24, 20, 18))
    d = ImageDraw.Draw(img)
    s = min(w, h)
    lines = sb["end_card"]["lines"]
    sizes = [int(s * 0.09)] + [int(s * 0.04)] + [int(s * 0.032)] * (len(lines) - 2)
    y = h // 2 - int(s * 0.18)
    for i, (text, size) in enumerate(zip(lines, sizes)):
        f = font(ETHIOPIC_FONTS if i == 0 else LATIN_FONTS, size)
        for part in textwrap.wrap(text, 34 if w < h else 70):
            d.text((w // 2, y), part, font=f, fill=(245, 232, 205) if i < 2 else (200, 190, 175), anchor="mm")
            y += int(size * 1.45)
        y += int(s * 0.015)
    img.save(path)


# ---------------------------------------------------------------- audio
def parse_loudnorm(stderr: str) -> dict:
    blob = stderr[stderr.rfind("{"): stderr.rfind("}") + 1]
    return json.loads(blob)


def build_mix(sb: dict, tl: list[dict], narr: dict[str, Path], score: Path, total_s: float) -> tuple[Path, dict]:
    DIR.mkdir(parents=True, exist_ok=True)
    m = sb["music"]
    duck = {"threshold": 0.02, "ratio": 6, "attack_ms": 300, "release_ms": 1500, **m.get("duck", {})}
    # 1. narration stem: each line at its voice_start, levelled to -16 LUFS
    args, parts = [], []
    for i, x in enumerate(tl):
        args += ["-i", str(narr[x["id"]])]
        ms = int(x["voice_start"] * 1000)
        parts.append(f"[{i}]aresample={SR},pan=stereo|c0=c0|c1=c0,adelay={ms}|{ms}[n{i}]")
    fc = ";".join(parts) + ";" + "".join(f"[n{i}]" for i in range(len(tl))) + \
        f"amix=inputs={len(tl)}:normalize=0,apad=whole_dur={total_s},atrim=0:{total_s},loudnorm=I=-16:TP=-2:LRA=11[out]"
    tag = sb.get("output_name", "heritage_short")
    narr_stem = DIR / f"stem_narration_{tag}.wav"
    run_ffmpeg(args + ["-filter_complex", fc, "-map", "[out]", "-ar", str(SR), str(narr_stem)])

    # 2. music stem: levelled, then offset by volume_db, faded out under the end card
    music_stem = DIR / f"stem_music_{tag}.wav"
    fade_st = max(total_s - 4, 0)
    run_ffmpeg(["-stream_loop", "-1", "-i", str(score), "-filter_complex",
                f"[0]atrim=0:{total_s},aresample={SR},loudnorm=I=-20:TP=-2:LRA=11,volume={m.get('volume_db', -6)}dB,"
                f"afade=t=in:d=1.0,afade=t=out:st={fade_st}:d=4[out]", "-map", "[out]", str(music_stem)])

    # 3. duck music under voice, sum
    premix = DIR / f"premix_{tag}.wav"
    sc = (f"sidechaincompress=threshold={duck['threshold']}:ratio={duck['ratio']}:"
          f"attack={duck['attack_ms']}:release={duck['release_ms']}")
    run_ffmpeg(["-i", str(music_stem), "-i", str(narr_stem), "-filter_complex",
                f"[1]asplit=2[sc][v];[0][sc]{sc}[ducked];[ducked][v]amix=inputs=2:normalize=0[out]",
                "-map", "[out]", str(premix)])

    # 4. two-pass loudness normalisation to platform target
    t0 = time.perf_counter()
    first = parse_loudnorm(run_ffmpeg(["-i", str(premix), "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                                       "-f", "null", "-"], capture=True))
    mix = DIR / f"mix_{tag}.wav"
    second = parse_loudnorm(run_ffmpeg([
        "-i", str(premix), "-af",
        f"loudnorm=I=-14:TP=-1:LRA=11:measured_I={first['input_i']}:measured_TP={first['input_tp']}:"
        f"measured_LRA={first['input_lra']}:measured_thresh={first['input_thresh']}:offset={first['target_offset']}:"
        f"linear=true:print_format=json", "-ar", str(SR), str(mix)], capture=True))
    loud = {"before_I": first["input_i"], "before_TP": first["input_tp"], "after_I": second["output_i"],
            "after_TP": second["output_tp"], "normalization_type": second.get("normalization_type")}
    log_call(STAGE, shot=None, model="ffmpeg-loudnorm-2pass", status="rendered", model_call=False, output=mix,
             latency_s=time.perf_counter() - t0, params={"target_I": -14, "target_TP": -1, "duck": duck}, extra=loud)
    return mix, loud


# ---------------------------------------------------------------- picture
def encode_card(png: Path, dst: Path, seconds: float, w: int, h: int, fps: int) -> None:
    frames = int(round(seconds * fps))
    run_ffmpeg(["-loop", "1", "-i", str(png), "-vf", f"scale={w}:{h},fade=t=in:d=0.6,format=yuv420p,setsar=1",
                "-frames:v", str(frames), "-r", str(fps), "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(dst)])


def build_aspect(sb: dict, aspect: str, w: int, h: int, clips: dict[str, Path], tl: list[dict], mix: Path,
                 total_s: float, draft: bool) -> Path:
    fps = sb["render"]["fps"]
    a = sb["render"]["aspects"][aspect]
    name = sb.get("output_name", "heritage_short")
    work = DIR / f"work_{name}_{aspect}"
    work.mkdir(parents=True, exist_ok=True)
    end_png, title = work / "end_card.png", work / "title.png"
    end_card_png(sb, w, h, end_png)
    title_png(sb, w, h, title)
    end_mp4 = work / "end_card.mp4"
    encode_card(end_png, end_mp4, sb["end_card"]["duration_s"], w, h, fps)
    concat = work / "concat.txt"
    concat.write_text("".join(f"file '{clips[x['id']].as_posix()}'\n" for x in tl) + f"file '{end_mp4.as_posix()}'\n",
                      encoding="utf-8")
    srt = DIR / (f"subtitles_{aspect}.srt" if name == "heritage_short" else f"{name}_subtitles_{aspect}.srt")
    write_srt(sb, tl, a["sub_wrap_chars"], srt)
    scale = 1 / 3 if draft else 1
    style = (f"FontName=Arial,FontSize={a['sub_font_size']},MarginV={int(a['sub_margin_v'])},Outline=1.6,Shadow=0,"
             f"BorderStyle=1,PrimaryColour=&H00F0F5FA,OutlineColour=&H00101010")
    out = DIR / f"{name}_{aspect}{'_draft' if draft else ''}.mp4"
    fc = ("[1]format=rgba,fade=t=in:st=0.6:d=0.8:alpha=1,fade=t=out:st=4.2:d=0.8:alpha=1[t];"
          f"[0][t]overlay=0:0:eof_action=pass,subtitles={srt.name}:force_style='{style}'[v]")
    t0 = time.perf_counter()
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(concat), "-loop", "1", "-t", "5", "-i", str(title),
                "-i", str(mix), "-filter_complex", fc, "-map", "[v]", "-map", "2:a", "-t", f"{total_s:.3f}",
                "-r", str(fps), "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(out)], cwd=DIR)
    log_call(STAGE, shot=None, model="ffmpeg-assemble", status="rendered", model_call=False, output=out,
             latency_s=time.perf_counter() - t0, params={"aspect": aspect, "size": f"{w}x{h}", "draft": draft,
                                                          "scale": scale}, extra={"duration_s": round(total_s, 2)})
    return out


def radio_cut(mix: Path, total_s: float, name: str = "heritage_short") -> Path:
    out = DIR / ("radio_cut.mp4" if name == "heritage_short" else f"{name}_radio_cut.mp4")
    run_ffmpeg(["-f", "lavfi", "-i", f"color=c=black:s=640x360:r=24:d={total_s:.3f}", "-i", str(mix),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "30", "-c:a", "aac", "-b:a", "160k",
                "-shortest", "-movflags", "+faststart", str(out)])
    return out


def run(draft: bool = False, offline: bool = False, radio_only: bool = False) -> list[Path]:
    sb = load_storyboard()
    narr = narr_stage.run(None, offline, quiet=True)
    tl = timeline.build(sb, narr)
    film_s = timeline.total(tl)
    total_s = film_s + sb["end_card"]["duration_s"]
    lo, hi = sb["render"]["target_duration_s"]
    print(f"[{STAGE}] film {film_s:.1f}s + end card = {total_s:.1f}s (target {lo}-{hi}s)")
    if not lo <= total_s <= hi:
        print(f"  WARNING: total {total_s:.1f}s is outside the {lo}-{hi}s target. Shorten narration or min durations.")
    (DIR).mkdir(parents=True, exist_ok=True)
    (DIR / f"timeline_{sb.get('output_name', 'heritage_short')}.json").write_text(json.dumps(tl, indent=2), encoding="utf-8")
    score = music_stage.run(offline)
    mix, loud = build_mix(sb, tl, narr, score, total_s)
    print(f"  loudness: {loud['before_I']} -> {loud['after_I']} LUFS, true peak {loud['after_TP']} dBTP")
    outputs = [radio_cut(mix, total_s, sb.get("output_name", "heritage_short"))]
    if radio_only:
        return outputs
    clips = shots_stage.run(None, draft, offline)
    for aspect, (w, h) in shots_stage.aspect_sizes(sb, draft).items():
        outputs.append(build_aspect(sb, aspect, w, h, clips[aspect], tl, mix, total_s, draft))
    for o in outputs:
        print(f"  wrote {o.relative_to(OUT.parent)}")
    return outputs


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--radio", action="store_true")
    a = ap.parse_args()
    run(a.draft, a.offline, a.radio)
