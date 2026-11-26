"""The edit is cut to the voice: each shot lasts as long as its narration line plus a lead and tail, never less than min_duration_s."""
from __future__ import annotations

from pathlib import Path

from .common import wav_duration


def build(sb: dict, narration: dict[str, Path]) -> list[dict]:
    fps = sb["render"]["fps"]
    lead = sb["render"].get("narration_lead_s", 0.4)
    tail = sb["render"].get("narration_tail_s", 0.7)
    t = 0.0
    out = []
    for shot in sb["shots"]:
        sid = shot["id"]
        voice = wav_duration(narration[sid])
        dur = max(shot["min_duration_s"], lead + voice + tail)
        frames = int(round(dur * fps))
        dur = frames / fps
        out.append({"id": sid, "start": round(t, 3), "duration": dur, "frames": frames,
                    "voice_start": round(t + lead, 3), "voice_duration": round(voice, 3)})
        t += dur
    return out


def total(tl: list[dict]) -> float:
    return sum(x["duration"] for x in tl)
