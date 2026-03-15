"""
Deliverable 2 - Resource Estimation
=====================================
GPU allocation estimates for deploying Socratic Oracle to a cohort of
250 HKU architecture students over a single semester.

What this does:
    Provides a pure-computation module (no web routes) that models
    realistic peak concurrent usage and calculates the GPU hardware
    required to serve the pilot.  The output is used in the admin
    dashboard and in our deployment documentation.

What I learned:
    - Capacity planning for AI workloads is fundamentally different from
      web app scaling.  A traditional web app is CPU-bound and scales
      horizontally; an LLM inference server is GPU-memory-bound and
      scales by stacking GPUs.
    - "250 students" does not mean "250 simultaneous users".  For an
      asynchronous tutoring tool (not a live lecture), realistic peak
      concurrency is around 5-10% of enrollment, especially spread
      across a semester.
    - VRAM is the bottleneck, not FLOPS.  A single A100 (80 GB) can
      hold the model weights for llama3.1 8B comfortably, but the KV
      cache for concurrent requests eats into that budget fast.

Author: Akshay T P
Date: March 2025
"""

from dataclasses import dataclass, field
from typing import Dict, Any


# ---------------------------------------------------------------------------
# DESIGN DECISION: Hardcoded model profiles vs. dynamic GPU probing
# ---------------------------------------------------------------------------
# We hardcode VRAM requirements for the models we know we will deploy.
#
# Alternative: dynamically query nvidia-smi or torch.cuda to detect
# available GPUs and current memory usage at runtime.
#   Pros:  always accurate, adapts to the actual hardware.
#   Cons:  requires the estimation code to run on a machine with GPUs,
#          which is not always the case during development.  Also, you
#          cannot plan capacity if the tool only works after deployment.
#
# Verdict: hardcoded profiles based on published model specs.  We add
#          a safety margin (20%) to account for fragmentation and
#          runtime overhead.
# ---------------------------------------------------------------------------


@dataclass
class ModelProfile:
    """VRAM and latency profile for a single model component."""
    name: str
    vram_gb: float          # approximate VRAM for weights + activations
    avg_latency_sec: float  # average per-request inference time
    notes: str = ""


@dataclass
class DeploymentScenario:
    """A particular hardware + workload configuration."""
    name: str
    gpu_type: str
    gpu_vram_gb: float
    num_gpus: int
    models: list = field(default_factory=list)  # list of ModelProfile
    concurrency_cap: int = 10
    notes: str = ""


# -- Model profiles based on published specs and our own measurements -------

WHISPER_BASE = ModelProfile(
    name="Whisper (base)",
    vram_gb=1.0,
    avg_latency_sec=0.5,
    notes="Whisper base model; 74M params.  Runs on CPU for our pilot "
          "since audio chunks are short. GPU optional."
)

LLAMA3_1_8B = ModelProfile(
    name="LLaMA 3.1 8B (4-bit quantized)",
    vram_gb=6.0,
    avg_latency_sec=4.0,
    notes="Ollama default quantization.  Full fp16 would need ~16 GB. "
          "4-bit GPTQ/GGUF brings it to ~6 GB with acceptable quality."
)

LLAVA_7B = ModelProfile(
    name="LLaVA 1.5 7B (4-bit quantized)",
    vram_gb=8.0,
    avg_latency_sec=6.0,
    notes="Vision-language model.  Image encoder (CLIP ViT-L) adds ~2 GB "
          "on top of the 7B language backbone."
)


def estimate_pilot_concurrency(
    total_students: int = 250,
    peak_fraction: float = 0.08,
    sessions_per_week: float = 2.0,
    avg_session_minutes: float = 15.0,
    semester_weeks: int = 14,
) -> Dict[str, Any]:
    """
    Estimate realistic peak concurrent usage for the 250-student pilot.

    Assumptions (documented so reviewers can challenge them):
      - This is an asynchronous tutoring tool, not a synchronous lecture.
      - Students use it at their own pace, spread across the week.
      - Peak hour is probably 8pm-11pm on weekday evenings (HKU pattern).
      - At peak, about 5-10% of enrolled students are active simultaneously.

    Returns:
        Dict with concurrency, total session, and usage estimates.
    """
    # ---------------------------------------------------------------------------
    # DESIGN DECISION: 8% peak fraction
    # ---------------------------------------------------------------------------
    # Why 8% and not 20% or 50%?
    #
    # For a synchronous tool (e.g. live voting during a lecture), you might
    # see 80%+ simultaneous usage.  But Socratic Oracle is asynchronous --
    # students open it when they are working on an assignment, not all at
    # once.  8% is conservative and aligns with usage patterns seen in
    # similar async ed-tech tools (Piazza, office-hour bots).
    #
    # If the tool becomes mandatory for an in-class exercise, this number
    # jumps dramatically, and we would need to re-estimate.
    # ---------------------------------------------------------------------------

    peak_concurrent = int(total_students * peak_fraction)
    total_sessions = int(total_students * sessions_per_week * semester_weeks)
    total_hours = total_sessions * avg_session_minutes / 60.0

    return {
        "total_students": total_students,
        "peak_concurrent_users": peak_concurrent,
        "peak_fraction": peak_fraction,
        "assumed_sessions_per_week": sessions_per_week,
        "avg_session_minutes": avg_session_minutes,
        "semester_weeks": semester_weeks,
        "total_sessions_semester": total_sessions,
        "total_usage_hours": round(total_hours, 1),
    }


def estimate_gpu_allocation(
    scenario: DeploymentScenario,
    peak_concurrent: int = 20,
    safety_margin: float = 0.20,
) -> Dict[str, Any]:
    """
    Calculate whether a given GPU allocation can serve the estimated
    peak concurrency.

    Args:
        scenario:         hardware + model configuration
        peak_concurrent:  estimated peak simultaneous inference requests
        safety_margin:    fraction of VRAM to reserve (fragmentation, OS, etc.)

    Returns:
        Dict with allocation details, headroom, and recommendation.
    """
    total_vram = scenario.num_gpus * scenario.gpu_vram_gb
    usable_vram = total_vram * (1 - safety_margin)

    model_vram = sum(m.vram_gb for m in scenario.models)

    # How many concurrent inference slots can we sustain?
    # Each slot needs the model in memory; with batching, the marginal
    # cost per extra slot is mostly KV cache (~0.5-1 GB per slot for 8B).
    kv_cache_per_slot_gb = 0.8
    slots_possible = max(1, int(
        (usable_vram - model_vram) / kv_cache_per_slot_gb
    ))

    can_serve = slots_possible >= peak_concurrent
    headroom = slots_possible - peak_concurrent

    # Throughput estimate: with N slots and average latency L, throughput
    # is roughly N / L requests per second.
    avg_latency = max(m.avg_latency_sec for m in scenario.models)
    throughput_rps = round(slots_possible / avg_latency, 2)

    return {
        "scenario": scenario.name,
        "gpu": f"{scenario.num_gpus}x {scenario.gpu_type} "
               f"({scenario.gpu_vram_gb} GB each)",
        "total_vram_gb": total_vram,
        "usable_vram_gb": round(usable_vram, 1),
        "model_vram_gb": model_vram,
        "kv_cache_per_slot_gb": kv_cache_per_slot_gb,
        "max_concurrent_slots": slots_possible,
        "peak_concurrent_needed": peak_concurrent,
        "can_serve_peak": can_serve,
        "headroom_slots": headroom,
        "throughput_rps": throughput_rps,
        "recommendation": (
            f"Sufficient. {headroom} slots of headroom."
            if can_serve
            else f"Insufficient. Need {-headroom} more slot(s). "
                 f"Consider adding GPUs or reducing model size."
        ),
    }


def generate_full_report() -> Dict[str, Any]:
    """
    Produce the complete resource estimation report combining usage
    projections and hardware scenarios.

    This is the main entry point -- call it from a route or a script and
    print/return the result.
    """
    usage = estimate_pilot_concurrency()

    # ---------------------------------------------------------------------------
    # Scenario A: Single A100 80 GB (text-only, no vision)
    # ---------------------------------------------------------------------------
    scenario_a = DeploymentScenario(
        name="Single A100 -- Text Only",
        gpu_type="NVIDIA A100",
        gpu_vram_gb=80,
        num_gpus=1,
        models=[WHISPER_BASE, LLAMA3_1_8B],
        concurrency_cap=10,
        notes="Whisper can run on CPU; A100 dedicated to LLM inference.",
    )

    # ---------------------------------------------------------------------------
    # Scenario B: Single A100 80 GB (text + vision)
    # ---------------------------------------------------------------------------
    scenario_b = DeploymentScenario(
        name="Single A100 -- Text + Vision",
        gpu_type="NVIDIA A100",
        gpu_vram_gb=80,
        num_gpus=1,
        models=[WHISPER_BASE, LLAMA3_1_8B, LLAVA_7B],
        concurrency_cap=8,
        notes="Both LLM and VLM share the A100. Concurrency drops.",
    )

    # ---------------------------------------------------------------------------
    # Scenario C: 2x A100 40 GB (common HPC configuration)
    # ---------------------------------------------------------------------------
    scenario_c = DeploymentScenario(
        name="2x A100 40 GB -- Text + Vision",
        gpu_type="NVIDIA A100",
        gpu_vram_gb=40,
        num_gpus=2,
        models=[WHISPER_BASE, LLAMA3_1_8B, LLAVA_7B],
        concurrency_cap=10,
        notes="One GPU for LLM, one for VLM. Better isolation.",
    )

    # ---------------------------------------------------------------------------
    # Scenario D: Consumer-grade (e.g. RTX 4090 24 GB) for dev/testing
    # ---------------------------------------------------------------------------
    scenario_d = DeploymentScenario(
        name="RTX 4090 24 GB -- Text Only (dev)",
        gpu_type="NVIDIA RTX 4090",
        gpu_vram_gb=24,
        num_gpus=1,
        models=[WHISPER_BASE, LLAMA3_1_8B],
        concurrency_cap=4,
        notes="Feasible for development and small-group testing.",
    )

    peak = usage["peak_concurrent_users"]
    allocations = [
        estimate_gpu_allocation(scenario_a, peak),
        estimate_gpu_allocation(scenario_b, peak),
        estimate_gpu_allocation(scenario_c, peak),
        estimate_gpu_allocation(scenario_d, peak),
    ]

    return {
        "usage_projection": usage,
        "hardware_scenarios": allocations,
        "summary": (
            f"For {usage['total_students']} students with ~{peak} peak "
            f"concurrent users, a single A100 80 GB (text-only) is "
            f"sufficient with comfortable headroom. Adding the vision "
            f"model (LLaVA) reduces concurrency headroom but remains "
            f"feasible on the same card. For production comfort, "
            f"2x A100 40 GB with model isolation is recommended."
        ),
    }


# ---------------------------------------------------------------------------
# FUTURE IMPROVEMENTS (if we had more time)
# ---------------------------------------------------------------------------
# 1. Dynamic profiling:
#    Run actual inference benchmarks on the target HPC hardware and feed
#    measured latencies back into the model.  Our current numbers are
#    educated guesses from published benchmarks.
#
# 2. Cost modeling:
#    HKU HPC charges by GPU-hour.  Adding a cost dimension would let us
#    answer "how much does this pilot cost per student per semester?"
#
# 3. Auto-scaling policy:
#    Instead of a fixed GPU allocation, define an auto-scaling rule:
#    "if queue_depth > 5 for > 2 minutes, spin up another GPU node."
#    This is standard on cloud (e.g. AWS SageMaker) but non-trivial
#    on an on-prem HPC cluster.
#
# 4. Simulation:
#    Build a discrete-event simulation of the semester workload to stress-
#    test the concurrency model before going live.
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import json
    report = generate_full_report()
    print(json.dumps(report, indent=2))
