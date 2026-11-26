# Design

> Fill every `TODO` with what really happened. The interview checks these notes against the logs, so write down real reactions, even short ones. Do not write ideal ones.

## Why this story

TODO: one paragraph in your own words. Why *Yegulelew Sekaram*, and why it matters to you and your family. For example: who first told it to you, where you read it, what Gulele means to your family.

## Audience and intent (written before generating)

- **Who:** young Ethiopians at home and in the diaspora (18–35) who know the title *Yegulelew Sekaram* but have never read it. *(TODO: confirm or change.)*
- **Where:** on a phone, vertical, shared on family WhatsApp and TikTok. Some viewers do not read Amharic fluently, so there are English subtitles.
- **What they should feel at the end:** they laugh at Tebeje first (the pig, "how many legs do I have?"), then feel the weight of a promise that keeps breaking. They end on Tiruneshe's line, "Nights of such vows pass", and know that the first Amharic short story is funny, sad and still true.
- **Define:** how might we make a 1948 Amharic story feel alive to people who scroll past "old literature"?

## Adaptation decisions

- The original is about 2,500 words. The film keeps **13 beats**: house, vow, relapse, flood, pig, sobriety, tavern, railway, dream, legs, last vow. It drops the side jokes (the Debre Libanos joke, the wooden-leg economics, the confessor) because each shot can carry only one idea.
- The key lines are quoted almost word for word from the original: "Whose house is this?", "Just today, just a little", "How many legs do I have?", "Nights of such vows pass". They are the story's voice.
- The amputation is shown through vultures and the dream reveal, not gore. The audience is family.
- There is one narrator voice in storyteller style, and no character voices. This keeps it simple and avoids voice-likeness questions.
- Every shot's reason is in `storyboard.json -> shots[].reason`.

## User test 1: radio cut

- **Prototype:** `outputs/final/radio_cut.mp4`, made with `python film.py --radio`. It is Amharic narration over a temp pad on a black screen. Total length: TODO s.
- **Date / how:** TODO (in person / Slack / WhatsApp).

| # | Who (relation, age range, Amharic reader?) | What they said / where they reacted | Insight |
|---|---|---|---|
| 1 | TODO | TODO | TODO |
| 2 | TODO | TODO | TODO |
| 3 | TODO | TODO | TODO |

**Pronunciation check by a native speaker:** TODO. Note any names or words the TTS said wrong (Tebeje, Gulele, Bekelech, Tiruneshe).

**What changed in the storyboard because of this:** TODO. Add each change to `storyboard.json -> revisions` too.

## User test 2: near-final cut

- **Prototype:** `outputs/final/heritage_short_9x16.mp4`.
- **Date / how:** TODO.

| # | Who | What they said / where they reacted | Insight |
|---|---|---|---|
| 1 | TODO | TODO | TODO |
| 2 | TODO | TODO | TODO |
| 3 | TODO | TODO | TODO |

**What changed:** TODO.

## Questions to ask testers

1. In one sentence, what was the story about?
2. Where did you laugh? Where did you stop paying attention?
3. Did the ending land? What do you think happens next night?
4. (Amharic speakers) Any word that sounded wrong?
5. (After test 2) Is Tebeje the same man in every shot?
