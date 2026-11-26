# Failures

Format: **what broke → what I tried → what fixed it / workaround**. Add an entry every time something breaks. These are the evidence for the troubleshooting criterion.

## F1. No FFmpeg on the machine

- **Broke:** `ffmpeg: command not found` on Windows 11. No admin-free install was at hand, and the deadline was close.
- **Tried:** checked PATH; considered winget.
- **Fix:** added `imageio-ffmpeg` to requirements. It bundles a static FFmpeg 9 build with libass, zoompan, sidechaincompress and loudnorm (checked with `ffmpeg -filters`). `pipeline/common.py:ffmpeg_exe` uses the system FFmpeg if one is on PATH, otherwise the bundled one. A clean clone needs only `pip install`.

## F2. No `make` on Windows

- **Broke:** the brief says `make film`, but Git Bash on this machine has no `make`.
- **Fix:** `python film.py` is the real entry point. The `Makefile` is a thin wrapper for machines that have `make`.

## F3. No `ffprobe` either

- **Broke:** the bundled FFmpeg comes without `ffprobe`, which I wanted for media durations.
- **Fix:** WAV durations come from Python's `wave` module. Other durations are parsed from `ffmpeg -i` stderr (`common.media_duration`).

## F4. Film too long in the first dry run

- See EXPERIMENTS E1. The total was 101.7 s against a 90 s ceiling. The minimum shot durations were reduced.

## F5. TODO: first real API run

Write down what really happens: wrong TTS model ID (`python -m pipeline.smoke` lists the valid ones), quota or 429 errors, Cloudflare rejecting a parameter, bad Amharic pronunciation, identity drift, Kaggle GPU queue or out-of-memory, ACE-Step CLI changes.

## F6. Cloudflare FLUX.1 schnell rejects `seed`

- **Broke:** the smoke test failed with `HTTP 400: AiError: Bad input: Error: Additional or unevaluated properties '/seed' at '/' not allowed` (code 5006). The Workers AI schema for `@cf/black-forest-labs/flux-1-schnell` accepts only `prompt` and `steps`.
- **Fix:** set `models.image.send_seed: false` in `storyboard.json`. The seed is still logged and stays in the cache hash.
- **Consequence:** schnell keyframes are **not reproducible** from the seed. Re-running a changed shot gives a new image. The cache protects every unchanged shot, so a re-run never touches approved images. To get seed control, switch to a FLUX.2 model on Workers AI, if its schema accepts `seed` (test it with `python -m pipeline.smoke`).

## F7. TTS model choice

- The smoke test listed the TTS models this key can see: `gemini-2.5-flash-preview-tts`, `gemini-2.5-pro-preview-tts`, `gemini-3.1-flash-tts-preview`, `gemini-3.8-flash-tts`, `gemini-3.8-flash-lite-tts`. The storyboard default (`2.5-flash-preview`) worked (4.0 s). I switched to `gemini-3.8-flash-tts`, the current model named in the brief. See EXPERIMENTS E3 for the comparison.

## F8. Narration 3× too long: 268 s film

- **Broke:** the first real narration run (`20261126T120030-dd08`) gave a 268 s film. Most clips were 19–23 s for lines of 7–14 Amharic words. s07 was 6 s, which matches the expected 5–7 s.
- **Tried:** transcribing the clips with `gemini-3.8-flash` failed (HTTP 503, high demand). `gemini-3.8-flash-lite` is not available for `generateContent` (404). `silencedetect` showed continuous speech for 17–21 s with only short gaps, so the length is speech, not pauses.
- **Hypothesis:** the TTS read the long English style instruction aloud before the Amharic. The prompt was the instruction, a blank line, then the text. TODO: confirm by listening to `outputs/narration/s01.wav`.
- **Fix:** shortened the instruction and changed the prompt to the documented `"Say ...: <text>"` form (`narration.py`). Status: TODO after quota resets / on another model.

## F9. Gemini TTS free tier: 10 requests per day per model

- **Broke:** HTTP 429 with `GenerateRequestsPerDayPerProjectPerModel-FreeTier`, `quotaValue: 10`, model `gemini-3.8-flash-tts`, `retryDelay: 71536s`. One 13-shot run plus the smoke test used up the day.
- **What I learned:** the retry decorator was retrying a daily quota (8 s, 16 s) and wasting attempts. Per-minute limits recovered with those retries, but the daily limit never does.
- **Fix:** `raise_for_http` now fails fast when a 429 says "per day". Per-minute 429s still retry. Because the quota is per model, the remaining runs today use a different TTS model; it is used for all 13 shots so the voice stays the same.

## F10. Runaway TTS audio after a timeout, and a second quota wall

- **Broke:** in the batched run `20261126T121039-9a7c`, the s08+s09+s10 call timed out (read timeout 120 s). The retry returned 83 s of audio for three lines that should take about 20 s (s08 33 s, s10 33 s after the split). Copies are in `outputs/experiments/f10_runaway/`.
- **Tried:** re-running that batch on `gemini-2.5-flash-preview-tts` hit its daily quota of 10. The smoke test, 2 prompt tests, 4 batches and the timed-out attempt all counted.
- **Fix:**
  1. Added a sanity check in `narration.py`: audio longer than 2 × (words ÷ 1.8) + 3 s is rejected before it can be saved or cached.
  2. Regenerated **all 13 lines** on one fresh model (`gemini-3.1-flash-tts-preview`, 5 batched calls) instead of mixing models, so the narrator's voice stays the same across the film.
- **Lesson:** at 10 requests per day per model, batching (3 lines per call, split at silences: `narration.split_batch`) is what made a 13-line film possible on the free tier.

## F11. The TTS voice did not sound like the story

- **Broke:** after hearing the TTS radio cut next to the Ethio Atronos audiobook of the original, the project author (a native speaker) judged the AI narration and my paraphrased script wrong for the story. The words were not Temesgen Gebre's, and the delivery was not a storyteller's.
- **Tried:** (1) rewrote the script as near-verbatim excerpts in the original order; (2) considered recording our own voice.
- **Fix:** the narrator gave permission (ETHICS.md), so the film now uses excerpts of his real reading. `narration.py` got an `audio_source` path: it cuts `[start, end]` segments from a licensed recording instead of calling TTS. It is cached and logged as `external:<file>`.

## F12. The transcription model ignores timestamp instructions

- **Broke:** `gemini-3.5-transcribe` returned plain continuous text for each 4-minute chunk and ignored the request for `[mm:ss-mm:ss]` sentence timestamps (`transcribe.py` parsed 0 segments).
- **Fix:** `pipeline/align.py` locates each target sentence by fuzzy match in the chunk text, converts its character position into a time estimate, and snaps the estimate to the narrator's real pauses.

## F13. silencedetect missed the narrator's pauses

- **Broke:** the first alignment gave cuts up to 76 s long. `silencedetect=n=-32dB:d=0.3` found too few pauses.
- **Measured:** a 50 ms loudness envelope over 15–75 s showed speech at a median of −21 dB and pauses around −40 dB. The pauses are real but short (0.15–0.3 s).
- **Fix:** pauses now come from the envelope itself (below −32 dB for at least 0.15 s), preferring sentence-length pauses of 0.35 s or more. Cut lengths dropped to 5–15 s.

## F14. Short quotes cannot be located; verification quotas

- **Broke:**
  - Two-word quotes such as "Is the woman saved?" produced 0.4–1.0 s cuts at the wrong places.
  - Verifying each cut by transcribing it used up `gemini-3.5-transcribe`'s 25 requests per day.
  - The fallback models (3.5, 3.6, 3.7 and 3.8 flash) all answered 503 "high demand" for over 10 minutes.
- **Fix:**
  - Use whole continuous sentences from the book (8–25 words), which are long enough to locate and have no audible splices.
  - Add a fallback list to `transcribe.py`.
  - The final check was by ear: `pipeline/review.py` builds a page with every cut next to its text. The project author listened to all of them and confirmed they were good.

## F15. Null bytes and quote marks broken by shell heredocs

- **Broke:** editing Python through Git Bash heredocs turned `"\x00"` escapes into real NUL bytes (`SyntaxError: source code string cannot contain null bytes`). The console also showed Amharic quote marks as `?`.
- **Fix:** rewrote the bytes with explicit byte codes, checked the JSON with `grep` for U+FFFD (none were really damaged), and used the Edit tool for escapes from then on.

## F16. A clean clone demanded API keys even with everything cached

- **Broke:** the clean-clone test (only the git-published files, no `.env`) stopped at once with `GEMINI_API_KEY missing`. The narration and keyframe stages checked for keys before looking at the cache.
- **Fix:** keys are now read lazily: a stage asks for a key only when a shot is not cached. Re-test (run `20261126T142135-0336`): no keys, zero model calls, the 88.4 s film rebuilt in 127 s.

## F17. Cloudflare daily image allowance, and no free Gemini image model

- **Broke:** generating 3 new opening keyframes for the family cut failed with `429 … you have used up your daily free allocation of 10,000 neurons` (code 4006), after about 46 FLUX schnell images that day. The retry decorator retried twice, because this daily cap has different wording from Gemini's.
- **Tried:** `gemini-nano-banana-2.1` and `nano-banana-pro-preview` both returned 429 quota on the first call (no free image tier on this key).
- **Fix:**
  1. `raise_for_http` now also fails fast on "daily free allocation".
  2. New storyboard field `keyframe_from`: a shot can borrow an approved image (`s01`, or `ref:tiruneshe` for the reference sheet). Nothing is called, and the borrowing is logged as `borrowed:<id>`.
  3. The submission cut needed no new images, so it was not blocked.
- **TODO:** when the allowance resets, remove `keyframe_from` from s21, s22 and s23 in `storyboard_family.json` and re-run. Only those 3 images and their clips will regenerate.
