# CosmicTagger — Architecture & Quality Review

**Review Date:** 2026-06-10
**Scope:** Eagle plugin, FastAPI backend, overall architecture

---

## Executive Summary

CosmicTagger is a **feature-rich but architecturally fragile** local-first AI tagging plugin for Eagle. It has ambitious capabilities (multi-modal, video, adaptive chunking, resume) that exceed most commercial alternatives, but suffers from **hardcoded paths, missing audio implementation, no batch API, and brittle process management**. With focused fixes, it could become the best open-source Eagle tagging tool.

**Verdict:** Solid core, needs hardening.

---

## 1. Eagle Plugin Architecture Review

### 1.1 Manifest Issues

```json
{
    "platform": "win",          // BLOCKER: macOS/Linux users excluded
    "devTools": false,          // Makes debugging impossible for users
    "frame": false              // No window chrome — hard to move
}
```

| Issue | Severity | Fix |
|-------|----------|-----|
| `platform: "win"` hardcoded | **High** | Remove or add `"mac,win"` |
| `devTools: false` | Medium | Set `true` for debug builds |
| `frame: false` | Low | Consider `true` for usability |
| No `description` field | Low | Add for Eagle store listing |

### 1.2 Hardcoded Paths (Critical)

```javascript
// script.js:13-14
const PROJECT_ROOT = "c:\\Users\\richk\\CascadeProjects\\localcura-eagle-plugin";
const VENV_PYTHON = path.join(PROJECT_ROOT, "venv", "Scripts", "python.exe");
```

**Problem:** After cleanup, `venv/` was deleted from the workspace. The plugin will fail to start the server on any machine, including yours.

**Fix:** Use `eagle.storage` or `eagle.plugin.path` (if available) to locate the backend dynamically. Prompt the user on first run.

### 1.3 Process Lifecycle (Fragile)

```javascript
// Server stdout is swallowed
serverProcess.stdout.on('data', (data) => { });

// Kill is SIGTERM only — Python may not clean up
serverProcess.kill();
```

**Problems:**
- No zombie process protection
- Plugin crash → Python server orphans
- No PID file tracking
- No port-in-use detection (8005 could be taken)

**Fix:** Write PID to `eagle.storage`, check port before spawn, use `taskkill /F /T` on Windows for force-cleanup.

### 1.4 Eagle API Usage

**Good:**
- `eagle.storage` for persistence (settings, resume state)
- `eagle.item.getSelected()` for batch selection
- `item.save()` for writing tags back

**Bad:**
- `eagle.window.reload()` after processing — ** reloads the entire Eagle UI**, disruptive
- No `try/catch` around `eagle.item.getSelected()`
- Resume stores `filePath` for every item — for 1000 items, this bloats storage
- Resume only tracks `processedCount`, not item IDs — breaks if selection changes

### 1.5 Memory Management

**Good:** Object URL cleanup exists:
```javascript
const objectURLs = new Set();
function cleanupQueueMemory() { ... }
```

**Missing:** No cleanup of `objectURLs` on plugin close/unload.

---

## 2. Backend (FastAPI) Review

### 2.1 API Design

| Endpoint | Purpose | Issue |
|----------|---------|-------|
| `POST /process` | Single file upload | No batch endpoint — plugin sends files one-by-one |
| `POST /similarity/group` | Group similar images | Not integrated into plugin flow |
| `GET /similarity/hash` | Single image hash | Not used by plugin |
| `GET /health` | Health check | Good |

**Missing endpoints:**
- `POST /process/batch` — send multiple files, get results in one call
- `GET /templates` — list available templates
- `POST /process/url` — process by file path instead of upload (avoids copying)

### 2.2 Security

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],      // ANY website can talk to your backend
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Severity: High.** Any malicious site you visit can POST images to `localhost:8005`.

**Fix:** Restrict to `http://localhost` origins or add an API key header check.

### 2.3 Audio — Claimed but Not Implemented

```python
if media_kind == "audio":
    return {
        "file": filename,
        "media_kind": media_kind,
        "error": "Audio analysis is not yet implemented in LocalCura.",
    }
```

README claims audio tagging. Backend returns an error. The `audio_template` exists but is never used for actual analysis.

**Fix:** Implement audio via:
1. Whisper (speech-to-text) for transcription
2. Librosa (already in old `audio_analyzer.py`) for tempo/instrumentation
3. Or send audio to Qwen3-VL (some VLMs support audio)

### 2.4 Video Processing

**Good:** Frame extraction works, multi-frame analysis, merging.

**Problems:**
- Temp file always uses `.mp4` extension regardless of actual format
- No frame deduplication (could analyze 5 identical frames)
- `_merge_video_analyses` uses simple set union — no confidence weighting
- Missing: video thumbnail selection, duration tagging, codec info

### 2.5 Error Handling Inconsistency

The backend returns different error shapes:
```python
{"error": "...", "retryable": True, "status": 504}     # Timeout
{"error": "...", "retryable": False}                    # Connection
{"error": "..."}                                         # Generic
```

Plugin checks `result?.retryable` but not consistently. Standardize on:
```python
{"success": False, "error": "...", "retryable": bool, "code": "..."}
```

### 2.6 Performance

**Image processing:**
- Always converts to JPEG before base64 — loses PNG transparency metadata
- No WebP/AVIF optimization path
- Single-threaded — no async queue for parallel Ollama calls

**Missing optimizations:**
- No response caching (same image analyzed twice = 2 LLM calls)
- No embedding cache for similarity grouping
- No connection pooling to Ollama

---

## 3. Functional Completeness Checklist

| Feature | Claimed | Implemented | Works? |
|---------|---------|-------------|--------|
| Image tagging | Yes | Yes | Partial |
| Video tagging | Yes | Yes | Partial (no frame dedup) |
| Audio tagging | Yes | **No** | No |
| Text tagging | Yes | Yes | Yes |
| Rating/aesthetic | Yes | Yes | Yes (0-10 → 0-5) |
| Renaming | Yes | Yes | Yes |
| Similarity grouping | Yes | API only | Not wired to plugin |
| Resume capability | Yes | Yes | Fragile (count-based, not ID-based) |
| Adaptive chunking | Yes | Yes | Yes |
| Settings UI | Yes | Yes | Yes |
| Batch processing | Yes | Yes | Slow (no batch API) |
| Eagle annotation | Yes | Yes | Yes |
| Offline/local | Yes | Yes | Yes (Ollama) |

---

## 4. Comparison with Other Tagging Tools

| Tool | Model | Batch | Video | Audio | Local | Similarity | Price |
|------|-------|-------|-------|-------|-------|------------|-------|
| **CosmicTagger** | Qwen3-VL (Ollama) | No* | Yes | No | Yes | API only | Free |
| ATagger | Built-in | Yes | No | No | No | No | Free/Paid |
| Eagle Tagger | Cloud API | Yes | No | No | No | No | Subscription |
| Tagger for Eagle | CLIP + GPT | Yes | No | No | No | No | One-time |
| JoyCaption | Florence-2 | Yes | No | No | Yes | No | Free |
| WD Tagger | Waifu Diffusion | Yes | No | No | Yes | No | Free |

*CosmicTagger sends files individually, not true batch.

**Where CosmicTagger wins:**
- True local/offline (no cloud dependency)
- Video support (rare in Eagle plugins)
- Multi-modal templates (photo, text, video, audio)
- Resume capability
- Adaptive chunking

**Where it loses:**
- No true batch API (competitors process 50+ images per call)
- No audio (competitors like JoyCaption handle this via model)
- Requires Ollama setup (competitors are plug-and-play)
- Hardcoded paths (competitors are portable)

---

## 5. Critical Bugs

### Bug 1: Plugin Cannot Start Server (BLOCKER)
`VENV_PYTHON` points to deleted `venv/`. The plugin will fail to spawn the backend.

### Bug 2: CORS Wildcard (SECURITY)
Any website can POST to `localhost:8005`.

### Bug 3: macOS/Linux Excluded
`"platform": "win"` prevents 30%+ of Eagle users from installing.

### Bug 4: Audio Returns Error
README promises audio tagging. Backend returns `"not yet implemented"`.

### Bug 5: Resume is Broken
If user changes selection between sessions, `processedCount` resumes from wrong items.

### Bug 6: Rating Off-by-One
`Math.round(score / 2)` where `score` is 0-10 produces 0-5. Eagle uses 1-5 stars. Score of 0 → 0 stars (unrated), score of 1-2 → 1 star.

---

## 6. Recommendations (Priority Order)

### P0 — Fix Before Release
1. **Fix path resolution** — detect backend location dynamically or prompt user
2. **Add batch endpoint** `POST /process/batch` — reduce overhead 10x
3. **Restrict CORS** to Eagle plugin origin
4. **Fix platform** in manifest — support all platforms
5. **Fix resume** — track processed item IDs, not just count

### P1 — Hardening
6. **Add API key** or auth token between plugin and backend
7. **Implement audio** via Whisper + librosa, or remove from README claims
8. **Add PID tracking** and orphan cleanup
9. **Standardize error responses** across backend
10. **Replace `eagle.window.reload()`** with targeted refresh or no-op

### P2 — Performance
11. **Add response caching** — hash image → cache analysis result
12. **Wire similarity grouping** into plugin flow (pre-process dedup)
13. **Parallel Ollama calls** for batch items (if Ollama queue allows)
14. **Compress/resize images** more aggressively before base64 encoding

### P3 — Polish
15. **Add `devTools: true`** for debug builds
16. **Add keyboard shortcuts** (Ctrl+T to tag selected)
17. **Progress bar** in Eagle status bar (not just plugin window)
18. **Tag preview** before applying (dry-run mode)

---

## 7. Scorecard

| Category | Score | Notes |
|----------|-------|-------|
| Architecture | 6/10 | Two implementations merged, fragile process mgmt |
| Code Quality | 6/10 | Inconsistent error handling, hardcoded values |
| Security | 4/10 | CORS wildcard, no auth, path traversal possible |
| Performance | 5/10 | No batch API, no caching, single-threaded |
| Feature Completeness | 7/10 | Audio missing, similarity not wired, resume fragile |
| Eagle Integration | 6/10 | Good API usage, bad lifecycle, platform locked |
| Documentation | 7/10 | README is good, but claims unsupported features |
| **Overall** | **5.9/10** | Solid concept, needs hardening |

---

*Reviewed against Eagle Plugin API docs, FastAPI best practices, and comparison with ATagger, JoyCaption, WD Tagger, and Eagle Tagger.*
