# LocalCura Executive Summary

## Context: Local-First Vision Stack (Late 2024–Early 2025)

- Multimodal LLMs (MLLMs) and efficient ViTs now run state-of-the-art vision locally on 24 GB consumer GPUs (RTX 3090/4090), displacing hyperscale APIs while keeping privacy and zero marginal cost.
- VRAM is the hard constraint; engineering patterns (quantization, hot-swap offloading) make multi-model pipelines reliable on single-GPU workstations.

## Vision Triumvirate Architecture

- **Gatekeeper — Aesthetic Shadow v2.5 (SigLIP):** Fast aesthetic/quality scoring to discard low-value assets early. Scalar 1–10; <4.5 drop, >5.5 keep, >6.5 showcase.
- **Indexer — JoyTag (ViT multi-label):** High-throughput controlled-vocabulary tagging (5k+ tags). Threshold tuning: >0.6 for precision; <0.3 for recall; or top-K.
- **Analyst — Qwen2.5-VL-7B-Instruct:** Agentic VLM for OCR, grounding, and structured JSON metadata. Naive Dynamic Resolution preserves aspect ratio/detail; M-ROPE maintains spatial grounding. Strong JSON fidelity for database-ready outputs.

## Hardware/VRAM Profile (24 GB target)

- Qwen2.5-VL BF16 ~15 GB; JoyTag ~2 GB; Aesthetic Shadow ~2 GB; CUDA/context ~1–4 GB.
- **Hot-Swap Offloading:** Keep models on CPU; move one at a time to GPU per phase (Gate → Index → Analyze). Between phases: `gc.collect()` + `torch.cuda.empty_cache()`.
- **Quantization Option:** AWQ/INT4 for Qwen cuts to ~5–6 GB, enabling concurrent residency and higher throughput on 24 GB.

## Pipeline (LocalCura)

1. Load image.
2. Aesthetic score; exit early if below threshold.
3. JoyTag tagging (thresholded sigmoid outputs).
4. Qwen2.5-VL analysis with strict JSON system prompt (`qwen_vl_utils.process_vision_info` for dynamic resolution).
5. Persist metadata (sidecar JSON/XMP) and sync to DAM (e.g., Eagle) with tag-merge semantics to avoid overwriting manual tags.

## Operational Guidance

- Use PyTorch 2.4+ with CUDA 12.1+, Transformers 4.45+, accelerate; bitsandbytes only if quantizing.
- Defensive error handling per stage; always run VRAM cleanup in `finally`.
- Prefer BF16 + offload for compatibility; switch to AWQ when throughput is priority.

## Why Local-First Now

Comparable quality to cloud VLMs on many tasks, with total privacy, deterministic cost (electricity only), and zero latency for terabyte-scale archives.
