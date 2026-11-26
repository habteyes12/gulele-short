"""List-price equivalents used to fill cost_usd_list_equiv in runs.jsonl.

We pay nothing (free tiers), but COSTS.md reports what the same calls would cost at public list
price. These numbers are estimates: check each provider's pricing page on the day you run and
update the value plus the date below. Record what you found in COSTS.md.
"""

CHECKED_ON = "UNVERIFIED - update after checking pricing pages"

# Gemini TTS (paid tier): price per second of generated audio.
# Basis: ~25 audio tokens per second x output audio token price.
GEMINI_TTS_USD_PER_AUDIO_SECOND = 0.00025

# Cloudflare Workers AI FLUX.1 schnell: price per image at 1024x1024, 8 steps (paid tier).
CF_FLUX_USD_PER_IMAGE = 0.0011

# GPU time on a rented T4 (for Kaggle/Colab work, list-price equivalent per GPU-hour).
T4_USD_PER_GPU_HOUR = 0.35


def tts_cost(audio_seconds: float) -> float:
    return round(audio_seconds * GEMINI_TTS_USD_PER_AUDIO_SECOND, 6)


def image_cost(n: int = 1) -> float:
    return round(n * CF_FLUX_USD_PER_IMAGE, 6)


def gpu_cost(gpu_minutes: float) -> float:
    return round(gpu_minutes / 60.0 * T4_USD_PER_GPU_HOUR, 6)
