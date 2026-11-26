"""One command for the whole pipeline.

    python film.py                 # validate -> narration -> keyframes -> shots -> music -> assemble (both aspects)
    python film.py --radio         # narration + music only, black screen (audience test 1)
    python film.py --draft         # one-third resolution, fast
    python film.py --offline       # no API keys: silent narration + placeholder cards (tests the plumbing)
    python film.py --stage keyframes --shot s04   # one stage, one shot
    python film.py --validate      # schema check only
    python film.py --storyboard storyboard_family.json   # the 3-minute family cut

Every stage caches by a hash of its inputs, so a rerun after editing one shot in storyboard.json
makes exactly one new model call for that shot. See runs.jsonl.
"""
from __future__ import annotations

import argparse
import os
import sys
import time

# --storyboard must be known before pipeline modules read it at import time
if "--storyboard" in sys.argv:
    os.environ["PIPELINE_STORYBOARD"] = sys.argv[sys.argv.index("--storyboard") + 1]

from pipeline import assemble, keyframes, music, narration, shots
from pipeline.common import RUN_ID, load_storyboard


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["narration", "keyframes", "shots", "music", "assemble"])
    ap.add_argument("--shot", nargs="*", help="limit narration/keyframes/shots to these shot ids")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--radio", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--storyboard", default="storyboard.json", help="e.g. storyboard_family.json for the 3-minute cut")
    a = ap.parse_args()

    t0 = time.perf_counter()
    sb = load_storyboard()
    print(f"storyboard.json valid: {len(sb['shots'])} shots, '{sb['title']['english']}'  run_id={RUN_ID}")
    if a.validate:
        return 0
    if a.stage == "narration":
        narration.run(a.shot, a.offline)
    elif a.stage == "keyframes":
        keyframes.run(a.shot, a.offline)
    elif a.stage == "shots":
        shots.run(a.shot, a.draft, a.offline)
    elif a.stage == "music":
        music.run(a.offline)
    elif a.stage == "assemble":
        assemble.run(a.draft, a.offline, a.radio)
    else:
        narration.run(a.shot, a.offline)
        if not a.radio:
            keyframes.run(a.shot, a.offline)
            shots.run(a.shot, a.draft, a.offline)
        assemble.run(a.draft, a.offline, a.radio)
    print(f"done in {time.perf_counter() - t0:.1f}s  (run_id={RUN_ID}, see runs.jsonl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
