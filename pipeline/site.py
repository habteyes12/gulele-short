"""Build the static showcase site in site/ from the storyboards, the logs and the rendered films.

    python -m pipeline.site            # -> site/index.html + site/media/*  (deploy site/ on Vercel)

Everything on the page comes from the contract (storyboard*.json) and runs.jsonl, so the site always
matches the films. Web versions of the films are re-encoded small (H.264, CRF 28) so they deploy fast.
"""
from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path

from PIL import Image

from .common import OUT, ROOT, RUNS, file_hash, run_ffmpeg

SITE = ROOT / "site"
MEDIA = SITE / "media"
def _repo_url() -> str:
    """GitHub link for the page: SITE_REPO_URL, else the git remote 'origin', else a placeholder."""
    import os, subprocess
    if os.environ.get("SITE_REPO_URL"):
        return os.environ["SITE_REPO_URL"]
    try:
        u = subprocess.run(["git", "config", "--get", "remote.origin.url"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    except OSError:
        u = ""
    if u.startswith("git@github.com:"):
        u = "https://github.com/" + u.split(":", 1)[1]
    return u.removesuffix(".git") or "https://github.com/"


REPO_URL = _repo_url()

FILMS = [
    ("heritage_short_9x16", "90-second film · vertical", 720, "film-vertical"),
    ("heritage_short_16x9", "90-second film · horizontal", 1280, "film-horizontal"),
    ("family_cut_16x9", "Family cut · full opening", 1280, "family"),
]


def esc(t: str) -> str:
    return html.escape(t, quote=True)


def web_video(name: str, width: int) -> Path | None:
    src = OUT / "final" / f"{name}.mp4"
    if not src.exists():
        print(f"  skip {name}: not rendered")
        return None
    dst = MEDIA / f"{name}.mp4"
    stamp = MEDIA / f"{name}.src"
    h = file_hash(src)
    if dst.exists() and stamp.exists() and stamp.read_text() == h:
        return dst
    scale = f"scale={width}:-2" if "16x9" in name else f"scale=-2:{int(width * 16 / 9) // 2 * 2}"
    run_ffmpeg(["-i", str(src), "-vf", scale, "-c:v", "libx264", "-preset", "slow", "-crf", "28", "-pix_fmt", "yuv420p",
                "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dst)])
    stamp.write_text(h)
    return dst


def poster(name: str, shot_png: Path) -> str:
    dst = MEDIA / f"{name}.jpg"
    im = Image.open(shot_png).convert("RGB")
    im.thumbnail((1280, 1280))
    im.save(dst, quality=82, optimize=True)
    return f"media/{dst.name}"


def thumb(png: Path) -> str:
    dst = MEDIA / "shots" / (png.stem + ".jpg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() or dst.stat().st_mtime < png.stat().st_mtime:
        im = Image.open(png).convert("RGB")
        im.thumbnail((640, 640))
        im.save(dst, quality=80, optimize=True)
    return f"media/shots/{dst.name}"


def stats() -> dict:
    rows = [json.loads(l) for l in RUNS.read_text(encoding="utf-8").splitlines() if l.strip()]
    st = Counter(r["status"] for r in rows)
    calls = [r for r in rows if r.get("model_call") and r["status"] == "ok"]
    kf = [r for r in calls if r["stage"] == "keyframes"]
    loud = [r for r in rows if r["model"] == "ffmpeg-loudnorm-2pass" and r.get("after_I")]
    return {
        "lines": len(rows), "runs": len({r["run_id"] for r in rows}), "calls": len(calls),
        "cache_hits": st["cache_hit"], "images": len(kf),
        "img_latency": round(sum(r["latency_s"] for r in kf) / max(len(kf), 1), 1),
        "lufs": loud[-1]["after_I"] if loud else "-14.0", "tp": loud[-1]["after_TP"] if loud else "-1.0",
    }


def failures() -> list[tuple[str, str]]:
    out = []
    for block in (ROOT / "FAILURES.md").read_text(encoding="utf-8").split("\n## ")[1:]:
        title, _, body = block.partition("\n")
        fix = next((l for l in body.splitlines() if l.startswith("- **Fix") or l.startswith("- **Fix:**")), "")
        fix = fix.replace("- **Fix:**", "").replace("- **Fix**", "").strip()
        if fix and "TODO" not in title:
            out.append((title.split(". ", 1)[-1], fix))
    return out


CSS = """
:root{--bg:#0f0c0a;--bg2:#17120f;--card:#1e1814;--ink:#f3eadc;--muted:#b9ab97;--dim:#7d7061;--gold:#d9a441;--red:#a8322d;--green:#2f6b4f;--line:#2d241e;
--serif:'Noto Serif Ethiopic','Noto Serif',Georgia,serif;--sans:'Inter',system-ui,Segoe UI,Arial,sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.65 var(--sans);-webkit-font-smoothing:antialiased}
img,video{max-width:100%;display:block}a{color:var(--gold)}
.wrap{max-width:1120px;margin:0 auto;padding:0 20px}
.tibeb{height:10px;background:repeating-linear-gradient(90deg,var(--green) 0 14px,var(--gold) 14px 20px,var(--red) 20px 34px,var(--gold) 34px 40px)}
nav{position:sticky;top:0;z-index:10;background:rgba(15,12,10,.86);backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}
nav .wrap{display:flex;align-items:center;gap:22px;height:56px}nav b{font-family:var(--serif);font-size:18px;margin-right:auto}
nav a{color:var(--muted);text-decoration:none;font-size:14px}nav a:hover{color:var(--ink)}
.hero{position:relative;min-height:88vh;display:flex;align-items:flex-end;overflow:hidden}
.hero img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;filter:saturate(.9) brightness(.55)}
.hero:after{content:"";position:absolute;inset:0;background:linear-gradient(180deg,rgba(15,12,10,.1) 30%,var(--bg) 96%)}
.hero .wrap{position:relative;z-index:1;padding-bottom:64px}
.kicker{color:var(--gold);letter-spacing:.18em;text-transform:uppercase;font-size:12px;font-weight:600}
h1{font-family:var(--serif);font-size:clamp(48px,9vw,104px);line-height:1.05;margin:.15em 0 .1em;font-weight:700}
.en{font-size:clamp(20px,3vw,30px);color:var(--muted);font-weight:300;margin:0}
.lede{max-width:620px;color:var(--muted);margin:22px 0 28px}
.btn{display:inline-block;padding:12px 22px;border-radius:999px;background:var(--gold);color:#1b1206;font-weight:700;text-decoration:none;margin:0 10px 10px 0}
.btn.ghost{background:transparent;color:var(--ink);border:1px solid var(--line)}
section{padding:84px 0;border-top:1px solid var(--line);scroll-margin-top:56px}
h2{font-family:var(--serif);font-size:clamp(30px,4.5vw,46px);margin:0 0 10px;font-weight:700}
.sub{color:var(--muted);max-width:720px;margin:0 0 36px}
.films{display:grid;grid-template-columns:minmax(0,340px) minmax(0,1fr);gap:28px;align-items:start}
.film{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden}
.film video{width:100%;background:#000;aspect-ratio:16/9;object-fit:cover}.film.v video{aspect-ratio:9/16}
.film+.film{margin-top:22px}.film p{margin:0;padding:12px 16px;color:var(--muted);font-size:14px}
.film p b{color:var(--ink)}
.story{display:grid;grid-template-columns:1fr 1fr;gap:40px}
.am{font-family:var(--serif);font-size:19px;line-height:1.9;color:var(--ink)}
blockquote{margin:28px 0 0;padding:18px 22px;border-left:3px solid var(--gold);background:var(--bg2);border-radius:0 10px 10px 0}
blockquote .am{font-size:22px}blockquote p{margin:4px 0}
.shots{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:18px}
.shot{background:var(--card);border:1px solid var(--line);border-radius:12px;overflow:hidden;display:flex;flex-direction:column}
.shot img{aspect-ratio:1;object-fit:cover;width:100%}
.shot div{padding:14px 16px 16px}.shot h3{margin:0 0 6px;font-size:15px}.shot .n{color:var(--gold);font-size:12px;font-weight:700;letter-spacing:.1em}
.shot .am{font-size:15px;line-height:1.75;margin:6px 0}.shot .t{color:var(--muted);font-size:13px;margin:0}
.flow{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;counter-reset:s}
.step{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;position:relative}
.step:before{counter-increment:s;content:counter(s);position:absolute;top:14px;right:16px;color:var(--dim);font-weight:700}
.step h3{margin:0 0 6px;font-size:16px}.step p{margin:0;color:var(--muted);font-size:14px}.step code{color:var(--gold);font-size:12.5px}
.nums{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:22px}
.num{background:var(--bg2);border:1px solid var(--line);border-radius:12px;padding:18px}
.num b{display:block;font-family:var(--serif);font-size:34px;color:var(--gold);line-height:1.1}.num span{color:var(--muted);font-size:13px}
.lessons{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.lesson{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px}
.lesson h3{margin:0 0 6px;font-size:16px}.lesson p{margin:0;color:var(--muted);font-size:14px}
.credits{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}.credits h3{margin:0 0 6px;font-size:15px;color:var(--gold)}
.credits p{margin:0;color:var(--muted);font-size:14px}
.ai{display:inline-flex;gap:8px;align-items:center;border:1px solid var(--gold);color:var(--gold);border-radius:999px;padding:6px 14px;font-size:13px;font-weight:600;margin-bottom:18px}
footer{padding:36px 0 50px;color:var(--dim);font-size:13px;border-top:1px solid var(--line)}
@media (max-width:860px){.films,.story,.lessons,.credits{grid-template-columns:1fr}.flow{grid-template-columns:1fr 1fr}.nums{grid-template-columns:1fr 1fr}
nav a.hide{display:none}.films{justify-items:center}.film.v{max-width:360px}}
@media (max-width:420px){.flow{grid-template-columns:1fr}}
"""


def main() -> None:
    MEDIA.mkdir(parents=True, exist_ok=True)
    sb = json.loads((ROOT / "storyboard.json").read_text(encoding="utf-8"))
    fam = json.loads((ROOT / "storyboard_family.json").read_text(encoding="utf-8"))
    kdir = OUT / "keyframes"
    vids = {}
    for name, label, width, key in FILMS:
        v = web_video(name, width)
        if v:
            vids[key] = (f"media/{v.name}", label)
    hero = poster("hero", kdir / "s04.png")
    pv = poster("poster_vertical", kdir / "s24.png" if (kdir / "s24.png").exists() else kdir / "s01.png")
    ph = poster("poster_family", kdir / "s02.png")
    p169 = poster("poster_horizontal", kdir / "s12.png")
    s = stats()
    tl90 = json.loads((OUT / "final" / "timeline_heritage_short.json").read_text())
    tlf = json.loads((OUT / "final" / "timeline_family_cut.json").read_text())
    dur90 = sum(x["duration"] for x in tl90) + sb["end_card"]["duration_s"]
    durf = sum(x["duration"] for x in tlf) + fam["end_card"]["duration_s"]

    def film_card(key, poster_src, cls=""):
        if key not in vids:
            return ""
        src, label = vids[key]
        return (f'<figure class="film {cls}"><video controls playsinline preload="none" poster="{poster_src}" src="{src}"></video>'
                f'<p><b>{esc(label)}</b></p></figure>')

    shots_html = []
    for i, sh in enumerate(fam["shots"], 1):
        png = kdir / f"{sh['id']}.png"
        if not png.exists():
            continue
        shots_html.append(
            f'<article class="shot"><img loading="lazy" src="{thumb(png)}" alt="{esc(sh["beat"])}">'
            f'<div><span class="n">SHOT {i:02}</span><h3>{esc(sh["beat"])}</h3>'
            f'<p class="am" lang="am">{esc(sh["narration"])}</p><p class="t">{esc(sh["subtitle"])}</p></div></article>')
    lessons = "".join(f'<div class="lesson"><h3>{esc(t)}</h3><p>{esc(f[:260])}</p></div>' for t, f in failures()[:8])
    ending = fam["shots"][-1]

    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(sb['title']['english'])}: an AI heritage short</title>
<meta name="description" content="A short film of Temesgen Gebre's 1948 Amharic story Yegulelew Sekaram, made with an AI pipeline from one storyboard file.">
<meta property="og:title" content="{esc(sb['title']['native'])}: {esc(sb['title']['english'])}">
<meta property="og:description" content="The first Amharic short story, retold as an AI-made short film.">
<meta property="og:image" content="{hero}"><meta name="theme-color" content="#0f0c0a">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Noto+Serif+Ethiopic:wght@400;700&display=swap" rel="stylesheet">
<style>{CSS}</style></head><body>
<nav><div class="wrap"><b lang="am">{esc(sb['title']['native'])}</b><a href="#film">Film</a><a href="#story" class="hide">Story</a>
<a href="#shots">Shots</a><a href="#making">Making</a><a href="#credits" class="hide">Credits</a></div></nav>
<div class="tibeb"></div>
<header class="hero"><img src="{hero}" alt="Tebeje under the eucalyptus by moonlight">
<div class="wrap"><div class="kicker">After Temesgen Gebre · 1948 · the first Amharic short story</div>
<h1 lang="am">{esc(sb['title']['native'])}</h1><p class="en">{esc(sb['title']['english'])}</p>
<p class="lede">Tebeje, Gulele's famous chicken trader and drunkard, builds a house of his own and swears off drink for its honour. Again and again.
Narrated in Amharic, with English subtitles, and made with AI from one storyboard file.</p>
<a class="btn" href="#film">Watch the film</a><a class="btn ghost" href="{REPO_URL}">View the pipeline</a></div></header>

<section id="film"><div class="wrap"><div class="ai">● Made with AI: AI-generated images, real narration</div>
<h2>The film</h2><p class="sub">A {dur90:.0f}-second cut for phones and feeds, and a {durf/60:.0f}-minute family cut that opens with the story's first four passages, word for word.</p>
<div class="films">{film_card('film-vertical', pv, 'v')}<div>{film_card('film-horizontal', p169)}{film_card('family', ph)}</div></div></div></section>

<section id="story"><div class="wrap story"><div><h2>The story</h2>
<p class="sub">In 1948 (1941 E.C.) Temesgen Gebre published <i>Yegulelew Sekaram</i>, which Asfaw Damte and Zerihun Asfaw credit as the first Amharic short story.
It is funny and merciless. Gulele laughs at Tebeje even when he dives into a flood to save a drowning maid and pulls out a pig. After nearly two sober years
he dreams the price of one more drink, and wakes to ask his housekeeper how many legs he has.</p></div>
<div><p class="am" lang="am">{esc(fam['shots'][0]['narration'])}</p>
<blockquote><p class="am" lang="am">{esc(ending['narration'])}</p><p class="t" style="color:var(--muted)">{esc(ending['subtitle'])}</p></blockquote></div></div></section>

<section id="shots"><div class="wrap"><h2>Every shot</h2><p class="sub">Each image was generated from the storyboard with the same character description and style block,
so Tebeje stays the same man from the first shot to the last. The Amharic is the narrator's own reading of the original text.</p>
<div class="shots">{''.join(shots_html)}</div></div></section>

<section id="making"><div class="wrap"><h2>How it was made</h2><p class="sub">One JSON file, <code>storyboard.json</code>, is the contract between five stages.
Every stage caches by a hash of its inputs, so changing one line regenerates one shot. A clean clone rebuilds the film with zero model calls.</p>
<div class="flow">
<div class="step"><h3>Storyboard</h3><p>Shots, prompts, narration, subtitles and cut points, validated by a JSON Schema. <code>storyboard.json</code></p></div>
<div class="step"><h3>Narration</h3><p>Licensed audiobook excerpts located by transcription and snapped to the narrator's pauses. <code>align.py</code></p></div>
<div class="step"><h3>Keyframes</h3><p>FLUX.1 schnell on Cloudflare Workers AI, with a cinematic style block and a fixed character. <code>keyframes.py</code></p></div>
<div class="step"><h3>Motion</h3><p>Eased Ken Burns moves per shot and aspect ratio. Wan 2.2 clips drop in when available. <code>shots.py</code></p></div>
<div class="step"><h3>Assembly</h3><p>Cut to the voice, ducked score, two-pass loudness, burned-in subtitles, AI end card. <code>assemble.py</code></p></div></div>
<div class="nums"><div class="num"><b>{s['calls']}</b><span>logged model calls in {s['runs']} runs</span></div>
<div class="num"><b>{s['cache_hits']}</b><span>cache hits: work not redone</span></div>
<div class="num"><b>{s['img_latency']} s</b><span>average per keyframe ({s['images']} images)</span></div>
<div class="num"><b>{s['lufs']}</b><span>LUFS, true peak {s['tp']} dBTP</span></div></div></div></section>

<section id="lessons"><div class="wrap"><h2>What broke, and what fixed it</h2><p class="sub">Free tiers, quotas and models that ignore instructions. Each is logged in <code>FAILURES.md</code>.</p>
<div class="lessons">{lessons}</div></div></section>

<section id="credits"><div class="wrap"><h2>Credits and consent</h2><div class="credits">
<div><h3>Story</h3><p>Temesgen Gebre, <i>Yegulelew Sekaram</i> (Addis Ababa, 1948). Text as published by Andemta with the kind permission of the author's family.</p></div>
<div><h3>Narration</h3><p>Ethio Atronos Amharic audiobook, excerpts used with the narrator's permission. No voice cloning: real recordings, cut in time.</p></div>
<div><h3>AI disclosure</h3><p>Images: FLUX.1 schnell. Transcription: Gemini. Assembly: FFmpeg. Characters are fictional; no real person is depicted.</p></div>
</div></div></section>
<div class="tibeb"></div>
<footer><div class="wrap">Built from <a href="{REPO_URL}">storyboard.json</a> by <code>python -m pipeline.site</code> · Made with AI · Non-commercial student work</div></footer>
</body></html>"""
    (SITE / "index.html").write_text(page, encoding="utf-8")
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file()) / 1e6
    print(f"site/index.html written, {len(shots_html)} shots, {len(vids)} films, {size:.1f} MB total")


if __name__ == "__main__":
    main()
