# Ethics: consent, licences, labelling

## Consent

- **A real person is voiced: the narrator.** The narration is cut from the Ethio Atronos Amharic audiobook of *Yegulelew Sekaram* (YouTube `@Atronosaudiobook`, read by narrator Samuel Adugna, as named in the recording's intro). The film uses short excerpts of his own reading of Temesgen Gebre's text. No AI voice cloning or imitation is used, and no words are put in his mouth that he did not read.
- **No real person is shown.** Tebeje, Weyzero Tiruneshe and the people of Gulele are fictional characters from a 1948 short story. All faces are generated from text descriptions. No photo of a real person was used as a reference.

| Person | Appears as | Consent given (date, how) | Words agreed |
|---|---|---|---|
| Samuel Adugna, Ethio Atronos audiobook | Voice: excerpts of his audiobook reading | The project author asked him for permission and he agreed (2026-11-26). TODO: how (Telegram / YouTube / phone), and save a screenshot of his reply at `docs/consent/atronos.png` | His own reading of the original text, excerpts only, in a non-commercial student film (90 s cut) and a family cut (about 3 min), posted publicly with the AI label switched on |

On-screen credit: the project author chose not to show his name on the end card. TODO: confirm the narrator is happy with that. This record and the post description carry the credit: "Narration: Ethio Atronos audiobook, used with permission".

## The source text

- *Yegulelew Sekaram* by **Temesgen Gebre**, first printed in Addis Ababa, Hidar 1941 E.C. (1948), pages 1–13. Asfaw Damte and Zerihun Asfaw credit it as the first Amharic short story.
- The full text used for the storyboard was taken from the Andemta blog (posted 29 June 2017), which states it is published "በደራሲው ቤተሰብ መልካም ፈቃድ" (with the kind permission of the author's family).
- **Copyright status: TODO, verify.** Ethiopian copyright (Proclamation No. 410/2004) protects a work for the author's life plus 50 years. The film is a non-commercial educational adaptation that credits the author on the title card and the end card.

## Model and output licences

| Component | Model / tool | Licence / terms | Output use |
|---|---|---|---|
| Narration (final) | Ethio Atronos audiobook recording | Used with the narrator's permission (see Consent) | Excerpts only, credited |
| Narration (earlier drafts, experiments) | Gemini TTS | Gemini API Terms; free-tier inputs may be used to improve Google products | Drafts only |
| Transcription / alignment | gemini-3.5-transcribe | Gemini API Terms | Internal: used only to find cut points |
| Keyframes | FLUX.1 [schnell] via Cloudflare Workers AI | Apache 2.0 weights; Cloudflare terms | Usable |
| Keyframes (alt) | FLUX.2 [klein] 4B | Apache 2.0 (the 9B variant is non-commercial: not used) | Usable |
| Video (optional) | Wan 2.2 TI2V-5B | Apache 2.0 | Usable |
| Music | ACE-Step 1.5 | MIT; trained on licensed, royalty-free and synthetic data | Usable commercially |
| Assembly | FFmpeg (imageio-ffmpeg build) | LGPL/GPL build | Tool only |
| Fonts | Ebrima (Windows), Arial | Windows system fonts | Rendered into video |

TODO: confirm each licence on the model card the day you use it.

## Labelling

- The film ends with an end card: "Made with AI: images FLUX, voice Gemini TTS, music ACE-Step".
- The platform's AI-content disclosure is switched on when posting (TikTok "AI-generated" label / YouTube "altered or synthetic content").
- Watermarks and provenance metadata from the models (SynthID in Gemini audio, any C2PA data) are not stripped.
- The post says in words that the film was made with AI, adapted from Temesgen Gebre's story.

## Style and privacy

- Prompts describe qualities ("hand-painted gouache, warm, grainy"). They never name a living artist.
- No private family details are sent to free endpoints. Only the published story text and invented prompts are sent.
- The story is about alcoholism. It is treated with humour and sympathy, without mocking addiction. The ending leaves the question open, as the original does.
