# CosmicTagger — Local-First AI Omnitagger for Eagle

A powerful, local-first AI tagging and analysis plugin for [Eagle App](https://eagle.cool/).

It uses **Ollama** running vision models (Qwen3-VL, LLaVA, etc.) to automatically:

- **Tag** images, video, audio, and text with descriptive keywords
- **Describe** content in detail
- **Analyze** genre, lighting, style, color palette, and technical quality
- **Suggest Names** for your files
- **Extract ComfyUI/SD Metadata** — reads AI generation prompts from PNGs
- **Group Similar Images** — perceptual hashing reduces LLM calls by 60-80%
- **Resume Interrupted Batches** — never lose progress
- **Rate Content** — 1-5 star aesthetic scoring

Everything runs **offline** via Ollama. No cloud. No API keys.

---

## ✨ Features

### Multi-Modal Tagging

- **Images** — Full analysis with subjects, genre, lighting, color, mood, style
- **Video** — Extracts 5 representative frames, merges tags across all frames
- **Audio** — Extracts metadata (duration, bitrate, ID3 tags) and analyzes genre/mood/instrumentation
- **Text** — Summarizes and categorizes documents

### AI Metadata Extraction

Automatically detects and extracts generation metadata from AI images:

- **ComfyUI** workflow data and prompts
- **Stable Diffusion WebUI** parameters (prompt, negative prompt, steps, sampler, seed, CFG)

### Color Palette Analysis

Extracts 5 dominant colors using PIL median-cut quantization. Classifies palette type:

- Monochrome, Vibrant, Dark, Warm, Cool, Mixed

### 3-Layer Tag Verification

1. **Normalize** — lowercase, deduplicate, strip special chars
2. **Filter** — remove stopwords, enforce min/max length, blacklist
3. **Score** — quality score based on diversity, count, deduplication ratio

### Visual Similarity Grouping

Uses perceptual hashing (aHash) to find duplicate/similar images before processing. Tags from one representative are propagated to all duplicates.

### Adaptive Chunking

Automatically adjusts batch size based on Ollama response times. Fast GPU = larger chunks, slow CPU = smaller chunks.

### Performance Optimizations

- **Response Cache** — SHA256-based LRU cache (500 entries). Same image = instant result.
- **Server-Side Batch** — `POST /process/batch/paths` sends file paths only; backend reads directly from disk
- **No Upload Overhead** — avoids copying image bytes over HTTP for local files

### Security

- **API Token Auth** — random 32-char token generated on init, passed via `X-API-Key`
- **Restricted CORS** — only `localhost`, `file://`, and Eagle webview origins allowed
- **PID Tracking** — kills orphaned Python servers on plugin load, force-kills on close

### UX

- **Results Panel** — per-item breakdown: tags, aesthetic score, color palette, AI metadata
- **Model Selector** — auto-detects all Ollama models, shows vision capability, recommends best
- **Keyboard Shortcut** — `Ctrl+Shift+T` triggers tagging without opening plugin window
- **Eagle Progress Bar** — native `eagle.window.setProgress()` during batch
- **Resume** — tracks processed item IDs (not just count), survives selection changes

---

## Prerequisites

- **Ollama**: [Download Ollama](https://ollama.com/) and ensure it is running (`http://localhost:11434`)
- **Python 3.10+**
- **Eagle App**

---

## Installation

### 1. Clone the Repo

```bash
git clone https://github.com/theCosmicCrafter/localcura-eagle-plugin.git
cd localcura-eagle-plugin
```

### 2. Setup Python Environment

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Install dependencies
pip install -r backend/requirements.txt

# Verify installation (optional but recommended)
python check_requirements.py
```

### 3. Usage

1. **Start Ollama**: Make sure Ollama is running in the background.
2. **Start the Backend**:
   ```bash
   python backend/localcura.py --start-server --port 8005
   ```

   - The system will automatically check for and pull `qwen3-vl` if it's missing.
3. **In Eagle**:
   - Load the unpacked plugin from the `eagle_plugin` folder.
   - Select items and click **"Analyze & Tag Selected"**.
   - Use the settings gear to customize behavior.

---

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
OLLAMA_BASE_URL=http://localhost:11434/api
OLLAMA_MODEL=qwen3-vl:8b

# Optional toggles
EXTRACT_METADATA=true
EXTRACT_COLORS=true
MAX_TAGS=30
MIN_TAG_LENGTH=2
MAX_TAG_LENGTH=25
```

### Plugin Settings

Click the **⚙️ Settings** button in the plugin header to customize:

| Setting           | Default | Description                               |
| ----------------- | ------- | ----------------------------------------- |
| Chunk Size        | 5       | Items processed per batch                 |
| Chunk Delay       | 5000ms  | Wait time between batches                 |
| Adaptive Chunking | On      | Auto-adjust based on response times       |
| Resume            | On      | Save progress for crash recovery          |
| Compression       | On      | Resize large images before sending        |
| Extract Metadata  | On      | Read ComfyUI/SD data from PNGs            |
| Extract Colors    | On      | Extract dominant color palette            |
| Verify Tags       | On      | 3-layer tag cleaning                      |
| Max Tags          | 30      | Limit tags per item                       |
| AI Model          | Auto    | Select Ollama model (fetched dynamically) |

---

## API Endpoints

| Endpoint                    | Method | Description                                        |
| --------------------------- | ------ | -------------------------------------------------- |
| `GET /health`               | GET    | Health check + model info                          |
| `POST /process`             | POST   | Single file upload                                 |
| `POST /process/batch`       | POST   | Multipart batch upload                             |
| `POST /process/batch/paths` | POST   | Batch by file paths (fastest)                      |
| `POST /similarity/group`    | POST   | Group similar images by perceptual hash            |
| `GET /similarity/hash`      | GET    | Single image hash                                  |
| `GET /models`               | GET    | List installed Ollama models with vision detection |
| `GET /cache/stats`          | GET    | Cache metrics                                      |
| `POST /cache/clear`         | POST   | Clear analysis cache                               |

---

## Troubleshooting

### "Ollama queue full (503)"

The plugin will automatically slow down and retry. Reduce chunk size in Settings.

### "Cannot locate backend"

The plugin auto-detects the backend path from `eagle.plugin.path`. If it fails, set the path manually in Settings.

### Browser crashes with 1000+ images

Enable similarity grouping and use smaller chunk sizes.

### "Resume batch?" prompt on startup

This is the resume feature working! Click OK to continue, Cancel to start fresh.

---

## Performance Tips

1. **Enable Similarity Grouping** for photo shoots with many similar shots
2. **Use Adaptive Chunking** to let the plugin find the optimal speed
3. **Resume** lets you safely process large batches across multiple sessions
4. **Server-side batch paths** is 10x faster than individual uploads for local files
5. **Cache** avoids re-analyzing identical images

---

## License

MIT License — feel free to modify and distribute.
