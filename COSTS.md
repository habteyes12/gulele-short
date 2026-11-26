# Costs and measurements

All work runs on free tiers, so the real cost is $0. The binding limits are quotas and GPU time. The table below comes from `runs.jsonl`: run `python -m pipeline.costs` and paste the output here after each major run.

## Free-tier limits found on the day

| Provider | Limit I found (date) | Notes |
|---|---|---|
| Gemini API (TTS) | **10 requests/day per model** (2026-11-26, from 429 `GenerateRequestsPerDayPerProjectPerModel-FreeTier`); a per-minute limit was also hit and recovered with 8–16 s retries | Separate quota for each TTS model |
| Cloudflare Workers AI | **10,000 neurons/day**: ran out after about 46 FLUX schnell images at 8 steps (2026-11-26, 429 code 4006), so about 215 neurons per image | Resets daily |
| Kaggle GPU | Not used (time) | Notebooks are ready in `notebooks/` |
| Gemini API (transcribe) | **25 requests/day** for `gemini-3.5-transcribe` (2026-11-26, 429) | 3.5, 3.6, 3.7 and 3.8 flash returned 503 "high demand" for over 10 minutes |

## Measured per stage

Built from `runs.jsonl` with `python -m pipeline.costs` (701 log lines, 30 runs, 2026-11-26):

| stage | model | ok calls | errors | cache hits | mean latency s | total s | GPU min | list-price USD |
|---|---|---|---|---|---|---|---|---|
| align | gemini-3.5-transcribe | 13 | 0 | 0 | 14.1 | 183 | 0.0 | 0.0000 |
| assemble | ffmpeg-assemble | 0 | 0 | 0 | 105.4 | 1687 | 0.0 | 0.0000 |
| assemble | ffmpeg-loudnorm-2pass | 0 | 0 | 0 | 17.4 | 227 | 0.0 | 0.0000 |
| keyframes | @cf/black-forest-labs/flux-1-schnell | 36 | 0 | 125 | 4.7 | 168 | 0.0 | 0.0396 |
| keyframes | placeholder-card | 0 | 0 | 0 | - | 0 | 0.0 | 0.0000 |
| music | ACE-Step 1.5 (run on Kaggle, see notebooks/) | 0 | 0 | 10 | - | 0 | 0.0 | 0.0000 |
| music | placeholder-pad | 0 | 0 | 0 | - | 0 | 0.0 | 0.0000 |
| narration | external:atronos_full.m4a | 0 | 0 | 47 | - | 0 | 0.0 | 0.0000 |
| narration | gemini-2.5-flash-preview-tts | 6 | 1 | 109 | 36.5 | 219 | 0.0 | 0.0498 |
| narration | gemini-3.1-flash-tts-preview | 5 | 0 | 37 | 13.4 | 67 | 0.0 | 0.0235 |
| narration | gemini-3.8-flash-tts | 13 | 1 | 0 | 11.7 | 152 | 0.0 | 0.0641 |
| narration | placeholder-silence | 0 | 0 | 0 | - | 0 | 0.0 | 0.0000 |
| shots | ffmpeg-kenburns | 0 | 0 | 0 | 3.8 | 575 | 0.0 | 0.0000 |
| smoke | @cf/black-forest-labs/flux-1-schnell | 1 | 1 | 0 | 11.1 | 11 | 0.0 | 0.0000 |
| smoke | gemini-2.5-flash-preview-tts | 1 | 0 | 0 | 4.0 | 4 | 0.0 | 0.0000 |
| smoke | gemini-3.8-flash-tts | 1 | 0 | 0 | 4.3 | 4 | 0.0 | 0.0000 |
| transcribe | gemini-3.5-transcribe | 7 | 0 | 0 | 13.9 | 97 | 0.0 | 0.0000 |

701 log lines, 30 runs

**Reading it:**
- **Keyframes:** 36 real FLUX calls in total, about 4.7 s each, and 125 cache hits. Caching saved about 78% of the image calls across repeated runs.
- **Narration:** 24 TTS calls across three models, because each model's free tier allows only 10 requests per day (FAILURES F9). The final film uses 0 TTS calls: narration is 47 cache hits of licensed audiobook excerpts.
- **CPU time:** the biggest consumer was local FFmpeg. Full-resolution assembly averages 105 s per aspect ratio; Ken Burns renders take 3.8 s per shot clip.
- **GPU:** 0 GPU minutes. Wan 2.2 and ACE-Step were not run, so motion is Ken Burns in FFmpeg and the score is a generated placeholder pad (see EXPERIMENTS).
- **Clean clone:** rebuilding the 88 s film with no keys takes 127 s and makes zero model calls.

## List-price equivalent

Prices used are in `pipeline/prices.py`. **They are unverified estimates. Check each pricing page and update the values and the `CHECKED_ON` date.**

| Stage | Unit | Units used | List price | Equivalent |
|---|---|---|---|---|
| Narration (Gemini TTS, drafts only) | audio second | ~550 s generated | $0.00025/s (est.) | ~$0.14 |
| Keyframes (FLUX schnell) | image | 36 | $0.0011 (est.) | ~$0.04 |
| Wan 2.2 / ACE-Step (T4) | GPU minute | 0 (not run) | $0.35/GPU-h (est.) | $0 |
| Assembly (FFmpeg, local) | CPU | ~1,700 s total | $0 | $0 |
| Transcription and alignment | requests | 20 | free tier | $0 |

## Frontier comparison

Not available to me: no frontier lane or organisation key was provided.
