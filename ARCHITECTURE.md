# Architecture

## One contract

`storyboard.json` is the only place creative decisions live. It holds the shots, prompts, seeds, narration, subtitles, motion, music caption and cues, model IDs and render settings. Every stage reads it and nothing else. `schema/storyboard.schema.json` (JSON Schema 2020-12, `additionalProperties: false`) is checked before every run, along with cross-field rules in `pipeline/common.py:load_storyboard`:

- shot IDs are unique
- every character a shot uses is defined
- every music cue points at a real shot

If a check fails, the run stops before any model call. A typo can never spend quota.

## Stages

| Stage | File | Reads | Writes | Model |
|---|---|---|---|---|
| narration | `pipeline/narration.py` | `shots[].audio_source` (licensed recording) or `shots[].narration` + `models.tts` | `outputs/narration/sNN.wav` | cut from the recording; Gemini TTS fallback (batched, 3 lines per call) |
| keyframes | `pipeline/keyframes.py` | `characters`, `style.block`, `shots[].image_prompt/seed`, `models.image` | `outputs/references/*.png`, `outputs/keyframes/sNN.png` | FLUX on Cloudflare Workers AI |
| shots | `pipeline/shots.py` | keyframes, `shots[].motion`, timeline | `outputs/shots/<aspect>/sNN.mp4` | FFmpeg zoompan, or a Wan 2.2 clip in `outputs/clips/` |
| music | `pipeline/music.py` | `music` | `outputs/music/score.wav` | ACE-Step on Kaggle (`notebooks/`), placeholder pad otherwise |
| assemble | `pipeline/assemble.py` | everything above | `outputs/final/*` | FFmpeg only |

`pipeline/timeline.py` cuts the picture to the voice. Each shot lasts `lead + narration length + tail`, and never less than `min_duration_s`. Shot lengths therefore come from the measured TTS audio, not guesses. When a narration line changes, its shot's length changes, and only that shot's clips re-render.

Keyframes are generated in this order:

1. Character reference sheets (`ref_tebeje`, `ref_tiruneshe`).
2. The shot keyframes. Each shot prompt is built the same way: `image_prompt + character descriptions + style block`.

Consistency comes from sending identical text every time, plus a fixed seed per shot. With a FLUX.2 model (`api_style: multipart`, `use_reference: true`), the reference sheet is also sent as an input image.

## Caching

`pipeline/common.py:Cache` keeps one manifest per stage in `outputs/cache/<stage>.json`, mapping each key to `{hash, output, mode}`. The hash is SHA-256 over the exact inputs that affect the output:

| Stage | Hash inputs |
|---|---|
| narration | text, voice, style prompt, model, mode |
| keyframes | full prompt, seed, model, params, reference image hashes, mode |
| shots | source file hash, kind, motion, frame count, size, fps, zoom amount |
| music | chosen file hash, duration |

A step runs only when its hash changed or its output file is missing. `mode` (`real`/`placeholder`) is part of the hash, so offline placeholders are replaced automatically once keys exist. The keyframe hash feeds the shot hash, so a change cascades only along its own shot. Assembly always re-runs: it is deterministic, takes about 30 s and makes no model call.

## Failure handling

- **Retries:** `with_retries` uses exponential backoff, 3 attempts, on HTTP 429/5xx, timeouts and empty responses. Errors in the 4xx range other than 429 fail fast, because retrying a bad request wastes quota.
- **Errors are logged:** every failed call is written to `runs.jsonl` with `status: "error"` and the message, then the run stops. Outputs already made stay cached, so the next run resumes where it stopped.
- **Fallbacks:**
  - no Wan clip: Ken Burns move
  - no ACE-Step track: placeholder pad
  - no API key: `--offline` placeholders

  A narrated, subtitled film can always be produced.
- **Atomic image writes:** an image is downloaded to a `.download` file and converted to PNG before the cache entry is written. A crash cannot leave a half-file marked as done.
- **Secrets:** keys come from environment variables or `.env`, which is git-ignored. `.env.example` lists the names only.

## Logging: `runs.jsonl`

One JSON line per event:

```json
{"ts": "...", "run_id": "...", "stage": "keyframes", "shot": "s04", "model": "@cf/black-forest-labs/flux-1-schnell",
 "model_call": true, "status": "ok", "params": {"steps": 8}, "seed": 104, "latency_s": 2.31,
 "cost_usd_list_equiv": 0.0011, "input_hash": "…", "output": "outputs/keyframes/s04.png", "prompt": "…"}
```

`status` values:

| Value | Meaning |
|---|---|
| `ok` | a real model call succeeded |
| `error` | a call failed |
| `cache_hit` | the step was skipped because its hash matched |
| `placeholder` | an offline stand-in was made |
| `rendered` | an FFmpeg step ran |
| `conformed` | the chosen music file was converted |

GPU notebook calls (Wan, ACE-Step) are written in the same format on Kaggle and appended with `python -m pipeline.ingest`.

## Audio chain

1. Each narration line is placed at its `voice_start` with `adelay`, and the stem is levelled to −16 LUFS.
2. The music is levelled to −20 LUFS, then shifted by `music.volume_db`, with a fade-in and fade-out.
3. `sidechaincompress` ducks the music under the voice. Threshold, ratio, attack and release come from `music.duck`.
4. The two stems are summed, then normalised with two-pass `loudnorm` to −14 LUFS integrated and −1 dBTP. The measured before/after values go to `runs.jsonl`.

## Picture chain

1. Each keyframe is centre-cropped to the output aspect, then upscaled ×1.5.
2. `zoompan` applies a cosine-eased move: push in, pull out, pan, tilt, or a slow "breath" for static shots.
3. The shot clips and an end card are joined with the concat demuxer.
4. A title overlay fades in over shot 1.
5. English subtitles are burned in with libass. Line wrap and font size are set per aspect so they stay inside the 9:16 safe area. The SRT is also exported as a sidecar file.

## Licensed external narration

A shot can set `audio_source: {file, segments: [[start, end], …]}`. The narration stage then cuts those pieces from the recording (with a 50 ms fade-in and 150 ms fade-out, and 0.35 s of silence between pieces) instead of calling TTS. The cache key is the file **path** plus the segments, not the file's contents. The full recording is git-ignored, because permission covers excerpts only. A clean clone therefore hits the cache from the committed excerpts. A cut that was never made fails with a clear message pointing to ETHICS.md.

Cut points come from two tools:

1. `pipeline/transcribe.py` transcribes the recording in 4-minute chunks, with cached text and a model fallback list.
2. `pipeline/align.py` does the matching:
   - fuzzy-matches each shot's sentence in the chunk text and converts its character position into a time estimate;
   - snaps the estimate to pauses from a 50 ms loudness envelope (below −32 dB for at least 0.15 s, preferring pauses of 0.35 s or more);
   - optionally transcribes the clip and tries neighbouring pauses until the text matches;
   - writes the segments back into the storyboard.

`pipeline/review.py` renders a page for the final check by ear.

## Several cuts from one pipeline

`film.py --storyboard <file>` (or `PIPELINE_STORYBOARD`) selects the contract, and `output_name` prefixes the final files. Shots the two cuts share use the same shot IDs and the same inputs, so the second cut reuses their cached narration, keyframes and clips.
