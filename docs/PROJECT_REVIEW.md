# LocalCura Eagle Plugin - Comprehensive Project Review

## Project Overview

**LocalCura** is a local-first AI tagging and analysis plugin for [Eagle App](https://eagle.cool/) that provides automated asset curation capabilities entirely offline on the user's GPU.

### Current Version: 1.0.0
**Codename:** CosmicTagger

---

## What It Does

LocalCura automatically processes digital assets in Eagle libraries with the following capabilities:

### Core Features

1. **Automated Tagging**
   - Uses CLIP (ViT-L/14) for zero-shot image classification
   - Extracts subjects, visual styles, and content descriptors
   - Learns from existing Eagle library tags for personalized vocabulary

2. **Aesthetic Scoring**
   - Employs `cafeai/cafe_aesthetic` (Aesthetic Shadow v2.5) model
   - Scores images 0-10 and maps to Eagle's 1-5 star rating system
   - Threshold filtering (default: 4.5) for quality control

3. **Visual Language Analysis (VLM)**
   - Uses Qwen2.5-VL-7B-Instruct (GGUF quantized via llama-cpp-python)
   - Generates detailed summaries, subject extraction, style classification
   - NSFW content detection for safety filtering
   - OCR capabilities for text-heavy images

4. **Audio Analysis**
   - BPM and tempo detection via librosa
   - Duration classification (short/medium/long)
   - Acoustic feature extraction (brightness, noise floor)
   - Genre hints based on spectral characteristics

5. **Video Support**
   - Multi-frame extraction (3 keyframes sampled)
   - Aggregated tagging across frames
   - Middle-frame aesthetic assessment

6. **Document Processing**
   - PDF first-page rendering
   - Text/Markdown/Word document analysis
   - OCR for scanned documents

### Supported File Formats

| Type | Extensions |
|------|-----------|
| Images | jpg, jpeg, png, webp, gif, bmp, svg, avif, heic, exr |
| Video | mp4, mov, avi, mkv, webm |
| Audio | mp3, wav, ogg, flac, m4a |
| Documents | pdf, txt, md, docx, json, yaml, csv |

---

## Architecture Overview

### System Components

```
┌─────────────────────────────────────────────────────────────────┐
│                     EAGLE APP (Host)                            │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              CosmicTagger Plugin (Electron)               │  │
│  │  ┌────────────────────────────────────────────────────┐  │  │
│  │  │              UI Layer (HTML/CSS/JS)                 │  │  │
│  │  │  - Server controls, Batch queue, Progress tracking │  │  │
│  │  └────────────────────────────────────────────────────┘  │  │
│  │                        ↕ API Calls                        │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ HTTP (localhost:8000)
                              ↓
┌─────────────────────────────────────────────────────────────────┐
│                    LOCALCURA BACKEND (Python)                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   FastAPI   │  │  Pipeline   │  │      AI Engines         │  │
│  │   Server    │→ │  Orchestrator│→ │  ┌─────┐ ┌─────┐ ┌──┐ │  │
│  │             │  │             │  │  │Aesth│ │Tagger│ │VLM│ │  │
│  └─────────────┘  └─────────────┘  │  │etic │ │      │ │   │ │  │
│                                     │  └─────┘ └─────┘ └──┘ │  │
│                                     │  ┌─────┐ ┌─────────┐   │  │
│                                     │  │Audio│ │ File    │   │  │
│                                     │  │     │ │ Preproc │   │  │
│                                     │  └─────┘ └─────────┘   │  │
│                                     └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | HTML5, Vanilla JS, CSS3 |
| **Plugin Runtime** | Eagle Plugin API (Node.js/Electron) |
| **Backend API** | FastAPI + Uvicorn |
| **ML Framework** | PyTorch + Transformers |
| **VLM Inference** | llama-cpp-python (GGUF) |
| **Audio Processing** | librosa + numpy |
| **Video Processing** | OpenCV |
| **Document Processing** | pypdfium2, python-docx |

### Model Stack

| Component | Model | Size | Purpose |
|-----------|-------|------|---------|
| Aesthetic Scoring | cafeai/cafe_aesthetic | ~1.2GB | Image quality assessment |
| Tagging | CLIP ViT-L/14 (local) | ~1.6GB | Zero-shot classification |
| VLM | Qwen2.5-VL-7B-Instruct-GGUF | ~4-6GB | Vision-language understanding |
| Audio | librosa (heuristics) | N/A | Audio feature extraction |

---

## Key Files and Structure

```
localcura-eagle-plugin/
├── eagle_plugin/              # Eagle plugin UI
│   ├── manifest.json           # Plugin metadata
│   ├── index.html             # Main UI (400x600px)
│   ├── script.js              # Plugin logic, server management
│   └── logo.png               # Plugin branding
├── backend/                   # Python AI backend
│   ├── localcura.py           # Main orchestrator (~1070 lines)
│   ├── audio_analyzer.py      # Audio processing
│   ├── requirements.txt       # Dependencies
│   └── setup.py               # Installation script
├── eagle_bridge.py            # Python bridge for Eagle API
├── eagle_integration.py       # Eagle API client wrapper
└── venv/                      # Python virtual environment
```

---

## Current Implementation Details

### VRAM Management
- Hot-swap system for loading/unloading models between GPU and CPU
- Sequential processing to avoid memory spikes
- Automatic cleanup after each inference

### API Endpoints
| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check, device status |
| `/process` | POST | Main processing endpoint (multipart/form-data) |

### Configuration System
- Environment variables via `.env` file
- Auto-detection of model paths
- HF_TOKEN support for gated models

### Tag Learning
- Automatically imports tags from Eagle's `tags.json`
- Prioritizes user's existing tag vocabulary
- Fallback to default generic labels

---

## Identified Gaps and Improvement Opportunities

### 1. Model Selection & Performance

| Issue | Current | Opportunity |
|-------|---------|-------------|
| VLM Model | Qwen2.5-VL-7B-GGUF (~4-6GB) | **Liquid AI LFM2-VL-450M** (~450M params, 2x faster, comparable accuracy) |
| Tagger | CLIP ViT-L/14 | **Moondream2** (2B params, purpose-built for captioning) |
| Aesthetic | cafe_aesthetic (external HF) | Local cached model or smaller alternative |

### 2. Missing Capabilities

| Capability | Status | Recommendation |
|------------|--------|----------------|
| **Video Captioning** | Partial (frame extraction only) | Add full video understanding with temporal analysis |
| **Audio Intelligence** | Basic (BPM/tempo) | Add full audio captioning with LP-MusicCaps style models |
| **Duplicate Detection** | ❌ Missing | Add perceptual hashing + similarity search |
| **Batch Processing Optimization** | Sequential | Implement parallel processing with semaphore control |
| **Progress Persistence** | In-memory only | Add SQLite state management for resume capability |
| **Custom Tag Rules** | ❌ Missing | User-defined tag inclusion/exclusion rules |
| **Plugin Auto-Update** | ❌ Missing | Implement version checking + update mechanism |

### 3. Architecture Improvements

| Area | Current | Recommended |
|------|---------|-------------|
| **State Management** | In-memory | SQLite + caching layer |
| **Configuration** | .env + env vars | YAML config with GUI editor |
| **Error Handling** | Basic try/catch | Structured error taxonomy + retry logic |
| **Logging** | File + console | Structured JSON logging with rotation |
| **Testing** | ❌ None | Unit tests + integration tests |
| **Documentation** | Basic README | API docs, user guide, developer docs |

### 4. UX Enhancements

| Feature | Priority | Description |
|---------|----------|-------------|
| **Real-time Preview** | High | Show generated tags before saving |
| **Tag Confidence Scores** | High | Display confidence % for each tag |
| **Custom Prompt Templates** | Medium | Allow user-defined VLM prompts |
| **Keyboard Shortcuts** | Medium | Quick tagging shortcuts |
| **Dark/Light Theme** | Low | Theme switching support |

---

## Eagle Plugin Best Practices (2025)

Based on official Eagle Plugin API documentation:

### Recommended Patterns
1. **Use `eagle.window.hide()`** instead of closing for persistent state
2. **Implement proper error boundaries** with user-friendly messages
3. **Leverage `eagle.onPluginCreate`** for initialization
4. **Use `eagle.item.getSelected()`** for current selection awareness
5. **Auto-reload with `eagle.window.reload()`** after bulk operations

### API Surface (Current Usage)
- `eagle.item.getSelected()` - Get current selection
- `eagle.item.update()` - Save changes to items
- `eagle.library.path` - Library location for tag learning
- `eagle.window.reload()` - Refresh Eagle UI
- `eagle.window.hide()` - Close plugin window

### Compliance Issues
- Plugin window size (400x600) is reasonable but could be resizable
- No persistent plugin state between sessions
- Limited integration with Eagle's native tagging UI

---

## Research Summary: Modern AI Models for Asset Captioning

### Vision-Language Models (2025)

| Model | Params | Speed | Accuracy | Best For |
|-------|--------|-------|----------|----------|
| **LFM2-VL-450M** | 450M | ⭐⭐⭐⭐⭐ Fast | Good | Edge deployment, real-time |
| **LFM2-VL-1.6B** | 1.6B | ⭐⭐⭐⭐ Very Fast | Very Good | Balanced speed/quality |
| **Moondream2** | 2B | ⭐⭐⭐⭐ Fast | Very Good | Captioning specialist |
| **Qwen2.5-VL-3B** | 3B | ⭐⭐⭐ Moderate | Excellent | Long context, documents |
| **Qwen2.5-VL-7B** | 7B | ⭐⭐ Slower | Outstanding | Maximum quality |
| **SmolVLM-500M** | 500M | ⭐⭐⭐⭐⭐ Very Fast | Good | Ultra-compact |

### Recommendation for LocalCura
**Primary:** LFM2-VL-1.6B (best speed/accuracy tradeoff)
**Secondary:** Moondream2 (if captioning quality is paramount)
**Fallback:** Qwen2.5-VL-3B (for document-heavy workflows)

### Audio Models (2025)

| Model/Approach | Description | Recommendation |
|----------------|-------------|----------------|
| **LP-MusicCaps** | LLM-based music captioning | Add for music description |
| **Audio-LLaMA** | Audio understanding | For general audio analysis |
| **Whisper + CLAP** | Speech + audio classification | For podcasts, interviews |

### Video Models (2025)

| Approach | Description | Status |
|----------|-------------|--------|
| **Keyframe + VLM** | Current implementation | Working |
| **Video-LLaMA/Video-Chat** | Native video understanding | Emerging |
| **Qwen2.5-VL temporal** | Time-aware video analysis | Recommended upgrade |

---

## Performance Benchmarks (Estimated)

### Current Stack (Qwen2.5-VL-7B-GGUF)
- **Load Time:** 15-30s (model initialization)
- **Image Processing:** 2-4s per image (RTX 3060 12GB)
- **VRAM Usage:** 6-8GB peak
- **Audio Processing:** <1s per file
- **Video Processing:** 3-6s per file (3 frames)

### Proposed Stack (LFM2-VL-1.6B)
- **Load Time:** 5-10s (faster initialization)
- **Image Processing:** 0.5-1s per image
- **VRAM Usage:** 2-3GB peak
- **Audio Processing:** <1s per file
- **Video Processing:** 1-2s per file

---

## Next Steps

See the following documents for detailed implementation plans:
1. **PRD.md** - Product Requirements Document
2. **PDR.md** - Product Design Review (Technical Specifications)
3. **DEVELOPMENT_PLAN.md** - Milestone-based development roadmap
