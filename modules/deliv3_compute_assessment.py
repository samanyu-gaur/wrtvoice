"""
Deliverable 3 - Compute Assessment
=====================================
Quantifies the memory, latency, and concurrency impact of adding a
vision-language model (LLaVA) to the existing Socratic Oracle stack
(Whisper + LLaMA 3.1).

What this does:
    Provides functions that calculate:
      - Total VRAM consumption when the VLM is loaded alongside the
        existing models.
      - How the concurrency cap from Deliverable 2 must be adjusted.
      - Expected latency increase for vision-inclusive inference.
      - A concrete recommendation for the deployment team.

What I learned:
    - Vision-language models are expensive not because the image encoder
      is large (CLIP ViT-L is only ~0.4B params) but because the image
      tokens flood the language model's context window.  A single 336x336
      image becomes 576 tokens in LLaVA 1.5 -- equivalent to a page of
      text -- and the KV cache for those tokens eats VRAM.
    - Co-locating multiple models on one GPU is a balancing act.  You save
      on PCIe transfer overhead, but you lose the ability to independently
      scale or restart each model.
    - For a pilot, running both models on one A100 is fine.  For
      production, isolating them on separate GPUs (or using vLLM's
      multi-model serving) is safer and easier to reason about.

Author: Akshay T P
Date: March 2025
"""

from typing import Dict, Any

# ---------------------------------------------------------------------------
# DESIGN DECISION: Static analysis vs. runtime profiling
# ---------------------------------------------------------------------------
# We provide static estimates based on published model specs and our own
# measurements.
#
# Alternative: instrument the actual running system with torch.cuda memory
# snapshots and time.perf_counter measurements.
#   Pros:  ground truth numbers; accounts for driver overhead, CUDA
#          fragmentation, and quantization-specific memory layouts.
#   Cons:  requires the assessment to run on the target GPU hardware,
#          which is not always accessible during development.  Also,
#          runtime measurements vary with batch composition and sequence
#          length.
#
# Verdict: static analysis with clearly documented assumptions, plus a
#          recommendation to validate with runtime profiling once the
#          pilot hardware is provisioned.
# ---------------------------------------------------------------------------


# -- Model memory profiles --------------------------------------------------

MODEL_PROFILES = {
    "whisper_base": {
        "name": "Whisper (base)",
        "params": "74M",
        "vram_gb": 1.0,
        "can_run_on_cpu": True,
        "avg_latency_sec": 0.5,
        "notes": (
            "Whisper base transcribes short audio chunks.  For our pilot "
            "it runs on CPU, freeing GPU memory for the LLMs.  GPU mode "
            "would reduce latency from ~500ms to ~100ms per chunk."
        ),
    },
    "llama3_1_8b_q4": {
        "name": "LLaMA 3.1 8B (4-bit GGUF)",
        "params": "8B",
        "vram_gb": 6.0,
        "can_run_on_cpu": False,
        "avg_latency_sec": 4.0,
        "notes": (
            "4-bit quantization brings the 8B model from ~16 GB (fp16) to "
            "~6 GB.  Quality loss is minimal for conversational Socratic "
            "dialogue.  Ollama uses GGUF quantization by default."
        ),
    },
    "llava_7b_q4": {
        "name": "LLaVA 1.5 7B (4-bit GGUF)",
        "params": "7B + CLIP ViT-L",
        "vram_gb": 8.0,
        "can_run_on_cpu": False,
        "avg_latency_sec": 6.0,
        "notes": (
            "LLaVA 1.5 includes a CLIP ViT-L/14 image encoder (~0.3 GB) "
            "plus a 7B Vicuna language backbone (~5.5 GB at 4-bit) plus "
            "the MLP projection layer.  A single high-res image produces "
            "~576 image tokens, increasing KV cache usage."
        ),
    },
}

# -- KV cache per concurrent inference slot ---------------------------------
# Each concurrent request needs its own KV cache.  For an 8B model with
# a 2048-token context in 4-bit, this is roughly 0.5-1 GB per slot.
KV_CACHE_PER_SLOT_GB = 0.8
VLM_KV_CACHE_PER_SLOT_GB = 1.2  # higher because image tokens bloat context


def assess_text_only(
    gpu_vram_gb: float = 80.0,
    safety_margin: float = 0.20,
) -> Dict[str, Any]:
    """
    Assess capacity for text-only mode (Whisper + LLaMA 3.1).

    This is the baseline from Deliverable 2.
    """
    usable = gpu_vram_gb * (1 - safety_margin)
    whisper = MODEL_PROFILES["whisper_base"]
    llama = MODEL_PROFILES["llama3_1_8b_q4"]

    # Whisper on CPU, so only LLaMA occupies the GPU
    model_vram = llama["vram_gb"]
    remaining = usable - model_vram
    max_slots = max(1, int(remaining / KV_CACHE_PER_SLOT_GB))

    return {
        "mode": "text_only",
        "gpu_vram_gb": gpu_vram_gb,
        "usable_vram_gb": round(usable, 1),
        "model_vram_gb": model_vram,
        "kv_cache_per_slot_gb": KV_CACHE_PER_SLOT_GB,
        "max_concurrent_slots": max_slots,
        "avg_latency_sec": llama["avg_latency_sec"],
        "throughput_rps": round(max_slots / llama["avg_latency_sec"], 2),
    }


def assess_text_plus_vision(
    gpu_vram_gb: float = 80.0,
    safety_margin: float = 0.20,
    vision_request_fraction: float = 0.30,
) -> Dict[str, Any]:
    """
    Assess capacity when the VLM (LLaVA) is loaded alongside the text LLM.

    Args:
        gpu_vram_gb:             total VRAM available
        safety_margin:           fraction reserved for overhead
        vision_request_fraction: expected fraction of requests that include
                                 an image (affects weighted avg latency)

    Returns:
        capacity assessment dict
    """
    usable = gpu_vram_gb * (1 - safety_margin)
    llama = MODEL_PROFILES["llama3_1_8b_q4"]
    llava = MODEL_PROFILES["llava_7b_q4"]

    # Both models must be resident in VRAM simultaneously
    model_vram = llama["vram_gb"] + llava["vram_gb"]
    remaining = usable - model_vram

    # The KV cache per slot is a weighted average depending on whether
    # the request uses vision or text-only
    weighted_kv = (
        vision_request_fraction * VLM_KV_CACHE_PER_SLOT_GB
        + (1 - vision_request_fraction) * KV_CACHE_PER_SLOT_GB
    )
    max_slots = max(1, int(remaining / weighted_kv))

    # Weighted average latency
    weighted_latency = (
        vision_request_fraction * llava["avg_latency_sec"]
        + (1 - vision_request_fraction) * llama["avg_latency_sec"]
    )

    return {
        "mode": "text_plus_vision",
        "gpu_vram_gb": gpu_vram_gb,
        "usable_vram_gb": round(usable, 1),
        "model_vram_gb": model_vram,
        "text_model_vram": llama["vram_gb"],
        "vision_model_vram": llava["vram_gb"],
        "weighted_kv_per_slot_gb": round(weighted_kv, 2),
        "max_concurrent_slots": max_slots,
        "vision_request_fraction": vision_request_fraction,
        "weighted_avg_latency_sec": round(weighted_latency, 2),
        "throughput_rps": round(max_slots / weighted_latency, 2),
    }


def compare_modes(gpu_vram_gb: float = 80.0) -> Dict[str, Any]:
    """
    Side-by-side comparison of text-only vs. text+vision on the same GPU.

    This is the key output for the compute assessment deliverable.
    """
    text = assess_text_only(gpu_vram_gb)
    vision = assess_text_plus_vision(gpu_vram_gb)

    slot_reduction = text["max_concurrent_slots"] - vision["max_concurrent_slots"]
    latency_increase = (
        vision["weighted_avg_latency_sec"] - text["avg_latency_sec"]
    )

    return {
        "text_only": text,
        "text_plus_vision": vision,
        "impact_summary": {
            "concurrent_slot_reduction": slot_reduction,
            "latency_increase_sec": round(latency_increase, 2),
            "additional_vram_gb": MODEL_PROFILES["llava_7b_q4"]["vram_gb"],
        },
        "recommendation": (
            f"Adding the vision model consumes an extra "
            f"{MODEL_PROFILES['llava_7b_q4']['vram_gb']} GB of VRAM and "
            f"reduces max concurrency by {slot_reduction} slot(s) on a "
            f"{gpu_vram_gb} GB GPU.  Average latency increases by "
            f"~{round(latency_increase, 1)}s for vision requests.  "
            f"For a pilot with ~20 peak concurrent users, a single A100 "
            f"80 GB is still sufficient.  If vision usage exceeds 50% of "
            f"requests, consider a second GPU dedicated to the VLM."
        ),
    }


def full_assessment() -> Dict[str, Any]:
    """
    Generate the complete compute assessment report.  Intended to be
    called from a route or printed to stdout.
    """
    return {
        "model_profiles": MODEL_PROFILES,
        "assessment_a100_80gb": compare_modes(80.0),
        "assessment_a100_40gb": compare_modes(40.0),
        "assessment_rtx4090_24gb": compare_modes(24.0),
        "key_takeaways": [
            "Whisper runs on CPU -- it does not compete for GPU VRAM.",
            "LLaVA 7B (4-bit) needs ~8 GB VRAM on top of LLaMA's ~6 GB.",
            "On a single A100 80 GB, both models fit with ample headroom "
            "for concurrent KV caches.",
            "On a 40 GB GPU, concurrency drops significantly -- recommend "
            "dedicated GPUs per model.",
            "On consumer hardware (24 GB), running both models "
            "simultaneously is tight; text-only mode is safer.",
            "Vision inference is ~50% slower than text-only due to image "
            "token processing.",
        ],
    }


# ---------------------------------------------------------------------------
# FUTURE IMPROVEMENTS (if we had more time)
# ---------------------------------------------------------------------------
# 1. Runtime benchmarking script:
#    A script that actually loads the models, sends sample requests, and
#    records wall-clock latency and peak VRAM.  This would replace our
#    static estimates with ground truth.
#
# 2. Adaptive concurrency:
#    Dynamically adjust the semaphore cap based on real-time GPU memory
#    pressure (via pynvml).  If memory usage spikes above 90%, temporarily
#    reduce the cap; if it drops, increase it.
#
# 3. Model swapping / offloading:
#    If the VLM is not being used, unload it from VRAM and reclaim the
#    memory for more text-only KV cache slots.  Reload when a vision
#    request arrives (adds a cold-start penalty of ~10-15 seconds).
#
# 4. Quantization exploration:
#    Test 3-bit or 2-bit quantization for the VLM specifically, since
#    design critique is less sensitive to subtle inference quality than,
#    say, medical imaging.  This could save 2-3 GB of VRAM.
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    import json
    print(json.dumps(full_assessment(), indent=2))
