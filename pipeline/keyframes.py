"""Stage: keyframes. Character reference sheets first, then one still per shot on Cloudflare Workers AI (FLUX).

Consistency comes from what is sent every time: the same character description, the same style block,
a fixed seed per shot and (with a FLUX.2 model, api_style=multipart) the character sheet as a reference image.
"""
from __future__ import annotations

import argparse
import base64
import time
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont

from . import prices
from .common import (OUT, Cache, RetryableError, env, file_hash, load_storyboard, log_call, raise_for_http,
                     select_shots, stable_hash, with_retries)

STAGE = "keyframes"
DIR = OUT / "keyframes"
REF_DIR = OUT / "references"
API = "https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/{model}"


def build_prompt(sb: dict, image_prompt: str, characters: list[str]) -> str:
    parts = [image_prompt]
    for c in characters:
        parts.append(sb["characters"][c]["description"])
    parts.append(sb["style"]["block"])
    return ". ".join(p.strip().rstrip(".") for p in parts) + "."


@with_retries(attempts=3, base_delay=6)
def cf_generate(prompt: str, seed: int, cfg: dict, account: str, token: str, refs: list[Path]) -> bytes:
    url = API.format(account=account, model=cfg["model"])
    headers = {"Authorization": f"Bearer {token}"}
    try:
        if cfg["api_style"] == "multipart":
            fields = {"prompt": (None, prompt)}
            for k, v in cfg["params"].items():
                fields[k] = (None, str(v))
            if cfg.get("send_seed", True):
                fields["seed"] = (None, str(seed))
            for i, ref in enumerate(refs[:4]):
                fields[f"input_image_{i}"] = (ref.name, ref.read_bytes(), "image/png")
            r = requests.post(url, headers=headers, files=fields, timeout=180)
        else:
            body = {"prompt": prompt, **cfg["params"]}
            if cfg.get("send_seed", True):
                body["seed"] = seed
            r = requests.post(url, headers=headers, json=body, timeout=180)
    except requests.RequestException as e:
        raise RetryableError(str(e)) from e
    raise_for_http(r)
    if r.headers.get("content-type", "").startswith("image/"):
        return r.content
    data = r.json()
    img = (data.get("result") or {}).get("image")
    if not img:
        raise RetryableError(f"no image in response: {str(data)[:300]}")
    return base64.b64decode(img)


def placeholder_image(path: Path, title: str, subtitle: str) -> None:
    img = Image.new("RGB", (1024, 1024))
    d = ImageDraw.Draw(img)
    for y in range(1024):  # warm ochre-to-indigo gradient so the cut still reads as a sequence
        t = y / 1023
        d.line([(0, y), (1024, y)], fill=(int(176 * (1 - t) + 40 * t), int(122 * (1 - t) + 44 * t), int(60 * (1 - t) + 90 * t)))
    try:
        f1, f2 = ImageFont.truetype("arial.ttf", 64), ImageFont.truetype("arial.ttf", 34)
    except OSError:
        f1 = f2 = ImageFont.load_default()
    d.text((512, 460), title, font=f1, fill="white", anchor="mm")
    d.text((512, 540), subtitle[:48], font=f2, fill=(235, 225, 210), anchor="mm")
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)


def save_image(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".download")
    tmp.write_bytes(data)
    Image.open(tmp).convert("RGB").save(path)  # normalise JPEG/WebP responses to PNG
    tmp.unlink()


def _generate(kind: str, key: str, path: Path, prompt: str, seed: int, sb: dict, cache: Cache, mode: str,
              creds: tuple[str, str] | None, refs: list[Path], label: tuple[str, str], quiet: bool = False) -> Path:
    cfg = sb["models"]["image"]
    inputs = {"prompt": prompt, "seed": seed, "model": cfg["model"], "params": cfg["params"],
              "api_style": cfg["api_style"], "send_seed": cfg.get("send_seed", True),
              "refs": [file_hash(r) for r in refs], "mode": mode}
    h = stable_hash(inputs)
    hit = cache.hit(key, h)
    if hit:
        if not quiet:
            log_call(STAGE, shot=key, model=cfg["model"], status="cache_hit", model_call=False, input_hash=h, output=hit)
        return hit
    t0 = time.perf_counter()
    if mode == "placeholder":
        placeholder_image(path, *label)
        log_call(STAGE, shot=key, model="placeholder-card", status="placeholder", model_call=False, input_hash=h,
                 output=path, latency_s=time.perf_counter() - t0)
    else:
        if not creds:
            raise SystemExit(f"{key}: not cached and CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN missing. Put them in .env, or use --offline.")
        try:
            data = cf_generate(prompt, seed, cfg, creds[0], creds[1], refs)
        except Exception as e:
            log_call(STAGE, shot=key, model=cfg["model"], status="error", params=cfg["params"], seed=seed,
                     input_hash=h, latency_s=time.perf_counter() - t0, error=str(e))
            raise
        save_image(path, data)
        log_call(STAGE, shot=key, model=cfg["model"], status="ok", params={**cfg["params"], "kind": kind,
                 "refs": len(refs)}, seed=seed, input_hash=h, output=path, latency_s=time.perf_counter() - t0,
                 cost_usd=prices.image_cost(), extra={"prompt": prompt})
    cache.put(key, h, path, mode)
    return path


def run(only: list[str] | None = None, offline: bool = False, refs_only: bool = False, quiet: bool = False) -> dict[str, Path]:
    sb = load_storyboard()
    cfg = sb["models"]["image"]
    cache = Cache(STAGE)
    mode = "placeholder" if offline else "real"
    # Credentials are read lazily: a fully cached run (clean clone) needs no keys.
    account, token = env("CLOUDFLARE_ACCOUNT_ID"), env("CLOUDFLARE_API_TOKEN")
    creds = (account, token) if account and token else None
    if not quiet:
        print(f"[{STAGE}] model={cfg['model']} api_style={cfg['api_style']} mode={mode}")

    # 1. reference sheets (fix the look before any shot)
    ref_paths: dict[str, Path] = {}
    for name, ch in sb["characters"].items():
        prompt = build_prompt(sb, ch.get("reference_prompt", "character reference sheet"), [name])
        ref_paths[name] = _generate("reference", f"ref_{name}", REF_DIR / f"{name}.png", prompt,
                                    ch.get("reference_seed", 0), sb, cache, mode, creds, [], (f"REF {name}", "reference sheet"), quiet)
    if refs_only:
        return ref_paths

    # 2. one keyframe per shot
    out: dict[str, Path] = {}
    borrowed = []
    for shot in select_shots(sb, only):
        if shot.get("keyframe_from"):
            borrowed.append(shot)
            continue
        refs = [ref_paths[c] for c in shot["characters"]] if cfg.get("use_reference") else []
        prompt = build_prompt(sb, shot["image_prompt"], shot["characters"])
        out[shot["id"]] = _generate("keyframe", shot["id"], DIR / f"{shot['id']}.png", prompt, shot["seed"], sb,
                                    cache, mode, creds, refs, (shot["id"].upper(), shot["beat"]), quiet)
    for shot in borrowed:  # reuse an approved image: no model call, logged so the log stays complete
        src_id = shot["keyframe_from"]
        src = ref_paths[src_id[4:]] if src_id.startswith("ref:") else (out.get(src_id) or DIR / f"{src_id}.png")
        dst = DIR / f"{shot['id']}.png"
        if not src.exists():
            raise SystemExit(f"{shot['id']}: keyframe_from {src_id} has no image yet")
        if not dst.exists() or file_hash(dst) != file_hash(src):
            dst.write_bytes(src.read_bytes())
        if not quiet:
            log_call(STAGE, shot=shot["id"], model=f"borrowed:{src_id}", status="borrowed", model_call=False, output=dst)
        out[shot["id"]] = dst
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", nargs="*")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--refs-only", action="store_true")
    a = ap.parse_args()
    run(a.shot, a.offline, a.refs_only)
