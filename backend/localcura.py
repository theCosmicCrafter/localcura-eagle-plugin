"""
LocalCura - Local-first image curation using Ollama and Qwen 3.
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".gif", ".avif", ".heic"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv", ".wmv", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".aac", ".m4a", ".ogg"}
TEXT_EXTENSIONS = {".txt", ".md", ".rtf", ".json", ".csv"}

# Try to import cv2 for video processing
try:
    import cv2
    HAVE_CV2 = True
except ImportError:
    HAVE_CV2 = False
    logger.warning("OpenCV not available. Video processing will be disabled.")

# Audio metadata extraction
try:
    from mutagen import File as MutagenFile
    HAVE_MUTAGEN = True
except ImportError:
    HAVE_MUTAGEN = False
MAX_TEXT_CHARS = 6000
MAX_IMAGE_SIZE = (1024, 1024)  # Max dimensions for processing
MAX_FILE_SIZE_MB = 50  # Max file size in MB
TAG_FIELDS = {
    "subjects",
    "genre",
    "lighting",
    "color_and_tone",
    "time_or_season",
    "similar_artists",
    "mood",
    "instrumentation",
    "structure",
    "production",
    "topics",
    "tone",
    "intent",
    "entities",
    "similar_authors",
}

load_dotenv()

# Configure Logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "localcura.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("localcura")


# Template cache to avoid disk reads on every request
_template_cache: Dict[str, Dict[str, Any]] = {}

def load_json_template(path: Path) -> Dict[str, Any]:
    """Load template with caching to avoid disk reads."""
    cache_key = str(path)
    
    # Return cached version if available
    if cache_key in _template_cache:
        return _template_cache[cache_key]
    
    if not path.exists():
        logger.warning("Template %s not found; using empty template.", path)
        return {"globalInstructions": "", "rules": []}
    
    template = json.loads(path.read_text(encoding="utf-8"))
    _template_cache[cache_key] = template
    return template


def render_prompt_from_template(
    template: Dict[str, Any], rename_template: Optional[Dict[str, Any]] = None
) -> str:
    lines = [
        "You are an AI tagging assistant embedded inside Eagle MCP.",
        f"GLOBAL INSTRUCTIONS: {template.get('globalInstructions', '').strip()}",
        "",
        "ANALYSIS RULES:",
    ]
    for rule in template.get("rules", []):
        name = rule.get("name", "Rule")
        instruction = rule.get("instruction", "")
        lines.append(f"- {name}: {instruction}")

    if rename_template:
        lines.append("")
        lines.append("RENAMING GUIDELINES:")
        for rule in rename_template.get("rules", []):
            if rule.get("type") == "name":
                lines.append(f"- {rule.get('instruction', '')}")

    lines.append("")
    lines.append(
        "Return a single JSON object that includes every required key exactly once."
    )
    lines.append(
        "Use arrays of concise tags when a rule expects multiple values; use short strings for description fields."
    )
    return "\n".join(lines)


def validate_file_size(file_buffer: bytes) -> bool:
    """Check if file size is within limits."""
    size_mb = len(file_buffer) / (1024 * 1024)
    return size_mb <= MAX_FILE_SIZE_MB

def compress_image_if_needed(image: Image.Image) -> Image.Image:
    """Resize image if it exceeds max dimensions while maintaining aspect ratio."""
    if image.width <= MAX_IMAGE_SIZE[0] and image.height <= MAX_IMAGE_SIZE[1]:
        return image
    
    # Calculate scaling factor to fit within max dimensions
    scale_w = MAX_IMAGE_SIZE[0] / image.width
    scale_h = MAX_IMAGE_SIZE[1] / image.height
    scale = min(scale_w, scale_h)
    
    new_size = (int(image.width * scale), int(image.height * scale))
    logger.info("Compressing image from %sx%s to %sx%s", 
                image.width, image.height, new_size[0], new_size[1])
    return image.resize(new_size, Image.LANCZOS)

def extract_audio_metadata(filepath: str, contents: bytes) -> Dict[str, Any]:
    """Extract metadata from audio bytes. Falls back to basic heuristics."""
    info: Dict[str, Any] = {"format": Path(filepath).suffix.lower(), "duration": None, "bitrate": None, "sample_rate": None, "channels": None}
    if HAVE_MUTAGEN:
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=info["format"], delete=False) as tmp:
                tmp.write(contents)
                tmp_path = tmp.name
            try:
                audio = MutagenFile(tmp_path)
                if audio is not None:
                    info["duration"] = getattr(audio.info, "length", None)
                    info["bitrate"] = getattr(audio.info, "bitrate", None)
                    info["sample_rate"] = getattr(audio.info, "sample_rate", None)
                    info["channels"] = getattr(audio.info, "channels", None)
                    # Tags
                    if audio.tags:
                        for key in ["title", "artist", "album", "genre", "date"]:
                            val = audio.tags.get(key) or audio.tags.get(key.upper())
                            if val:
                                info[key] = str(val[0] if isinstance(val, list) else val)
            finally:
                try:
                    os.unlink(tmp_path)
                except:
                    pass
        except Exception as e:
            logger.warning("Mutagen failed for %s: %s", filepath, e)
    # Build description for LLM
    parts = [f"Audio file: {Path(filepath).name}", f"Format: {info['format']}"]
    if info["duration"] is not None:
        parts.append(f"Duration: {info['duration']:.1f}s")
    if info["bitrate"] is not None:
        parts.append(f"Bitrate: {info['bitrate'] // 1000} kbps")
    if info["sample_rate"] is not None:
        parts.append(f"Sample rate: {info['sample_rate']} Hz")
    if info["channels"] is not None:
        parts.append(f"Channels: {info['channels']}")
    for key in ["title", "artist", "album", "genre"]:
        if key in info:
            parts.append(f"{key.capitalize()}: {info[key]}")
    return {"text": "\n".join(parts), "metadata": info}


def determine_media_kind(filename: str, content_type: Optional[str]) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix in IMAGE_EXTENSIONS or (
        content_type and content_type.startswith("image/")
    ):
        return "image"
    if suffix in VIDEO_EXTENSIONS or (
        content_type and content_type.startswith("video/")
    ):
        return "video"
    if suffix in AUDIO_EXTENSIONS or (
        content_type and content_type.startswith("audio/")
    ):
        return "audio"
    if suffix in TEXT_EXTENSIONS or (content_type and content_type.startswith("text/")):
        return "text"
    return "unknown"


def extract_video_frames(video_bytes: bytes, max_frames: int = 5) -> List[Image.Image]:
    """
    Extract representative frames from video bytes.
    
    Args:
        video_bytes: Raw video file bytes
        max_frames: Maximum number of frames to extract (default 5)
    
    Returns:
        List of PIL Images
    """
    if not HAVE_CV2:
        raise RuntimeError("OpenCV not available for video processing")
    
    # Write to temp file (cv2 needs file path)
    import tempfile
    with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name
    
    try:
        cap = cv2.VideoCapture(tmp_path)
        if not cap.isOpened():
            raise RuntimeError("Could not open video file")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            raise RuntimeError("Could not determine video frame count")
        
        # Extract frames evenly distributed throughout video
        frames = []
        indices = [int(total_frames * i / (max_frames + 1)) for i in range(1, max_frames + 1)]
        
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if ret:
                # Convert BGR to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(frame_rgb)
                frames.append(pil_image)
        
        cap.release()
        return frames
        
    finally:
        # Clean up temp file
        try:
            os.unlink(tmp_path)
        except:
            pass


def truncate_text_payload(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    if len(text) <= MAX_TEXT_CHARS:
        return text
    return text[:MAX_TEXT_CHARS] + "\n\n[Truncated for analysis]"


def normalize_key(key: str) -> str:
    return key.strip().lower().replace(" ", "_")


class Config:
    """Configuration for LocalCura."""

    def __init__(self) -> None:
        base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/api")
        self.ollama_base_url = base_url
        self.ollama_model = os.getenv("OLLAMA_MODEL", "qwen3-vl:8b")
        self.eagle_library_path = os.getenv("EAGLE_LIBRARY_PATH")
        self.photography_template_path = Path(
            os.getenv("PHOTOGRAPHY_TEMPLATE", "templates/photography_template")
        )
        self.audio_template_path = Path(os.getenv("AUDIO_TEMPLATE", "templates/audio_template"))
        self.text_template_path = Path(os.getenv("TEXT_TEMPLATE", "templates/text_template"))
        self.video_template_path = Path(os.getenv("VIDEO_TEMPLATE", "templates/video_template"))
        self.rename_template_path = Path(
            os.getenv("RENAME_TEMPLATE", "templates/rename_template")
        )


class OllamaClient:
    """Thin wrapper around the Ollama chat endpoint."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._ensure_model_exists()

    def _ensure_model_exists(self) -> None:
        """Check if model exists, if not, pull it."""
        try:
            logger.info("Checking if model %s exists...", self.cfg.ollama_model)
            tags_url = f"{self.cfg.ollama_base_url}/tags"
            resp = requests.get(tags_url, timeout=5)

            needs_pull = True
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                for m in models:
                    if m.get("name") == self.cfg.ollama_model:
                        needs_pull = False
                        break

            if needs_pull:
                logger.info("Model %s not found. Pulling...", self.cfg.ollama_model)
                pull_url = f"{self.cfg.ollama_base_url}/pull"
                resp = requests.post(
                    pull_url,
                    json={"name": self.cfg.ollama_model, "stream": False},
                    timeout=1800,
                )
                if resp.status_code == 200:
                    logger.info("Successfully pulled model.")
                else:
                    logger.error("Failed to pull model: %s", resp.text)
            else:
                logger.info("Model found.")

        except Exception as e:
            logger.error("Error ensuring model exists: %s", e)

    def _invoke_chat(self, prompt: str, user_payload: Dict[str, Any]) -> Dict[str, Any]:
        base = self.cfg.ollama_base_url.rstrip("/")
        if not base.endswith("/api"):
            base += "/api"
        url = f"{base}/chat"

        payload = {
            "model": self.cfg.ollama_model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": prompt},
                user_payload,
            ],
            "options": {
                "temperature": 0.1,
                "num_ctx": 4096,  # Increased from Ollama default 2048
            },
        }

        try:
            logger.info(
                "Sending request to Ollama at %s (model: %s)...",
                url,
                self.cfg.ollama_model,
            )
            # Aligned with Ollama defaults: NUM_PARALLEL=1 means sequential processing
            # 120s timeout allows for slower vision model inference on large images
            response = requests.post(url, json=payload, timeout=120)

            if response.status_code != 200:
                # Handle specific Ollama error codes for better client retry logic
                if response.status_code == 503:
                    logger.warning("Ollama queue full (503): %s", response.text)
                    return {
                        "error": "Ollama queue full (503) - retry later",
                        "retryable": True,
                        "status": 503,
                    }
                elif response.status_code == 504:
                    logger.warning("Ollama timeout (504): %s", response.text)
                    return {
                        "error": "Ollama timeout (504) - retry later",
                        "retryable": True,
                        "status": 504,
                    }
                else:
                    logger.error("Ollama Error %s: %s", response.status_code, response.text)
                    return {
                        "error": f"Ollama HTTP {response.status_code}",
                        "raw": response.text,
                    }

            result = response.json()
            content = result.get("message", {}).get("content", "")

            try:
                data = json.loads(content)
                return data
            except json.JSONDecodeError:
                logger.error(f"Failed to parse JSON from Ollama: {content}")
                return {"error": "Invalid JSON response", "raw": content}

        except requests.exceptions.Timeout:
            logger.error("Ollama request timed out after 120s")
            return {
                "error": "Request timeout (120s) - Ollama may be busy",
                "retryable": True,
                "status": 504,
            }
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Ollama connection error: {e}")
            return {
                "error": f"Connection error - Ollama may not be running: {e}",
                "retryable": False,
            }
        except Exception as e:
            logger.error("Ollama inference failed: %s", e)
            return {"error": str(e)}

    def analyze_image(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        buffered = BytesIO()
        image.save(buffered, format="JPEG")
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return self._invoke_chat(
            prompt,
            {"role": "user", "content": "Analyze this image.", "images": [img_str]},
        )

    def analyze_text(self, text: str, prompt: str) -> Dict[str, Any]:
        return self._invoke_chat(
            prompt,
            {
                "role": "user",
                "content": f"Analyze this text and follow the template strictly:\n\n{text}",
            },
        )


class LocalCuraApp:
    """Main application logic."""

    def __init__(self):
        self.cfg = Config()
        self.client = OllamaClient(self.cfg)
        self.photography_template = load_json_template(
            self.cfg.photography_template_path
        )
        self.audio_template = load_json_template(self.cfg.audio_template_path)
        self.text_template = load_json_template(self.cfg.text_template_path)
        self.video_template = load_json_template(self.cfg.video_template_path)
        self.rename_template = load_json_template(self.cfg.rename_template_path)

    def process_file(self, filepath: Path) -> Dict[str, Any]:
        """Process a local file."""
        try:
            contents = filepath.read_bytes()
            return self._process_blob(filepath.name, contents, None)
        except Exception as e:
            logger.error("Error processing file %s: %s", filepath, e)
            return {"error": str(e)}

    def process_upload(self, file: UploadFile) -> Dict[str, Any]:
        """Process an uploaded file."""
        try:
            contents = file.file.read()
            return self._process_blob(file.filename, contents, file.content_type)
        except Exception as e:
            logger.error("Error processing upload: %s", e)
            return {"error": str(e)}

    def _process_blob(
        self, filename: str, contents: bytes, content_type: Optional[str]
    ) -> Dict[str, Any]:
        media_kind = determine_media_kind(filename or "", content_type)
        
        # Validate file size
        if not validate_file_size(contents):
            size_mb = len(contents) / (1024 * 1024)
            logger.warning("File %s too large (%.1f MB > %d MB limit)", 
                          filename, size_mb, MAX_FILE_SIZE_MB)
            return {
                "file": filename,
                "media_kind": media_kind,
                "error": f"File too large ({size_mb:.1f} MB > {MAX_FILE_SIZE_MB} MB limit)",
                "retryable": False,
            }
        
        prompt = self._build_prompt(media_kind)

        if media_kind == "image":
            try:
                image = Image.open(BytesIO(contents)).convert("RGB")
                # Compress large images before sending to LLM
                image = compress_image_if_needed(image)
                analysis = self.client.analyze_image(image, prompt)
                return self._format_result(filename, analysis, media_kind)
            except Exception as e:
                logger.error("Error processing image %s: %s", filename, e)
                return {
                    "file": filename,
                    "media_kind": media_kind,
                    "error": f"Image processing failed: {str(e)}",
                    "retryable": False,
                }

        if media_kind == "text":
            text_payload = truncate_text_payload(contents)
            analysis = self.client.analyze_text(text_payload, prompt)
            return self._format_result(filename, analysis, media_kind)

        if media_kind == "video":
            if not HAVE_CV2:
                return {
                    "file": filename,
                    "media_kind": media_kind,
                    "error": "Video processing requires OpenCV (cv2). Install with: pip install opencv-python-headless",
                    "retryable": False,
                }
            try:
                # Extract frames from video
                frames = extract_video_frames(contents, max_frames=5)
                if not frames:
                    return {
                        "file": filename,
                        "media_kind": media_kind,
                        "error": "Could not extract frames from video",
                        "retryable": False,
                    }
                
                # Analyze each frame and aggregate results
                all_analyses = []
                for i, frame in enumerate(frames):
                    logger.info("Analyzing video frame %d/%d for %s", i+1, len(frames), filename)
                    frame = compress_image_if_needed(frame)
                    analysis = self.client.analyze_image(frame, prompt)
                    all_analyses.append(analysis)
                
                # Merge analyses from all frames
                merged_analysis = self._merge_video_analyses(all_analyses)
                return self._format_result(filename, merged_analysis, media_kind)
                
            except Exception as e:
                logger.error("Error processing video %s: %s", filename, e)
                return {
                    "file": filename,
                    "media_kind": media_kind,
                    "error": f"Video processing failed: {str(e)}",
                    "retryable": False,
                }

        if media_kind == "audio":
            try:
                audio_info = extract_audio_metadata(filename, contents)
                text_payload = audio_info["text"]
                prompt = self._build_prompt(media_kind)
                analysis = self.client.analyze_text(text_payload, prompt)
                result = self._format_result(filename, analysis, media_kind)
                result["audio_metadata"] = audio_info["metadata"]
                return result
            except Exception as e:
                logger.error("Error processing audio %s: %s", filename, e)
                return {
                    "file": filename,
                    "media_kind": media_kind,
                    "error": f"Audio processing failed: {str(e)}",
                    "retryable": False,
                }

        return {
            "file": filename,
            "media_kind": media_kind,
            "error": "Unsupported media type",
            "retryable": False,
        }

    def _build_prompt(self, media_kind: str) -> str:
        if media_kind == "text":
            return render_prompt_from_template(self.text_template)
        if media_kind == "audio":
            return render_prompt_from_template(self.audio_template)
        if media_kind == "video":
            return render_prompt_from_template(self.video_template, self.rename_template)
        return render_prompt_from_template(
            self.photography_template, self.rename_template
        )

    def _merge_video_analyses(self, analyses: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Merge analyses from multiple video frames into a single result."""
        if not analyses:
            return {}
        
        merged = {
            "description": "",
            "subjects": [],
            "genre": [],
            "cinematography": [],
            "production_quality": [],
        }
        
        # Collect all unique values from all frames
        all_subjects = set()
        all_genres = set()
        all_cinematography = set()
        all_production = set()
        descriptions = []
        
        for analysis in analyses:
            norm = self._normalize_analysis(analysis)
            
            # Merge subjects
            subjects = norm.get("subjects", [])
            if isinstance(subjects, str):
                subjects = [s.strip() for s in subjects.split(",") if s.strip()]
            if isinstance(subjects, list):
                all_subjects.update(subjects)
            
            # Merge other fields
            genre = norm.get("genre", [])
            if isinstance(genre, str):
                genre = [genre]
            all_genres.update(genre)
            
            cinematography = norm.get("cinematography", [])
            if isinstance(cinematography, str):
                cinematography = [cinematography]
            all_cinematography.update(cinematography)
            
            production = norm.get("production_quality", [])
            if isinstance(production, str):
                production = [production]
            all_production.update(production)
            
            # Collect descriptions
            if norm.get("description"):
                descriptions.append(norm["description"])
        
        # Build merged result
        merged["subjects"] = sorted(all_subjects)
        merged["genre"] = sorted(all_genres)[:3]  # Top 3 genres
        merged["cinematography"] = sorted(all_cinematography)[:5]  # Top 5 cinematography tags
        merged["production_quality"] = sorted(all_production)[:3]
        
        # Create combined description
        if descriptions:
            # Use first description as base, mention it's from multiple frames
            merged["description"] = descriptions[0]
            if len(descriptions) > 1:
                merged["description"] += f" (Analyzed across {len(descriptions)} representative frames)"
        
        return merged

    def _format_result(
        self, filename: str, analysis: Dict[str, Any], media_kind: str
    ) -> Dict[str, Any]:
        normalized = self._normalize_analysis(analysis)
        tags = self._extract_tags(normalized)

        # Compute aesthetic score (0-10) if available or inferred
        aesthetic = 0.0
        if "aesthetic_score" in normalized:
            try:
                aesthetic = float(normalized["aesthetic_score"])
            except (ValueError, TypeError):
                aesthetic = 0.0
        elif "quality" in normalized:
            # Heuristic: map quality descriptors to score
            quality_map = {"excellent": 9, "high": 7, "good": 6, "average": 5, "low": 3, "poor": 2}
            q = str(normalized["quality"]).lower()
            aesthetic = quality_map.get(q, 5)

        return {
            "file": filename,
            "media_kind": media_kind,
            "tags": tags,
            "analysis": normalized,
            "suggested_name": normalized.get("suggested_name"),
            "description": normalized.get("description"),
            "aesthetic": round(aesthetic, 1),
        }

    @staticmethod
    def _normalize_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
        normalized: Dict[str, Any] = {}
        for key, value in data.items():
            norm_key = normalize_key(key)
            if norm_key == "subjects" and isinstance(value, str):
                value = [s.strip() for s in value.split(",") if s.strip()]
            normalized[norm_key] = value
        return normalized

    @staticmethod
    def _extract_tags(analysis: Dict[str, Any]) -> list[str]:
        collected = []
        for field in TAG_FIELDS:
            value = analysis.get(field)
            if isinstance(value, list):
                collected.extend(value)
            elif isinstance(value, str):
                collected.append(value)
        return sorted(
            {
                str(tag).strip()
                for tag in collected
                if isinstance(tag, str) and tag.strip()
            }
        )


# -------------------------------------------------------------------------
# CLI & Server
# -------------------------------------------------------------------------

app_instance = LocalCuraApp()

# Create FastAPI app
app = FastAPI(title="LocalCura qwen3-vl")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8005",
        "http://127.0.0.1:8005",
        "file://",
        "null",
    ],
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

# Simple API key middleware
API_KEY = os.getenv("COSMICTAGGER_API_KEY", "")

@app.middleware("http")
async def api_key_check(request, call_next):
    # Skip health check and OPTIONS
    if request.url.path == "/health" or request.method == "OPTIONS":
        return await call_next(request)
    if API_KEY:
        header_key = request.headers.get("X-API-Key", "")
        if header_key != API_KEY:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"error": "Invalid or missing API key", "success": False}
            )
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok", "model": app_instance.cfg.ollama_model}


@app.post("/process")
def process(file: UploadFile = File(...)):
    return app_instance.process_upload(file)


@app.post("/process/batch")
async def process_batch(files: List[UploadFile] = File(...)):
    """Process multiple files in one request."""
    results = []
    errors = []
    for file in files:
        try:
            result = app_instance.process_upload(file)
            results.append(result)
            if "error" in result:
                errors.append({"file": file.filename, "error": result["error"]})
        except Exception as e:
            logger.error("Batch processing failed for %s: %s", file.filename, e)
            errors.append({"file": file.filename, "error": str(e)})
            results.append({"file": file.filename, "error": str(e)})
    return {
        "total": len(files),
        "processed": len(results),
        "errors": errors,
        "results": results,
    }


@app.post("/process/batch/paths")
async def process_batch_paths(payload: Dict[str, Any]):
    """Process files by their local file paths."""
    paths = payload.get("paths", [])
    if not paths:
        return {"total": 0, "results": []}

    results = []
    errors = []
    for p in paths:
        try:
            file_path = Path(p)
            if not file_path.exists():
                errors.append({"path": p, "error": "File not found"})
                results.append({"path": p, "error": "File not found"})
                continue
            result = app_instance.process_file(file_path)
            result["path"] = p
            results.append(result)
            if "error" in result:
                errors.append({"path": p, "error": result["error"]})
        except Exception as e:
            logger.error("Batch path processing failed for %s: %s", p, e)
            errors.append({"path": p, "error": str(e)})
            results.append({"path": p, "error": str(e)})

    return {
        "total": len(paths),
        "processed": len(results),
        "errors": errors,
        "results": results,
    }


# -------------------------------------------------------------------------
# Visual Similarity Grouping (Perceptual Hashing)
# -------------------------------------------------------------------------

def compute_perceptual_hash(image: Image.Image, hash_size: int = 8) -> int:
    """Compute average hash (aHash) for image similarity comparison."""
    # Resize to hash_size x hash_size and convert to grayscale
    small = image.convert('L').resize((hash_size, hash_size), Image.LANCZOS)
    pixels = list(small.getdata())
    avg = sum(pixels) / len(pixels)
    # Create hash: 1 if pixel > average, else 0
    bits = ''.join('1' if p > avg else '0' for p in pixels)
    return int(bits, 2)

def hamming_distance(hash1: int, hash2: int) -> int:
    """Calculate Hamming distance between two hashes."""
    x = hash1 ^ hash2
    distance = 0
    while x:
        distance += x & 1
        x >>= 1
    return distance

@app.post("/similarity/group")
async def group_similar_images(files: List[UploadFile] = File(...), threshold: int = 8):
    """
    Group visually similar images using perceptual hashing.
    
    Args:
        files: List of image files to analyze
        threshold: Max Hamming distance to consider images similar (default 8)
    
    Returns:
        groups: List of groups, each containing similar image indices
        hashes: List of computed hashes for each image
    """
    hashes = []
    results = []
    
    for file in files:
        try:
            contents = await file.read()
            image = Image.open(BytesIO(contents)).convert("RGB")
            img_hash = compute_perceptual_hash(image)
            hashes.append({
                "filename": file.filename,
                "hash": img_hash,
                "hash_hex": f"{img_hash:016x}"
            })
        except Exception as e:
            logger.error("Failed to hash %s: %s", file.filename, e)
            hashes.append({"filename": file.filename, "hash": None, "error": str(e)})
    
    # Group similar images
    groups = []
    used = set()
    
    for i, h1 in enumerate(hashes):
        if i in used or h1.get("hash") is None:
            continue
        
        group = [i]
        used.add(i)
        
        for j, h2 in enumerate(hashes[i+1:], start=i+1):
            if j in used or h2.get("hash") is None:
                continue
            
            distance = hamming_distance(h1["hash"], h2["hash"])
            if distance <= threshold:
                group.append(j)
                used.add(j)
        
        if len(group) > 1:
            groups.append({
                "indices": group,
                "filenames": [hashes[idx]["filename"] for idx in group],
                "representative": group[0]  # First image as representative
            })
    
    return {
        "groups": groups,
        "hashes": hashes,
        "threshold": threshold,
        "total_processed": len(files),
        "similar_groups_found": len(groups),
        "potential_savings": sum(len(g["indices"]) - 1 for g in groups)
    }


@app.get("/similarity/hash")
def get_image_hash(file_path: str):
    """Get perceptual hash for a single image file path."""
    try:
        image = Image.open(file_path).convert("RGB")
        img_hash = compute_perceptual_hash(image)
        return {
            "filename": Path(file_path).name,
            "hash": img_hash,
            "hash_hex": f"{img_hash:016x}"
        }
    except Exception as e:
        return {"error": str(e), "filename": file_path}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", type=str, help="Path to image file")
    parser.add_argument("--port", type=int, default=8000, help="Port to run server on")
    parser.add_argument(
        "--start-server", action="store_true", help="Start the API server"
    )
    # Note: 'uvicorn' is typically run from CLI as `uvicorn backend.localcura:app`

    args = parser.parse_args()

    if args.start_server:
        import uvicorn

        uvicorn.run(app, host="0.0.0.0", port=args.port)
    elif args.file:
        result = app_instance.process_file(Path(args.file))
        print(json.dumps(result, indent=2))
    else:
        # Default behavior if run directly without args might be to start server or print help
        print("Use --start-server to run the backend or --file to process an image.")


if __name__ == "__main__":
    main()
