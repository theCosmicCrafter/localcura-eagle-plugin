# LocalCura vs Unified Eagle Tagger — Feature Comparison

**Date:** 2026-06-10

---

## Overview

| | **LocalCura** (polished) | **Unified Eagle Tagger** |
|---|---|---|
| **Origin** | CosmicTagger — Ollama-powered image tagger | Merged from LocalCura + Eagle Vault Agent + Eagle MCP Server |
| **Backend size** | `localcura.py` (~900 lines) | `main.py` (~1500 lines) + `enhanced_analyzer.py` |
| **Plugin size** | `script.js` (~50KB) | `script.js` (~33KB) |
| **Architecture** | Plugin + FastAPI server | Plugin + FastAPI server |
| **AI backend** | Ollama (Qwen3-VL) | Ollama (Qwen3-VL, LLaVA, etc.) |

---

## Features Where Unified Tagger Wins

### 1. ComfyUI/AI Metadata Extraction
**Unified:** Extracts ComfyUI workflow data, Stable Diffusion parameters, and generation metadata from PNG files automatically.
**LocalCura:** No metadata extraction.

### 2. 3-Layer Tag Verification
**Unified:** Full verification pipeline:
- Layer 1: Normalize (lowercase, dedup, strip)
- Layer 2: Filter (stopwords, length checks, blacklist)
- Layer 3: Quality scoring + categorization
**LocalCura:** Basic `cleanTags()` function with stopword list only.

### 3. Color Palette Extraction
**Unified:** Uses KMeans clustering on image pixels to extract dominant colors + accent colors + color palette classification (warm, cool, vibrant, muted, monochrome).
**LocalCura:** No color analysis.

### 4. Results Panel / Detailed UI
**Unified:** Shows per-item results with:
- Star rating display
- Aesthetic score (0-10)
- Quality score
- Description box
- Categorized tag sections (genre, lighting, color, time, subject, artist)
- Color palette visualization
**LocalCura:** Queue grid with status icons only (pending/processing/success/error).

### 5. Model Management UI
**Unified:** `/models` endpoint probes all installed Ollama models, detects vision capability, ranks by size, recommends best model.
**LocalCura:** Single hardcoded model (`qwen3-vl:8b`).

### 6. Configurable Tag Limits
**Unified:** User can set max tags (5-50), min/max tag length via UI.
**LocalCura:** Fixed tag behavior.

### 7. FFmpeg Video Processing
**Unified:** Uses FFmpeg for frame extraction (more robust, supports more formats).
**LocalCura:** Uses OpenCV (lighter weight, fewer dependencies).

### 8. Batch State Persistence to Disk
**Unified:** Saves resume state to `logs/batch_state.json` (survives plugin reload).
**LocalCura:** Saves to `eagle.storage` (lost if Eagle crashes).

### 9. ImageHash Library for Similarity
**Unified:** Uses `imagehash` library (phash, dhash, whash) with union-find grouping.
**LocalCura:** Custom aHash implementation with simple Hamming distance.

### 10. Pydantic Data Models
**Unified:** `AnalysisResult` BaseModel with typed fields, validation, comprehensive return structure.
**LocalCura:** Plain dicts.

---

## Features Where LocalCura Wins

### 1. Audio Processing
**LocalCura:** Full audio support via `mutagen` — extracts metadata (duration, bitrate, sample rate, channels, ID3 tags) and sends to Ollama for genre/mood/instrumentation analysis.
**Unified:** No audio support at all.

### 2. Security / Auth
**LocalCura:**
- API token generated on init, stored in `eagle.storage`
- Passed via `X-API-Key` header on every request
- Server middleware rejects unauthorized requests
- CORS restricted to localhost/file origins only
**Unified:**
- CORS `allow_origins=["*"]` — any website can POST to your backend
- No auth mechanism
- Security risk: malicious sites can trigger analysis

### 3. Cross-Platform Support
**LocalCura:**
- Manifest has no `platform` field (works on all OS)
- Dynamic Python path detection (venv Windows, venv Unix, system PATH)
- Settings UI for manual path override
**Unified:**
- `"platform": "win"` locks out macOS/Linux users
- Hardcoded `c:\Users\richk\...` paths
- No path auto-detection

### 4. Server-Side Batch Paths
**LocalCura:** `POST /process/batch/paths` — plugin sends file paths, backend reads files directly from disk. Eliminates file upload overhead entirely.
**Unified:** `POST /batch` — still requires multipart file uploads (sends bytes over HTTP).

### 5. Response Cache
**LocalCura:** SHA256-based LRU cache (500 entries) — re-analyzing the same image returns instantly.
**Unified:** No cache.

### 6. PID Tracking / Orphan Cleanup
**LocalCura:**
- Stores server PID on start
- Kills orphan processes on plugin load
- Force-kills with `taskkill /F /T` on Windows on stop/close
- `onPluginDestroy` handler cleans up
**Unified:**
- Basic `spawn`/`kill`
- No PID tracking
- Plugin crash = orphaned Python server
- No cleanup on unload

### 7. Keyboard Shortcuts
**LocalCura:** `Ctrl+Shift+T` triggers tagging without opening plugin window.
**Unified:** No keyboard shortcuts.

### 8. Eagle Native Progress Bar
**LocalCura:** Calls `eagle.window.setProgress()` during batch — shows progress in Eagle's taskbar/window chrome.
**Unified:** Custom DOM progress bar only.

### 9. Resume with Item IDs
**LocalCura:** Tracks processed item IDs — survives selection changes, supports partial resume.
**Unified:** Tracks `processedCount` integer — breaks if selection changes between sessions.

### 10. Plugin Settings Persistence
**LocalCura:** Settings stored in `eagle.storage` with full UI (chunk size, delays, adaptive chunking, similarity, resume, compression, backend paths).
**Unified:** Settings are mostly hardcoded or read from `.env` only.

### 11. Adaptive Chunking
**LocalCura:** Automatically adjusts batch size based on Ollama response times (fast hardware = larger chunks).
**Unified:** Fixed chunk size.

### 12. No Full UI Reload
**LocalCura:** `item.save()` updates Eagle UI without reloading — tags appear instantly.
**Unified:** Also uses `item.save()`, but may still trigger reload in some flows.

---

## Code Quality Comparison

| Aspect | LocalCura | Unified |
|---|---|---|
| **Error handling** | Inconsistent shapes (some have `retryable`, some don't) | Raises `HTTPException` with structured responses |
| **Type safety** | Plain dicts, type hints optional | Pydantic models, dataclasses, strict typing |
| **Documentation** | Minimal inline comments | Extensive docstrings, module headers |
| **Config management** | Env vars + `eagle.storage` | Env vars + `.env` + Pydantic validation |
| **Logging** | Basic logger per module | Centralized logger with file + console |
| **Test coverage** | `test_ollama.py` only | None |
| **Modularity** | Single file (`localcura.py`) | Better separation (extractors, verifiers, processors) |

---

## Recommendation

**LocalCura is the better foundation** for these reasons:
1. **Security** — auth token + restricted CORS are non-negotiable
2. **Portability** — works on all platforms, auto-detects paths
3. **Audio** — unified tagger can't handle audio at all
4. **Performance** — batch paths + cache = much faster for large collections
5. **Reliability** — PID tracking prevents zombie servers

**But Unified Tagger has features worth porting:**
1. **ComfyUI metadata extraction** — useful for AI art libraries
2. **Color palette extraction** — valuable for visual organization
3. **3-layer tag verification** — produces cleaner, more diverse tags
4. **Results panel** — much better UX for reviewing per-item analysis
5. **Model management UI** — lets users choose models
6. **Configurable tag limits** — user control over verbosity

**Best path forward:** Merge the two. Take LocalCura's security, portability, audio, and performance, then port Unified's ComfyUI extraction, color analysis, tag verification, and results UI on top of it.
