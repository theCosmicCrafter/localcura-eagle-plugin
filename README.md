# LocalCura AI for Eagle (Ollama Edition)

A powerful, local-first AI tagging and analysis plugin for [Eagle App](https://eagle.cool/).

It uses **Ollama** running **Qwen 3 VL** to automatically:

* **Tag** images with descriptive keywords.
* **Describe** content in detail.
* **Analyze** genre, lighting, and style.
* **Suggest Names** for your files.
* **Group Similar Images** to reduce LLM calls.
* **Resume Interrupted Batches** - never lose progress.
* **Tag Videos** - Extracts and analyzes representative frames from video files.

Everything runs **offline** via Ollama.

## ✨ New Features

### Adaptive Chunking
Automatically adjusts batch size based on Ollama response times. Fast hardware = larger chunks, slower hardware = smaller chunks.

### Visual Similarity Grouping
Uses perceptual hashing to identify similar images. Process one representative from each group and apply tags to all similar images - reduces LLM calls by 60-80% for duplicate/similar shots.

### Video Analysis
Extracts 5 representative frames from videos (MP4, MOV, AVI, MKV, etc.) and analyzes them like images. Tags are merged across all frames for comprehensive video metadata.

### Resume Capability
If the browser crashes or you close the plugin mid-batch, you'll be prompted to resume where you left off when you reopen.

### Smart Retry with UX
Different error types get different retry strategies:
- **503/Queue Full**: Exponential backoff with wait time estimates
- **Timeouts**: Automatic quality reduction and retry
- **Connection errors**: Clear messaging about Ollama status

### Configuration UI
Click the settings gear icon to customize:
- Chunk size and delays
- Enable/disable adaptive chunking
- Toggle resume capability
- Image compression settings

### Memory Management
Fixed memory leaks when processing 1000+ images by properly managing object URLs.

## Prerequisites

* **Ollama**: [Download Ollama](https://ollama.com/) and ensure it is running (`http://localhost:11434`).
* **Python 3.10+**
* **Eagle App**

## Installation

### 1. Clone the Repo

```bash
git clone https://github.com/yourusername/localcura.git
cd localcura
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
   * The system will automatically check for and pull `qwen3-vl` if it's missing.

3. **In Eagle**:
   * Load the unpacked plugin from the `eagle_plugin` folder.
   * Select images and click "Analyze & Tag Selected".
   * Use the settings gear to customize chunking behavior.

## Configuration

### Environment Variables

Create a `.env` file in the root directory:

```env
OLLAMA_BASE_URL=http://localhost:11434/api
OLLAMA_MODEL=qwen3-vl:8b
```

### Plugin Settings

Click the **⚙️ Settings** button in the plugin header to customize:

| Setting | Default | Description |
|---------|---------|-------------|
| Chunk Size | 5 | Images processed per batch |
| Chunk Delay | 5000ms | Wait time between batches |
| Adaptive Chunking | On | Auto-adjust based on response times |
| Resume | On | Save progress for crash recovery |
| Compression | On | Resize large images before sending |

### Ollama Optimization

For best performance with 1000+ images:

```bash
# Increase Ollama's queue size (optional)
export OLLAMA_MAX_QUEUE=50

# Allow more parallel processing if you have GPU memory
export OLLAMA_NUM_PARALLEL=2
```

## API Endpoints

The backend provides these additional endpoints:

### Process Image
`POST /process` - Analyze and tag a single image

### Similarity Grouping
`POST /similarity/group` - Group visually similar images
```bash
curl -X POST http://localhost:8005/similarity/group \
  -F "files=@image1.jpg" \
  -F "files=@image2.jpg" \
  -F "threshold=8"
```

### Get Image Hash
`GET /similarity/hash?file_path=/path/to/image.jpg`

## Troubleshooting

### "Ollama queue full (503)"
The plugin will automatically slow down and retry. You can adjust chunk delays in Settings.

### Browser crashes with 1000+ images
Memory management is now fixed. If issues persist, reduce chunk size in Settings.

### "Resume batch?" prompt on startup
This is the resume feature working! Click OK to continue, Cancel to start fresh.

## Performance Tips

1. **Enable Similarity Grouping** for photo shoots with many similar shots
2. **Use Adaptive Chunking** to let the plugin find the optimal speed
3. **Resume** lets you safely process large batches across multiple sessions
4. Image compression reduces upload time for high-res photos

## License

MIT License - feel free to modify and distribute.
