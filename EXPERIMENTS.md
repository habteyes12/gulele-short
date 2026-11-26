# Experiments

Format: **hypothesis → change → result → decision**. Change one thing at a time and keep the seed fixed. Cite the `run_id` or log lines from `runs.jsonl` as evidence. Target: about 10 entries.

## E1. Shot length from placeholder narration estimate

- **Hypothesis:** 13 shots with 5–8 s minimums and narration estimated at 1.8 words/s fit inside 60–90 s.
- **Change:** offline dry run, `python film.py --offline --draft` (run `20261126T061508-97e0`).
- **Result:** total 101.7 s (98.2 s film + 3.5 s end card), outside the target. The `min_duration_s` floors (6–8 s) were adding dead time.
- **Decision:** set the minimums to 5 s (7 s for the last shot) and the narration tail from 0.7 to 0.5 s. The re-run (`20261126T073158-c979`) still came to 99.2 s, so the narration itself was too long. I trimmed 9 lines (removed repeats the picture already shows, such as "Gulele roared with laughter" over a shot of people laughing), going from about 150 to 136 Amharic words. Run `20261126T073440-571a`: 91.0 s on the estimate. The real number depends on actual TTS speed (E2).

## E2. Real Amharic TTS speed vs estimate

- **Hypothesis:** Gemini TTS reads the Amharic lines at about 1.8 words/s, so the film lands at about 80 s.
- **Change:** first real narration runs.
- **Result:**
  - `20261126T120030-dd08` (gemini-3.8-flash-tts, long style prompt): 268 s. That is the prompt problem in E3, not the reading speed.
  - With the prompt fixed (`gemini-3.1-flash-tts-preview`, run `20261126T121915-b2bf`): each line takes 4.4–8.2 s, about 1.9 words/s. The estimate held, but the film was 98.8 s, because 13 lines with leads and tails do not fit in 90 s.
- **Decision:** cut s02 ("Meet Tebeje": s01 already names him, s03 shows his face), and tightened the lead and tail to 0.3 s and 0.4 s. Run `20261126T122017-538b`: **89.3 s**. The change is recorded in `storyboard.json -> revisions`.

## E3. Style prompt: does a long instruction help?

- **Hypothesis:** a descriptive style instruction ("old storyteller by a coffee fire, calm, unhurried, dry humour…") improves the narration.
- **Change:** same line (s01), same voice (Charon), three prompts. Clips are in `outputs/experiments/e3_tts_prompt/`.

| Prompt | Model | s01 length |
|---|---|---|
| long instruction, blank line, text | gemini-3.8-flash-tts | 19.07 s |
| `Say slowly and warmly, like an old storyteller by the coffee fire: <text>` | gemini-2.5-flash-preview-tts | 10.37 s |
| `Say: <text>` | gemini-2.5-flash-preview-tts | 6.61 s |

- **Result:** the long instruction tripled the length. `silencedetect` shows continuous speech, so the extra time is spoken words, most likely the English instruction read aloud. TODO: confirm by ear. "Slowly" alone added about 57% to the length.
- **Decision:** use `Say: <text>`. With Amharic text, the model's default reading is already calm. The brief's advice that "a short style instruction usually improves a voice" did not hold here: any instruction cost time I did not have. TODO: confirm by ear which take sounds best.

## E4. Character consistency: text-only vs reference image

- **Hypothesis:** repeating the identical character description and style block keeps Tebeje recognisable across shots without a reference image.
- **Change:** generated both reference sheets and all 12 keyframes with `flux-1-schnell`, text only (run `20261126T122114-c0e7`, 14 calls, 3.1–17.0 s each). The character description and style block are identical in every prompt. Contact sheet: `outputs/experiments/keyframes_v1_contact.jpg`.
- **Result (my read of the contact sheet):**
  - Tebeje keeps the same features in all 11 shots he appears in: long grey-black hair, full grey beard, off-white gabi, khaki trousers, bare feet.
  - Tiruneshe matches her sheet in s12 and s13 (white netela).
  - Drift: hair colour varies between more grey (s04, s13) and darker (s07, s12). The face shape differs from shot to shot. The style block held the palette and gouache look throughout.
  - Defects: garbled sign text in s09 (schnell has no negative prompt); the pig in s07 is small and easy to miss.
  - TODO: blind check. Show 2 people 4 shots each and ask "same man?"
- **Decision:** text-only consistency is good enough for a pan-and-zoom film. The reference-image path (FLUX.2, `use_reference: true`) stays in the code but is not used. TODO: if time allows, regenerate s07 with "a large pink pig" and compare.

## E5. Seed sweep on a hard shot

- **Hypothesis:** the crowd shots (s06, s09) fail more often (hands, faces) and need several seeds.
- **Change:** s09 with seeds 109, 209, 309, same prompt.
- **Result:** TODO
- **Decision:** TODO

## E6. Score candidates (ACE-Step)

- **Hypothesis:** a sparse masinqo/krar caption with "no lead melody" sits under the voice better than a fuller arrangement.
- **Change:** 3 candidates, seeds 11/22/33 (`notebooks/acestep_kaggle.py`). Listen at low volume under the radio cut.
- **Result:** TODO (one line per candidate)
- **Decision:** chose TODO because TODO.

## E7. Ducking settings

- **Hypothesis:** threshold 0.02, ratio 6, attack 300 ms, release 1500 ms ducks smoothly without pumping.
- **Change:** compare with ratio 3, and with release 600 ms.
- **Result:** TODO
- **Decision:** TODO

## E8. Ken Burns vs Wan 2.2 on one shot

- **Hypothesis:** for a slow emotional shot (s03), a Ken Burns push-in is as good as a Wan clip at a fraction of the GPU cost.
- **Change:** s03 as Ken Burns vs Wan 2.2 TI2V-5B. Log GPU minutes. Blind preference test with at least 3 people.
- **Result:** TODO
- **Decision:** TODO

## E9. Subtitle readability in 9:16

- **Hypothesis:** a 30-character wrap at font size 9 stays inside the vertical safe area and is readable on a phone.
- **Change:** watch on a real phone. Compare with 40 characters at size 8.
- **Result:** TODO
- **Decision:** TODO

## E10. Two-pass vs one-pass loudnorm

- **Hypothesis:** two-pass loudnorm hits −14 LUFS more accurately than one-pass.
- **Change:** compare the `after_I` values logged by `ffmpeg-loudnorm-2pass` with a one-pass run.
- **Result:** TODO
- **Decision:** TODO

## E11. Automatic check: does each clip say its own line?

- **Hypothesis:** splitting batches at silences (`narration.split_batch`) puts every line on the right shot.
- **Change:** transcribed each clip with `gemini-3.5-transcribe` and compared it to `storyboard.json` (`outputs/experiments/narration_transcript_check.txt`).
- **Result:** 6 of 12 were checked before the per-minute quota hit (s01, s03, s04, s05, s06, s08). All 6 match their own shot's text, in order, with no English spoken. Possible mispronunciation: s01 "ዶሮ ነጋዴው" was heard as "ዶሮ እና ጋዲዮ". TODO: a native speaker confirms by ear.
- **Decision:** the split works. TODO: check s07 and s09–s13 when the quota resets, or by ear in `outputs/review.html`.

## E12. Look: gouache illustration vs cinematic photoreal

- **Hypothesis:** a "35mm film still, anamorphic, practical light" style block makes the film read as more professional, and an explicit "Ethiopian Habesha … bloodshot glassy drunk eyes" description makes Tebeje clearly Ethiopian and clearly drunk. Both were requested by the project author.
- **Change:** replaced the style block and character descriptions; regenerated all keyframes (run `20261126T131836-d1a0`, 12 calls, 3.5–5.8 s each). Contact sheets: `outputs/experiments/keyframes_v1_contact.jpg` (gouache) vs `keyframes_v2_cinematic_contact.jpg`.
- **Result:** the cinematic set reads as real 1940s Addis. Faces are clearly Habesha, the gabi and beard stay the same across shots, and the drunk expressions show in s01, s03 and s04. Small defects: garbled sign text on a wall in s01; in s07 he holds bottles rather than being carried.
- **Decision:** keep the cinematic look.

## E13. Spliced short quotes vs continuous passages

- **Hypothesis:** the film needs the most famous lines, even if they are short.
- **Change:** a 10-shot cut built from short quotes joined by "…" vs 12 continuous sentences from the book.
- **Result:** short quotes were 0.4–3.6 s, often located at the wrong place, and joining two quotes spliced across a pause. Continuous passages were 5.7–14.7 s, all located correctly (confirmed by ear), and sounded natural.
- **Decision:** use continuous passages. The famous lines are still there, inside their own sentences.

## E14. Same contract, three lengths

- **Hypothesis:** one storyboard schema and pipeline can produce cuts of different lengths without code changes.
- **Change:** `storyboard.json` (9 passages) vs `storyboard_family.json` (20 passages), selected with `film.py --storyboard`.
- **Result:** submission cut 88.4 s (run `20261126T134318-a2a8`); family cut 188.4 s (run `20261126T135155-6f57`). Both are at −14.0 LUFS and −1.0 dBTP. The shots the two cuts share were cache hits in the second render: only the 10 new keyframes were generated.
- **Decision:** submit the 88 s cut, because the brief asks for 60–90 s. The 3-minute cut is for family and the post.
