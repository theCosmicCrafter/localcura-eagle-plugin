# Product Design Review (PDR)
# LocalCura AI for Eagle - Technical Specifications v2.0

**Document Version:** 1.0  
**Date:** February 9, 2026  
**Status:** Draft  

---

## 1. Architecture Overview

### 1.1 System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EAGLE APPLICATION                                  │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    PLUGIN RENDERER (Electron)                         │  │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────────────┐ │  │
│  │  │   UI Layer      │  │  State Manager  │  │    Eagle API Client    │ │  │
│  │  │  (HTML/CSS/JS)  │  │   (Redux-like)  │  │     (REST Wrapper)     │ │  │
│  │  └─────────────────┘  └─────────────────┘  └────────────────────────┘ │  │
│  │           ↓                    ↓                       ↓            │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │              PLUGIN CONTROLLER (Node.js Process)                  │ │  │
│  │  │   - Server lifecycle management                                   │ │  │
│  │  │   - IPC with backend                                              │ │  │
│  │  │   - Event handling                                                │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       │ HTTP/REST
                                       ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                         LOCALCURA BACKEND (Python)                           │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                      API LAYER (FastAPI)                              │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌───────────┐ │  │
│  │  │  /health     │  │  /process    │  │  /batch      │  │  /config  │ │  │
│  │  │  GET         │  │  POST        │  │  POST        │  │  GET/PUT  │ │  │
│  │  └──────────────┘  └──────────────┘  └──────────────┘  └───────────┘ │  │
│  │         ↓                 ↓                  ↓                      │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │                    PIPELINE ORCHESTRATOR                          │ │  │
│  │  │   - File type detection                                           │ │  │
│  │  │   - Router to specialized processors                                │ │  │
│  │  │   - Result aggregation                                            │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  │         ↓              ↓              ↓              ↓              │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │  │
│  │  │  IMAGE   │  │  VIDEO   │  │  AUDIO   │  │ DOCUMENT │  │  TEXT   │ │  │
│  │  │ PROCESSOR│  │ PROCESSOR│  │ PROCESSOR│  │PROCESSOR │  │PROCESSOR│ │  │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │  │
│  │       │             │             │             │             │       │  │
│  │  ┌────▼─────────────▼─────────────▼─────────────▼─────────────▼────┐ │  │
│  │  │                   MODEL INFERENCE ENGINE                        │ │  │
│  │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐ │ │  │
│  │  │  │  LFM2-VL   │  │ Aesthetic  │  │   CLIP     │  │  Audio   │ │ │  │
│  │  │  │  (VLM)     │  │  Scorer    │  │  (Tagger)  │  │ Analyzer │ │ │  │
│  │  │  └────────────┘  └────────────┘  └────────────┘  └──────────┘ │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  │                               ↑                                      │  │
│  │  ┌──────────────────────────────────────────────────────────────────┐ │  │
│  │  │                    VRAM MANAGER (Hot-Swap)                        │ │  │
│  │  │   - Load/unload models on demand                                  │ │  │
│  │  │   - Memory pressure handling                                    │ │  │
│  │  │   - Queue management                                              │ │  │
│  │  └──────────────────────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 Technology Stack

| Layer | Technology | Version | Purpose |
|-------|-----------|---------|---------|
| **Frontend** | HTML5 + CSS3 | - | UI rendering |
| **Plugin Runtime** | Node.js (Electron) | v18+ | Eagle plugin host |
| **Backend Framework** | FastAPI | 0.104+ | API server |
| **ASGI Server** | Uvicorn | 0.23+ | HTTP server |
| **ML Framework** | PyTorch | 2.1+ | Deep learning |
| **Transformers** | Hugging Face | 4.45+ | Model loading |
| **VLM Backend** | Transformers / llama-cpp | latest | VLM inference |
| **Audio** | librosa + numpy | 0.10+ | Audio analysis |
| **Video** | OpenCV | 4.8+ | Frame extraction |
| **Documents** | pypdfium2 + python-docx | latest | Doc processing |
| **Database** | SQLite | 3.39+ | State persistence |
| **Cache** | diskcache | latest | Model cache |

---

## 2. Component Specifications

### 2.1 Plugin Frontend (`eagle_plugin/`)

#### File Structure
```
eagle_plugin/
├── manifest.json          # Plugin metadata
├── index.html            # Main UI template
├── script.js             # Core logic (refactored to modules)
├── styles.css            # Extracted styles
├── components/
│   ├── ServerControl.jsx # Server start/stop UI
│   ├── BatchQueue.jsx    # Queue visualization
│   ├── TagPreview.jsx    # Tag preview panel
│   └── Settings.jsx      # Configuration panel
└── assets/
    ├── logo.png
    └── icons/
```

#### Key Classes

**PluginStateManager**
```javascript
class PluginStateManager {
  constructor() {
    this.state = {
      serverStatus: 'stopped', // stopped | starting | running | error
      backendOnline: false,
      isProcessing: false,
      queue: [], // Array<QueueItem>
      settings: {},
      stats: {
        processedToday: 0,
        totalProcessed: 0
      }
    };
    this.listeners = new Set();
  }
  
  subscribe(callback) { this.listeners.add(callback); }
  dispatch(action) { /* Redux-style actions */ }
  persist() { /* Save to localStorage */ }
}
```

**ServerManager**
```javascript
class ServerManager {
  async start(libraryPath) { /* Spawn Python process */ }
  async stop() { /* Kill process gracefully */ }
  async healthCheck() { /* Poll /health endpoint */ }
  onCrash(callback) { /* Handle unexpected exits */ }
}
```

### 2.2 Backend API (`backend/`)

#### API Endpoints

| Endpoint | Method | Request | Response | Description |
|----------|--------|---------|----------|-------------|
| `/health` | GET | - | `{"status": "ok", "device": "cuda", "models_loaded": true}` | Health check |
| `/process` | POST | `multipart/form-data` with `file` | ProcessingResult | Single file processing |
| `/batch` | POST | `{"items": [...], "options": {}}` | BatchResult | Batch processing |
| `/config` | GET/PUT | Config object | Config object | Get/update config |
| `/models` | GET | - | `{"available": [...], "loaded": [...]}` | Model status |
| `/tags/suggest` | POST | `{"partial": "str"}` | `{"suggestions": [...]}` | Tag autocomplete |

#### Data Models (Pydantic)

```python
class ProcessingResult(BaseModel):
    file: str
    type: Literal["image", "video", "audio", "document", "text"]
    tags: List[str]
    confidence_scores: Dict[str, float]
    aesthetic_score: Optional[float]
    aesthetic_rating: Optional[int]  # 1-5
    summary: Optional[str]
    metadata: Dict[str, Any]
    processing_time_ms: int
    model_version: str

class BatchResult(BaseModel):
    job_id: str
    total: int
    completed: int
    failed: int
    results: List[ProcessingResult]
    errors: List[Dict[str, str]]
```

### 2.3 Pipeline Processors

#### ImageProcessor
```python
class ImageProcessor:
    """Handles all image file types."""
    
    supported_formats = {'.jpg', '.jpeg', '.png', '.webp', '.gif', '.bmp', 
                        '.svg', '.avif', '.heic', '.exr'}
    
    async def process(self, filepath: Path, options: dict) -> ProcessingResult:
        image = self._load_image(filepath)
        
        # Parallel processing where possible
        results = await asyncio.gather(
            self._tag(image),
            self._score_aesthetic(image),
            self._analyze_vlm(image, options.get('vlm_depth', 'standard'))
        )
        
        return self._aggregate_results(results)
    
    def _load_image(self, filepath: Path) -> Image.Image:
        # Handle EXR/HDR, AVIF, HEIC via plugins
        # Normalize to RGB
        pass
```

#### VideoProcessor
```python
class VideoProcessor:
    """Extracts frames and generates video-aware tags."""
    
    async def process(self, filepath: Path, options: dict) -> ProcessingResult:
        # Scene detection
        scenes = self._detect_scenes(filepath)
        
        # Extract keyframes
        keyframes = self._extract_keyframes(filepath, scenes, max_frames=5)
        
        # Process each frame
        frame_results = []
        for frame in keyframes:
            result = await self._image_processor.process_frame(frame)
            frame_results.append(result)
        
        # Aggregate tags across frames
        # Detect temporal features (motion, transitions)
        return self._aggregate_video_results(frame_results)
```

#### AudioProcessor
```python
class AudioProcessor:
    """Enhanced audio analysis with ML-based captioning."""
    
    def __init__(self):
        self.basic_analyzer = LibrosaAnalyzer()
        self.captioner = Optional[MusicCaptioner]  # LP-MusicCaps
    
    async def process(self, filepath: Path) -> ProcessingResult:
        # Basic features (BPM, duration, spectral)
        features = self.basic_analyzer.analyze(filepath)
        
        # ML-based caption if available
        caption = None
        if self.captioner:
            caption = await self.captioner.generate(filepath)
        
        return ProcessingResult(
            type="audio",
            tags=self._generate_tags(features, caption),
            summary=caption or features.summary,
            metadata=features.to_dict()
        )
```

---

## 3. AI Model Specifications

### 3.1 Primary VLM: LFM2-VL-1.6B

| Attribute | Specification |
|-----------|--------------|
| **Model** | LiquidAI/LFM2-VL-1.6B |
| **Parameters** | 1.6B (active) |
| **Context** | 32K tokens |
| **Vision Encoder** | SigLIP2 NaFlex (400M) |
| **Input Resolution** | Up to 512x512 native, patch-based for larger |
| **Quantization** | BF16 (native), supports INT8 |
| **VRAM Required** | ~2.5GB |
| **Inference Speed** | ~100 tokens/sec (RTX 3060) |
| **License** | Commercial use allowed |

**Integration:**
```python
from transformers import AutoModelForVision2Seq, AutoProcessor

class LFM2VLEngine:
    def __init__(self, model_path: str):
        self.model = AutoModelForVision2Seq.from_pretrained(
            model_path,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )
        self.processor = AutoProcessor.from_pretrained(model_path)
    
    def analyze(self, image: Image.Image, prompt: str) -> dict:
        inputs = self.processor(image, prompt, return_tensors="pt")
        outputs = self.model.generate(**inputs, max_new_tokens=512)
        return self.processor.decode(outputs[0])
```

### 3.2 Alternative VLM: Moondream2

| Attribute | Specification |
|-----------|--------------|
| **Model** | vikhyatk/moondream2 |
| **Parameters** | 2B |
| **Specialty** | Image captioning, visual Q&A |
| **Quantization** | 4-bit available (~1GB) |
| **VRAM Required** | 2-4GB |
| **Speed** | Faster than LFM2-VL for captioning |
| **License** | Apache 2.0 |

### 3.3 Tagger: CLIP + Custom Labels

| Attribute | Specification |
|-----------|--------------|
| **Base Model** | openai/clip-vit-large-patch14 |
| **Label Source** | Eagle library tags.json + defaults |
| **Top-K** | 6-10 tags |
| **Confidence Threshold** | 0.25 |
| **VRAM** | ~1GB (can run on CPU) |

### 3.4 Aesthetic Scorer

| Attribute | Specification |
|-----------|--------------|
| **Model** | cafeai/cafe_aesthetic or LAION aesthetic predictor |
| **Input** | 224x224 RGB |
| **Output** | 0-10 score |
| **Mapping** | 8-10 = 5 stars, 7-8 = 4 stars, etc. |

### 3.5 Audio Captioner (Future)

| Attribute | Specification |
|-----------|--------------|
| **Model** | LP-MusicCaps style (music-specific) |
| **Alternative** | Audio-LLaMA (general audio) |
| **Approach** | Spectrogram + captioning VLM |

---

## 4. Database Schema

### 4.1 SQLite Schema

```sql
-- Processing jobs for resume capability
CREATE TABLE jobs (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    total_items INTEGER,
    completed_items INTEGER,
    options TEXT -- JSON
);

-- Individual item processing results
CREATE TABLE job_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT REFERENCES jobs(id),
    eagle_item_id TEXT,
    file_path TEXT,
    status TEXT CHECK(status IN ('pending', 'processing', 'completed', 'failed')),
    result TEXT, -- JSON ProcessingResult
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Tag frequency for analytics
CREATE TABLE tag_stats (
    tag TEXT PRIMARY KEY,
    count INTEGER DEFAULT 0,
    last_used TIMESTAMP
);

-- Settings
CREATE TABLE settings (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. Configuration System

### 5.1 Configuration Hierarchy

1. **Default config** (embedded)
2. **User config file** (`~/.localcura/config.yaml`)
3. **Environment variables**
4. **Runtime API changes** (per-session)

### 5.2 Configuration Schema

```yaml
# config.yaml
models:
  vlm:
    provider: "lfm2-vl"  # or "moondream", "qwen"
    model_path: "~/.localcura/models/lfm2-vl-1.6b"
    device: "auto"  # auto, cuda, cpu
    quantization: "bf16"  # bf16, int8, int4
  
  tagger:
    enabled: true
    label_source: "eagle"  # eagle, file, default
    label_file: null
    top_k: 8
  
  aesthetic:
    enabled: true
    threshold: 4.5
    model: "cafe_aesthetic"

processing:
  max_concurrent: 1
  offload_models: true
  auto_download_models: true
  supported_formats:
    image: [".jpg", ".png", ".webp"]
    video: [".mp4", ".mov"]
    audio: [".mp3", ".wav"]
    document: [".pdf", ".docx"]

ui:
  preview_mode: true
  theme: "auto"  # auto, dark, light
  tag_confidence_threshold: 0.3
  keyboard_shortcuts:
    process_selected: "Ctrl+P"
    stop_processing: "Ctrl+Shift+C"

advanced:
  vram_limit_gb: 6
  log_level: "INFO"
  health_check_interval_sec: 2
```

---

## 6. Error Handling Strategy

### 6.1 Error Taxonomy

| Code | Category | Retry Strategy | User Message |
|------|----------|----------------|--------------|
| E001 | Model Load Failed | Backoff 3x | "Failed to load AI model. Retrying..." |
| E002 | GPU OOM | Fallback to CPU | "GPU memory full. Switching to CPU mode (slower)." |
| E003 | File Read Error | Skip | "Could not read file. Skipping." |
| E004 | Model Inference Error | Skip + Log | "AI analysis failed for this file." |
| E005 | Eagle API Error | Retry 3x | "Eagle connection issue. Retrying..." |
| E006 | Server Crash | Auto-restart | "Server crashed. Restarting..." |

### 6.2 Circuit Breaker Pattern

```python
class CircuitBreaker:
    """Prevents cascade failures."""
    
    def __init__(self, failure_threshold=5, recovery_timeout=30):
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
        
    async def call(self, func, *args):
        if self.state == "OPEN":
            raise CircuitOpenError("Service temporarily unavailable")
        
        try:
            result = await func(*args)
            self.on_success()
            return result
        except Exception as e:
            self.on_failure()
            raise
```

---

## 7. Performance Optimizations

### 7.1 Caching Strategy

| Cache Type | Key | TTL | Storage |
|------------|-----|-----|---------|
| Model weights | model_name + quantization | Infinite | Disk ( HuggingFace cache) |
| Tag embeddings | label_hash | Infinite | Disk (numpy) |
| File results | file_hash + model_version | 7 days | SQLite |
| Tag suggestions | prefix | 1 hour | Memory |

### 7.2 VRAM Management

```python
class VRAMManager:
    """Hot-swap models to stay within budget."""
    
    def __init__(self, budget_gb: float):
        self.budget_bytes = budget_gb * 1e9
        self.loaded_models = {}
        self.access_times = {}
    
    async def load(self, name: str, loader: Callable):
        required = self._estimate_size(name)
        
        while self._current_usage() + required > self.budget_bytes:
            # Evict least recently used
            await self._evict_lru()
        
        model = loader()
        self.loaded_models[name] = model
        self.access_times[name] = time.time()
        return model
    
    async def _evict_lru(self):
        lru = min(self.access_times, key=self.access_times.get)
        del self.loaded_models[lru]
        del self.access_times[lru]
        torch.cuda.empty_cache()
```

---

## 8. Testing Strategy

### 8.1 Test Pyramid

| Level | Coverage Target | Tools |
|-------|-----------------|-------|
| Unit | 80% | pytest, pytest-asyncio |
| Integration | 60% | pytest + TestClient |
| E2E | 30% | Playwright (plugin UI) |

### 8.2 Key Test Cases

```python
# tests/test_pipeline.py
class TestImageProcessor:
    async def test_jpg_processing(self):
        result = await processor.process(test_jpg)
        assert len(result.tags) > 0
        assert 0 <= result.aesthetic_score <= 10
    
    async def test_exr_handling(self):
        result = await processor.process(test_exr)
        assert result.type == "image"
    
    async def test_oom_fallback(self):
        # Force OOM condition
        with mock.patch('torch.cuda') as mock_cuda:
            mock_cuda.memory_allocated.return_value = 10e9
            result = await processor.process(test_jpg)
            assert result.metadata['fallback_to_cpu'] is True
```

---

## 9. Deployment & Distribution

### 9.1 Installation Methods

| Method | Target Users | Complexity |
|--------|--------------|------------|
| **One-click installer** (.exe/.dmg) | Casual | Low |
| **Git clone + setup.py** | Technical | Medium |
| **Eagle Plugin Store** | All | Low (when available) |
| **Portable (USB)** | Freelancers | Low |

### 9.2 Build Pipeline

```yaml
# .github/workflows/release.yml
name: Release Build

on:
  push:
    tags: ['v*']

jobs:
  build-windows:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install pyinstaller
          pip install -r requirements.txt
      
      - name: Build executable
        run: pyinstaller --onefile backend/localcura.py
      
      - name: Package plugin
        run: |
          mkdir LocalCura-v${{ github.ref_name }}
          cp -r eagle_plugin LocalCura-v${{ github.ref_name }}/
          cp dist/localcura.exe LocalCura-v${{ github.ref_name }}/
          7z a LocalCura-v${{ github.ref_name }}-windows.zip LocalCura-v${{ github.ref_name }}/
      
      - name: Create Release
        uses: softprops/action-gh-release@v1
        with:
          files: LocalCura-v${{ github.ref_name }}-windows.zip
```

---

## 10. Security Considerations

### 10.1 Threat Model

| Threat | Likelihood | Impact | Mitigation |
|--------|------------|--------|------------|
| Path traversal | Low | High | Validate all paths, chroot when possible |
| Model poisoning | Low | Medium | Checksum verification of downloaded models |
| Memory exhaustion | Medium | Medium | VRAM limits, timeout guards |
| Plugin escape | Low | High | Rely on Eagle's sandbox |

### 10.2 Input Validation

```python
from pathlib import Path
import re

SAFE_PATH_RE = re.compile(r'^[a-zA-Z0-9_\-\.\s/\\]+$')

def validate_path(filepath: str, base_dir: Path) -> Path:
    """Prevent path traversal attacks."""
    path = Path(filepath).resolve()
    
    # Check against allowed characters
    if not SAFE_PATH_RE.match(str(path)):
        raise ValueError("Invalid characters in path")
    
    # Ensure path is within base directory
    if not str(path).startswith(str(base_dir.resolve())):
        raise ValueError("Path traversal detected")
    
    return path
```

---

## 11. Monitoring & Observability

### 11.1 Logging

```python
# Structured JSON logging
{
    "timestamp": "2026-02-09T15:30:00Z",
    "level": "INFO",
    "component": "pipeline",
    "event": "processing_complete",
    "file": "image_001.jpg",
    "duration_ms": 850,
    "tags_count": 8,
    "model": "lfm2-vl-1.6b",
    "device": "cuda"
}
```

### 11.2 Metrics

| Metric | Type | Collection |
|--------|------|------------|
| Processing duration | Histogram | Automatic |
| VRAM usage | Gauge | Periodic poll |
| Tag accuracy | User feedback | Post-processing survey |
| Error rate | Counter | Exception handler |
| Model inference time | Histogram | Per-model |

---

## 12. Future Extensibility

### 12.1 Plugin Architecture

```python
# Allow third-party processors
class ProcessorPlugin(ABC):
    @abstractmethod
    def supports(self, filepath: Path) -> bool:
        pass
    
    @abstractmethod
    async def process(self, filepath: Path) -> ProcessingResult:
        pass

# Registration
plugin_registry = ProcessorRegistry()
plugin_registry.register(MyCustomProcessor())
```

### 12.2 Cloud-Assisted Mode (Optional)

For users who opt-in:
- Heavy processing offloaded to API
- Local encryption of assets before upload
- Results cached locally
- Fallback to local models on connection loss

---

## Appendix A: API Response Examples

### A.1 Image Processing Response

```json
{
  "file": "sunset_photo.jpg",
  "type": "image",
  "tags": [
    "sunset",
    "ocean",
    "beach",
    "golden hour",
    "landscape",
    "nature"
  ],
  "confidence_scores": {
    "sunset": 0.97,
    "ocean": 0.95,
    "beach": 0.92,
    "golden hour": 0.88,
    "landscape": 0.85,
    "nature": 0.82
  },
  "aesthetic_score": 8.5,
  "aesthetic_rating": 5,
  "summary": "A serene beach sunset with golden hour lighting over calm ocean waters",
  "metadata": {
    "width": 3840,
    "height": 2160,
    "dominant_colors": ["#FF6B35", "#004E89", "#F7C59F"]
  },
  "processing_time_ms": 720,
  "model_version": "lfm2-vl-1.6b"
}
```

### A.2 Audio Processing Response

```json
{
  "file": "upbeat_track.mp3",
  "type": "audio",
  "tags": [
    "128 bpm",
    "fast tempo",
    "electronic",
    "upbeat",
    "energetic",
    "synth"
  ],
  "confidence_scores": {
    "electronic": 0.91,
    "upbeat": 0.87
  },
  "aesthetic_score": null,
  "aesthetic_rating": null,
  "summary": "Upbeat electronic track at 128 BPM with energetic synth melodies",
  "metadata": {
    "bpm": 128,
    "duration": 214.5,
    "key": "F# minor",
    "spectral_centroid": 2850
  },
  "processing_time_ms": 420,
  "model_version": "librosa-0.10"
}
```
