# Product Requirements Document (PRD)
# LocalCura AI for Eagle - v2.0

**Document Version:** 1.0  
**Date:** February 9, 2026  
**Status:** Draft  
**Author:** ODIN Analysis  

---

## 1. Executive Summary

### 1.1 Product Vision
LocalCura v2.0 will be the most efficient, accurate, and user-friendly local AI asset curation plugin for Eagle App, leveraging cutting-edge small vision-language models (VLMs) to provide enterprise-grade asset management capabilities entirely on-device.

### 1.2 Problem Statement
Digital asset management (DAM) tools require extensive manual tagging, leading to:
- **Inconsistent metadata** across large libraries
- **Poor discoverability** due to inadequate tagging
- **Time waste** (avg. 30-60 seconds per asset for manual tagging)
- **Privacy concerns** with cloud-based AI solutions
- **High costs** of enterprise DAM solutions ($50-200/user/month)

### 1.3 Solution
A local-first AI plugin that automatically:
- Generates descriptive tags using state-of-the-art VLMs
- Rates assets by aesthetic quality
- Extracts searchable metadata from images, videos, audio, and documents
- Operates entirely offline on consumer GPUs

---

## 2. Target Audience

### 2.1 Primary Users
1. **Creative Professionals** (50%)
   - Graphic designers, photographers, videographers
   - Libraries: 10K-500K assets
   - Pain Point: Finding specific visual styles quickly

2. **Content Teams** (30%)
   - Marketing teams, social media managers
   - Libraries: 5K-50K assets
   - Pain Point: Brand consistency across asset library

3. **Personal Power Users** (20%)
   - Hobbyists, collectors, researchers
   - Libraries: 1K-20K assets
   - Pain Point: Organization without manual effort

### 2.2 User Personas

**Persona: Alex - Freelance Photographer**
- 45K RAW + edited photos across 8 years
- Needs: Style-based discovery, client deliverable ratings
- Technical Level: Moderate (uses Lightroom, Eagle)
- Hardware: RTX 4070, 32GB RAM

**Persona: Maya - Brand Manager**
- 12K brand assets, logos, campaign materials
- Needs: Consistent tagging taxonomy, quick search
- Technical Level: Low-Moderate
- Hardware: Laptop with external GPU enclosure

---

## 3. Functional Requirements

### 3.1 Core Features (Must Have)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| F-01 | Auto-Tagging | P0 | Generate 5-15 relevant tags per asset using VLM analysis |
| F-02 | Aesthetic Rating | P0 | Score 0-10 and convert to Eagle 1-5 star ratings |
| F-03 | Multi-Modal Support | P0 | Process images, video, audio, documents |
| F-04 | Smart Batch Processing | P0 | Process multiple assets with progress tracking |
| F-05 | Tag Learning | P1 | Import existing Eagle tags for personalized vocabulary |
| F-06 | Confidence Scoring | P1 | Display confidence % for generated tags |
| F-07 | Preview Mode | P1 | Show generated tags before saving to Eagle |

### 3.2 Advanced Features (Should Have)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| F-08 | Duplicate Detection | P2 | Perceptual hashing to find similar assets |
| F-09 | Audio Captioning | P2 | Generate descriptions for music/audio files |
| F-10 | Video Scene Detection | P2 | Detect scene changes and tag per scene |
| F-11 | Custom Tag Rules | P2 | User-defined tag inclusion/exclusion patterns |
| F-12 | Resume Processing | P2 | Save progress, resume after interruption |
| F-13 | Export/Import Tags | P3 | Backup and restore tag databases |

### 3.3 Premium Features (Could Have)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| F-14 | Face Recognition | P3 | Group photos by person (privacy-safe, local) |
| F-15 | OCR & Text Extraction | P3 | Extract and tag text from images/PDFs |
| F-16 | Style Transfer Detection | P3 | Identify artistic styles applied |
| F-17 | Color Palette Extraction | P3 | Tag dominant colors per asset |

---

## 4. Non-Functional Requirements

### 4.1 Performance Requirements

| Metric | Current | Target v2.0 | Stretch |
|--------|---------|-------------|---------|
| Image processing | 2-4s | <1s | 0.5s |
| Video processing (per min) | 3-6s | 1-2s | <1s |
| Audio processing | <1s | <0.5s | <0.3s |
| Model load time | 15-30s | <10s | <5s |
| VRAM usage (peak) | 6-8GB | <3GB | <2GB |
| Concurrent processing | 1 | 3 | 5 |

### 4.2 Quality Requirements

| Metric | Target |
|--------|--------|
| Tag relevance accuracy | >85% (top-5 tags) |
| Aesthetic correlation | >0.75 (human correlation) |
| False positive rate | <5% |
| System uptime | >99% (backend) |

### 4.3 Compatibility Requirements

| Component | Requirement |
|-----------|-------------|
| OS | Windows 10/11 (primary), macOS (secondary) |
| Eagle App | v3.0+ |
| GPU | NVIDIA GTX 1060 6GB+ (minimum), RTX 3060+ (recommended) |
| RAM | 16GB minimum, 32GB recommended |
| Storage | 10GB for models + cache |

---

## 5. User Experience Requirements

### 5.1 UI/UX Guidelines

**Plugin Window:**
- Size: 450x700px (resizable)
- Theme: Match Eagle dark/light mode
- Layout: Three-panel (status, queue, settings)

**Workflow:**
1. One-click server start (auto-detect if already running)
2. Drag-and-drop or selection-based batching
3. Real-time progress with per-item status
4. Review-before-save option for power users
5. Keyboard shortcuts for common actions

### 5.2 Error Handling

| Scenario | Behavior |
|----------|----------|
| Server fail | Auto-restart with backoff, clear error message |
| GPU OOM | Fall back to CPU mode with warning |
| Model missing | Auto-download with progress indicator |
| Eagle not running | Graceful degradation, queue for later |
| Unsupported format | Skip with clear notification |

---

## 6. Integration Requirements

### 6.1 Eagle API Integration

| Endpoint | Usage |
|----------|-------|
| `/api/info` | Health check, version compatibility |
| `/api/item/list` | Get selected/current items |
| `/api/item/info` | Fetch file paths |
| `/api/item/update` | Save tags, ratings, annotations |
| `/api/library/info` | Get library path for tag learning |

### 6.2 Model Provider Integration

| Provider | Models | Usage |
|----------|--------|-------|
| Hugging Face | LFM2-VL, Moondream2 | Primary inference |
| Local Path | GGUF files | Offline fallback |
| Ollama (optional) | Various | Power user alternative |

---

## 7. Security & Privacy Requirements

### 7.1 Privacy
- **Zero cloud dependency** for core features
- **No telemetry** without explicit opt-in
- **Local model storage** only
- **No asset data leaves device**

### 7.2 Security
- Input validation on all API endpoints
- Safe file path handling (no path traversal)
- Sandboxed plugin execution (Eagle provides)

---

## 8. Success Metrics

### 8.1 User Adoption
- Target: 1,000 active users within 6 months
- Retention: >60% monthly active rate
- NPS: >40 (excellent)

### 8.2 Performance KPIs
- Avg. processing time per asset < 1 second
- Tag accuracy (user-reported) > 80%
- Crash rate < 0.1%

### 8.3 Business Metrics
- GitHub stars: 500+
- Community contributions: 10+ PRs
- Documentation completeness: 100%

---

## 9. Release Criteria

### 9.1 MVP (v2.0.0)
- [ ] LFM2-VL-1.6B integration
- [ ] Image + video + audio processing
- [ ] Basic batch processing with progress
- [ ] Windows support, Eagle 3.0+ compatible
- [ ] Documentation and setup guide

### 9.2 Stable (v2.1.0)
- [ ] Moondream2 alternative backend
- [ ] Duplicate detection
- [ ] Audio captioning (LP-MusicCaps)
- [ ] macOS support
- [ ] Resume/progress persistence

### 9.3 Feature Complete (v2.2.0)
- [ ] Custom tag rules
- [ ] OCR integration
- [ ] Video scene detection
- [ ] Plugin auto-updater
- [ ] Advanced settings UI

---

## 10. Open Questions

1. Should we support AMD GPUs via ROCm?
2. What is the Eagle App roadmap for plugin APIs?
3. Should we offer a cloud-assisted mode (opt-in only)?
4. How to handle NSFW filtering responsibly?
5. What's the licensing strategy for model weights?

---

## 11. Appendices

### 11.1 Glossary
- **VLM**: Vision-Language Model
- **DAM**: Digital Asset Management
- **GGUF**: GPT-Generated Unified Format (llama.cpp)
- **VRAM**: Video RAM (GPU memory)

### 11.2 Reference Documents
- Eagle Plugin API: https://developer.eagle.cool/plugin-api
- LFM2-VL Technical Report: https://arxiv.org/abs/2511.23404
- Moondream2 Docs: https://moondream.ai/
