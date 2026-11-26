"""Build a local HTML review page: each shot's keyframe, its narration clip and the text it should say.

    python -m pipeline.review                                   # storyboard.json -> outputs/review.html
    python -m pipeline.review storyboard_family.json            # -> outputs/review_family_cut.html

Use it to check by ear that every audio cut starts and ends on the right words.
"""
from __future__ import annotations

import html
import json
import sys

from .common import OUT, ROOT


def main(sb_file: str = "storyboard.json") -> None:
    sb = json.loads((ROOT / sb_file).read_text(encoding="utf-8"))
    name = sb.get("output_name", "heritage_short")
    rows = []
    for s in sb["shots"]:
        src = s.get("audio_source")
        cut = ", ".join(f"{a:.1f}-{b:.1f}s" for a, b in (src.get("segments") or [[src["start"], src["end"]]])) if src else "TTS"
        rows.append(
            f"<tr><td><b>{s['id']}</b><br>{html.escape(s['beat'])}<br><small>{cut}</small></td>"
            f"<td><img src='keyframes/{s['id']}.png' width='170'></td>"
            f"<td><audio controls preload='none' src='narration/{s['id']}.wav'></audio>"
            f"<p class=am>{html.escape(s['narration'])}</p><p>{html.escape(s['subtitle'])}</p>"
            f"<p class=q>Starts and ends on these words? &nbsp; ☐ yes &nbsp; ☐ cut early &nbsp; ☐ cut late</p></td></tr>")
    v916, v169 = f"final/{name}_9x16.mp4", f"final/{name}_16x9.mp4"
    page = f"""<!doctype html><meta charset=utf-8><title>Review {name}</title>
<style>body{{font-family:Segoe UI,Arial;margin:16px;background:#1b1714;color:#eee}}td{{vertical-align:top;padding:8px;border-bottom:1px solid #444}}
.am{{font-family:Nyala,Ebrima;font-size:22px}}.q{{color:#c9b38a;font-size:13px}}</style>
<h2>{html.escape(sb['title']['native'])}: {name}</h2>
<p><video controls width=330 src="{v916}"></video> <video controls width=520 src="{v169}"></video></p>
<table>{''.join(rows)}</table>"""
    out = OUT / ("review.html" if name == "heritage_short" else f"review_{name}.html")
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main(*(sys.argv[1:2]))
