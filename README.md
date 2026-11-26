# የጉለሌው ሰካራም: The Drunkard of Gulele

An Amharic short film adapted from **Temesgen Gebre's *Yegulelew Sekaram* (1948)**, often called the first Amharic short story. A code pipeline makes the film from one contract file: keyframes, moving shots, narration, music and the final edit, in 16:9 and 9:16.

| Cut | Contract | Length | Output |
|---|---|---|---|
| Submission | [`storyboard.json`](storyboard.json), 9 passages | 88 s | `outputs/final/heritage_short_{9x16,16x9}.mp4` |
| Family cut | [`storyboard_family.json`](storyboard_family.json), 20 passages | 3:08 | `outputs/final/family_cut_{9x16,16x9}.mp4` |

**Narration:** excerpts of the Ethio Atronos Amharic audiobook, used with the narrator's permission (see [ETHICS.md](ETHICS.md)). The full recording is **not** in this repo: only the cut excerpts in `outputs/narration/` are committed, and a clean clone runs from them.

## Run it

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows   (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
cp .env.example .env              # add GEMINI_API_KEY, CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN
python film.py                    # == make film
```

Outputs go to `outputs/final/`: `heritage_short_16x9.mp4`, `heritage_short_9x16.mp4`, `radio_cut.mp4`, plus SRT subtitle files.

**No keys?** The generated stems are committed with their cache manifests (`outputs/cache/*.json`). On a clean clone, `python film.py` finds a cache hit for every model call and only re-runs the FFmpeg assembly. To test the plumbing with no generated assets at all, run `python film.py --offline --draft`. It uses silent narration and placeholder cards.

| Command | What it does |
|---|---|
| `python film.py` | Full pipeline, both aspect ratios |
| `python film.py --radio` | Narration and music on a black screen (audience test 1) |
| `python film.py --draft` | One-third resolution, fast |
| `python film.py --stage keyframes --shot s04` | One stage, one shot |
| `python film.py --validate` | JSON Schema check only |
| `python film.py --storyboard storyboard_family.json` | The 3-minute family cut |
| `python -m pipeline.transcribe <audio>` | Transcribe a long licensed recording in 4-minute chunks |
| `python -m pipeline.align <audio> [--shot s05]` | Find each shot's sentence in the recording and write its `audio_source` cut points |
| `python -m pipeline.review [storyboard_family.json]` | Local HTML page: each shot's picture, audio cut and text, for checking by ear |
| `python -m pipeline.smoke` | Calls each provider once and lists the TTS models your key can see |
| `python -m pipeline.costs` | Per-stage latency, calls, cache hits and cost table built from `runs.jsonl` |

## How it works

```
storyboard.json ──validate (schema/)──┬─ narration  Gemini TTS, one WAV per shot ───────┐
                                      ├─ keyframes  reference sheets → FLUX per shot ──┐ │
                                      │             shots  Wan 2.2 clip or Ken Burns ◄─┘ │
                                      ├─ music      ACE-Step (Kaggle) or placeholder pad │
                                      └─ assemble   timeline from voice lengths ◄────────┘
                                                    duck · loudnorm · subtitles · end card · 16:9 + 9:16
```

Each stage hashes its inputs and skips work whose hash has not changed. If you edit one shot's `image_prompt`, the pipeline makes **one** new FLUX call, re-renders that shot's two clips and re-assembles. Every call, cache hit and render is written as one line in [`runs.jsonl`](runs.jsonl). See [ARCHITECTURE.md](ARCHITECTURE.md).

## Stack and cost

| Stage | Model | Where | Cost |
|---|---|---|---|
| Narration | Ethio Atronos audiobook excerpts (licensed); Gemini TTS in drafts | local cut / Gemini API free tier | $0 |
| Cut points | gemini-3.5-transcribe + loudness-envelope pauses | Gemini API free tier | $0 |
| Keyframes | FLUX.1 schnell, cinematic style block | Cloudflare Workers AI free allowance | $0 |
| Moving shots | Ken Burns in FFmpeg; Wan 2.2 TI2V-5B optional | local / Kaggle T4 | $0 |
| Music | ACE-Step 1.5 | Kaggle T4 | $0 |
| Assembly | FFmpeg (bundled via `imageio-ffmpeg`) | local | $0 |

Measured latency and list-price equivalents are in [COSTS.md](COSTS.md).

## Showcase site (Vercel)

`python -m pipeline.site` builds a static site in `site/` from the storyboards, `runs.jsonl` and the rendered films. It includes small web versions of the films (H.264, CRF 28, about 29 MB in total), every shot with its Amharic and English text, live numbers from the log, the failure log highlights, and credits. The GitHub link fills itself from the git remote.

To deploy, push to GitHub, then in Vercel choose **Add New → Project → import the repo → Deploy**. `vercel.json` already sets `outputDirectory: site` with no build step, so no settings need changing. Re-run `python -m pipeline.site`, commit and push to update the site.

## Documents

[DESIGN.md](DESIGN.md) audience, intent and user tests · [ARCHITECTURE.md](ARCHITECTURE.md) · [EXPERIMENTS.md](EXPERIMENTS.md) · [FAILURES.md](FAILURES.md) · [COSTS.md](COSTS.md) · [ETHICS.md](ETHICS.md)
