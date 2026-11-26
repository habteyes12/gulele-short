# %% [markdown]
# # Wan 2.2 TI2V-5B image-to-video (optional, Kaggle GPU, Internet ON)
# Upload outputs/keyframes/*.png and storyboard.json as a Kaggle dataset. Draft at the smallest size first.
# A T4 has 16 GB and no bf16 speed-up, so expect several minutes or more per 5 s clip. Pick your 3-4 most
# important shots instead of all 13. Shots without a clip keep their Ken Burns move.
# Check https://github.com/Wan-Video/Wan2.2 for the current flags before you run.

# %%
import json, time, subprocess, pathlib, datetime
DATA = pathlib.Path("/kaggle/input/gulele-short")          # <- your dataset name
SB = json.loads((DATA / "storyboard.json").read_text())
SHOTS = ["s03", "s06", "s09", "s13"]                       # <- the shots worth the GPU time
OUT = pathlib.Path("/kaggle/working/clips"); OUT.mkdir(parents=True, exist_ok=True)
LOG = pathlib.Path("/kaggle/working/gpu_runs.jsonl")

def log(**rec):
    rec.setdefault("ts", datetime.datetime.utcnow().isoformat(timespec="milliseconds") + "Z")
    with open(LOG, "a") as f:
        f.write(json.dumps(rec) + "\n")

# %%
subprocess.run("git clone --depth 1 https://github.com/Wan-Video/Wan2.2 && cd Wan2.2 && pip install -q -r requirements.txt",
               shell=True, check=True)
subprocess.run("pip install -q 'huggingface_hub[cli]' && huggingface-cli download Wan-AI/Wan2.2-TI2V-5B --local-dir Wan2.2/Wan2.2-TI2V-5B",
               shell=True, check=True)

# %%
by_id = {s["id"]: s for s in SB["shots"]}
for sid in SHOTS:
    shot = by_id[sid]
    dst = OUT / f"{sid}.mp4"
    cmd = ["python", "generate.py", "--task", "ti2v-5B", "--size", "1280*704",
           "--ckpt_dir", "./Wan2.2-TI2V-5B", "--offload_model", "True", "--convert_model_dtype", "--t5_cpu",
           "--image", str(DATA / "keyframes" / f"{sid}.png"), "--prompt", shot["video_prompt"],
           "--base_seed", str(shot["seed"]), "--save_file", str(dst)]
    t0 = time.time()
    r = subprocess.run(cmd, cwd="Wan2.2", capture_output=True, text=True)
    dt = time.time() - t0
    ok = r.returncode == 0 and dst.exists()
    log(stage="shots", shot=sid, model="Wan2.2-TI2V-5B", status="ok" if ok else "error", seed=shot["seed"],
        params={"size": "1280*704", "offload": True, "t5_cpu": True}, latency_s=round(dt, 2),
        gpu_minutes=round(dt / 60, 2), output=f"outputs/clips/{sid}.mp4", error=None if ok else r.stderr[-400:])
    print(sid, "ok" if ok else r.stderr[-600:], f"{dt / 60:.1f} min")

# %% [markdown]
# Download clips into outputs/clips/ and gpu_runs.jsonl into notebooks/, then:
#     python -m pipeline.ingest notebooks/gpu_runs.jsonl
#     python film.py
# The shots stage finds outputs/clips/<id>.mp4 and uses it in place of the Ken Burns move for that shot only.
