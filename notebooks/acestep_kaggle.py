# %% [markdown]
# # ACE-Step 1.5: three score candidates (Kaggle, GPU T4 x2, Internet ON)
# Paste each `# %%` block into its own Kaggle cell. Upload storyboard.json as a Kaggle dataset, or paste the
# music block into MUSIC below.
#
# Check the ACE-Step 1.5 README (https://github.com/ACE-Step/ACE-Step-1.5) for its current inference entry
# point before you run this. The install and CLI change between releases. If the CLI below fails, use the
# README's Python API or Gradio launch command instead, and write down what you changed in FAILURES.md.

# %%
import json, time, subprocess, pathlib, datetime
MUSIC = {
    "caption": "instrumental, slow Ethiopian tizita mood, solo masinqo and soft krar, gentle kebero hand drum far in the background, warm, nostalgic, sparse, no lead melody under the voice, theme returns at the end",
    "bpm": 72, "key": "C minor", "duration_s": 95, "instrumental": True,
}
SEEDS = [11, 22, 33]
OUT = pathlib.Path("/kaggle/working/music"); OUT.mkdir(parents=True, exist_ok=True)
LOG = pathlib.Path("/kaggle/working/gpu_runs.jsonl")

def log(**rec):
    rec.setdefault("ts", datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z")
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")

# %%
t0 = time.time()
subprocess.run("git clone --depth 1 https://github.com/ACE-Step/ACE-Step-1.5 && cd ACE-Step-1.5 && pip install -q -e .",
               shell=True, check=True)
print(f"install {time.time() - t0:.0f}s")

# %%
# Generate one candidate per seed. CHECK THE FLAGS against the README.
for seed in SEEDS:
    dst = OUT / f"candidate_seed{seed}.wav"
    cmd = ["python", "-m", "acestep.cli",            # <- verify the entry point in the README
           "--caption", MUSIC["caption"], "--duration", str(MUSIC["duration_s"]),
           "--bpm", str(MUSIC["bpm"]), "--key", MUSIC["key"], "--seed", str(seed),
           "--instrumental", "--output", str(dst)]
    t0 = time.time()
    r = subprocess.run(cmd, cwd="ACE-Step-1.5", capture_output=True, text=True)
    dt = time.time() - t0
    ok = r.returncode == 0 and dst.exists()
    log(stage="music", shot=None, model="ACE-Step-1.5", status="ok" if ok else "error", seed=seed,
        params={k: MUSIC[k] for k in ("bpm", "key", "duration_s", "instrumental")}, latency_s=round(dt, 2),
        gpu_minutes=round(dt / 60, 2), output=f"outputs/music/candidates/{dst.name}",
        error=None if ok else r.stderr[-400:])
    print(seed, "ok" if ok else r.stderr[-400:], f"{dt:.0f}s")

# %% [markdown]
# Download /kaggle/working/music/*.wav into outputs/music/candidates/ and gpu_runs.jsonl into notebooks/.
# Then on your machine:
#     python -m pipeline.ingest notebooks/gpu_runs.jsonl
# Listen to each candidate quietly under the radio cut, pick one, set storyboard.json -> music.chosen to
# "outputs/music/candidates/candidate_seedNN.wav", and write the reason in EXPERIMENTS.md.
