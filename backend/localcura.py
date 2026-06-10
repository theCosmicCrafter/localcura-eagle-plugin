"""
LocalCura - Local-first image curation using Ollama and Qwen 3.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
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
import colorsys

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

# Simple in-memory LRU cache for analysis results
_analysis_cache: Dict[str, Dict[str, Any]] = {}
_CACHE_MAX_SIZE = 500

def _cache_key(contents: bytes) -> str:
    return hashlib.sha256(contents).hexdigest()

def _get_cached(contents: bytes) -> Optional[Dict[str, Any]]:
    key = _cache_key(contents)
    return _analysis_cache.get(key)

def _set_cached(contents: bytes, result: Dict[str, Any]) -> None:
    key = _cache_key(contents)
    if len(_analysis_cache) >= _CACHE_MAX_SIZE:
        # Evict oldest entry (simple: clear half)
        keys = list(_analysis_cache.keys())
        for k in keys[:len(keys)//2]:
            del _analysis_cache[k]
    _analysis_cache[key] = result

def clear_cache() -> None:
    _analysis_cache.clear()
    logger.info("Analysis cache cleared.")


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
        lines.append(f"- {instruction}  (category: {name})")

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
    lines.append(
        "IMPORTANT: Tag values must be plain words or short phrases ONLY. "
        "NEVER prefix tag values with category names like 'Subject:', 'Genre:', 'Lighting:', etc. "
        "For example, output 'black collar' NOT 'Subject: black collar', and 'portrait' NOT 'Genre: portrait'."
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

class MetadataExtractor:
    """Extract ComfyUI/Stable Diffusion metadata from PNG/JPG."""

    @staticmethod
    def extract_comfyui_metadata(image_path: Path) -> Dict[str, Any]:
        metadata = {}
        try:
            with Image.open(image_path) as img:
                if img.format == 'PNG' and hasattr(img, 'info'):
                    for key in ['parameters', 'prompt', 'workflow', 'comfyui']:
                        if key in img.info:
                            try:
                                metadata['prompt'] = json.loads(img.info[key])
                            except:
                                metadata['prompt'] = img.info[key]
                            metadata['ai_generated'] = True
                            metadata['generator'] = 'comfyui'
                            break
                    if 'parameters' in img.info:
                        params = img.info['parameters']
                        if 'Steps:' in params or 'Sampler:' in params:
                            parts = params.split('Negative prompt:')
                            metadata['prompt'] = parts[0].strip()
                            if len(parts) > 1:
                                metadata['negative_prompt'] = parts[1].split('Steps:')[0].strip()
                            metadata['ai_generated'] = True
                            metadata['generator'] = 'stable-diffusion'
                            for param in ['Steps', 'Sampler', 'CFG scale', 'Seed', 'Size']:
                                if f'{param}:' in params:
                                    try:
                                        value = params.split(f'{param}:')[1].split(',')[0].strip()
                                        metadata[param.lower().replace(' ', '_')] = value
                                    except:
                                        pass
                metadata['width'] = img.width
                metadata['height'] = img.height
                metadata['format'] = img.format
        except Exception as e:
            logger.warning("Metadata extraction failed for %s: %s", image_path, e)
        return metadata


class ColorExtractor:
    """Extract dominant color palette using PIL quantize (no sklearn needed)."""

    def __init__(self, n_dominant: int = 5):
        self.n_dominant = n_dominant

    def extract(self, image: Image.Image) -> Dict[str, Any]:
        try:
            small = image.resize((150, 150), Image.LANCZOS).convert('RGB')
            quantized = small.quantize(colors=self.n_dominant, method=2)
            palette = quantized.getpalette()[:self.n_dominant * 3]
            colors = []
            for i in range(self.n_dominant):
                r, g, b = palette[i * 3:i * 3 + 3]
                colors.append({"hex": f"#{r:02x}{g:02x}{b:02x}", "rgb": [r, g, b]})
            # Classify palette
            palette_type = self._classify(colors)
            return {"dominant": colors, "palette_type": palette_type}
        except Exception as e:
            logger.warning("Color extraction failed: %s", e)
            return {}

    @staticmethod
    def _classify(colors: List[Dict]) -> str:
        if not colors:
            return "unknown"
        hues, sats, vals = [], [], []
        for c in colors:
            r, g, b = [x / 255.0 for x in c['rgb']]
            h, s, v = colorsys.rgb_to_hsv(r, g, b)
            hues.append(h)
            sats.append(s)
            vals.append(v)
        avg_sat = sum(sats) / len(sats)
        avg_val = sum(vals) / len(vals)
        if avg_sat < 0.15:
            return "monochrome"
        if avg_val > 0.7 and avg_sat > 0.5:
            return "vibrant"
        if avg_val < 0.4:
            return "dark"
        hue_std = max(hues) - min(hues)
        if hue_std < 0.1:
            return "warm" if 0.0 < sum(hues) / len(hues) < 0.15 or 0.9 < sum(hues) / len(hues) < 1.0 else "cool"
        return "mixed"


class TagVerifier:
    """3-layer tag verification: normalize, filter, quality-score."""

    STOPWORDS = {
        'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'for', 'from',
        'with', 'by', 'at', 'as', 'is', 'are', 'was', 'were', 'be', 'been',
        'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
        'dare', 'ought', 'used', 'this', 'that', 'these', 'those', 'i', 'you',
        'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her', 'us', 'them',
        'image', 'photo', 'picture', 'photograph', 'shot', 'scene', 'view',
        'file', 'media', 'asset', 'subject', 'subjects', 'context',
    }

    def __init__(self, max_tags: int = 30, min_len: int = 2, max_len: int = 25):
        self.max_tags = max_tags
        self.min_len = min_len
        self.max_len = max_len

    def verify(self, raw_tags: List[str]) -> Dict[str, Any]:
        # Layer 1: Normalize
        normalized = self._normalize(raw_tags)
        # Layer 2: Filter
        filtered = self._filter(normalized)
        # Layer 3: Quality score
        score, issues = self._score(filtered, normalized)
        return {
            "original": raw_tags,
            "cleaned": filtered,
            "quality_score": score,
            "issues": issues,
        }

    def _normalize(self, tags: List[str]) -> List[str]:
        out = []
        for t in tags:
            s = str(t).strip().lower()
            s = re.sub(r'[^a-z0-9\s\-/#]', '', s)
            s = re.sub(r'\s+', ' ', s)
            if s:
                out.append(s)
        return out

    def _filter(self, tags: List[str]) -> List[str]:
        out = []
        seen = set()
        for t in tags:
            if t in self.STOPWORDS:
                continue
            if len(t) < self.min_len or len(t) > self.max_len:
                continue
            if t in seen:
                continue
            seen.add(t)
            out.append(t)
        return out[:self.max_tags]

    def _score(self, final: List[str], original: List[str]) -> Tuple[float, List[str]]:
        issues = []
        score = 1.0
        if len(final) < 3:
            issues.append("too_few_tags")
            score -= 0.2
        if len(final) > self.max_tags:
            issues.append("too_many_tags")
            score -= 0.1
        dedup_ratio = len(final) / max(len(original), 1)
        if dedup_ratio < 0.5:
            issues.append("high_duplication")
            score -= 0.15
        return max(0.0, score), issues


def extract_audio_metadata
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

        # Check cache (skip for text since contents may vary by read mode)
        if media_kind != "text":
            cached = _get_cached(contents)
            if cached:
                logger.info("Cache hit for %s", filename)
                # Sanitize cached tags in case they were stored with old prefixes
                result = dict(cached)
                if "tags" in result and isinstance(result["tags"], list):
                    result["tags"] = sanitize_tags(result["tags"])
                return {**result, "cached": True}

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
                
                # Extract ComfyUI metadata if enabled
                metadata = {}
                if os.getenv("EXTRACT_METADATA", "true").lower() == "true":
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=Path(filename).suffix, delete=False) as tmp:
                        tmp.write(contents)
                        tmp_path = tmp.name
                    try:
                        metadata = MetadataExtractor.extract_comfyui_metadata(Path(tmp_path))
                    finally:
                        try:
                            os.unlink(tmp_path)
                        except:
                            pass
                
                analysis = self.client.analyze_image(image, prompt)
                result = self._format_result(filename, analysis, media_kind)
                
                # Extract color palette
                if os.getenv("EXTRACT_COLORS", "true").lower() == "true":
                    cv = ColorExtractor(n_dominant=5)
                    result["color_palette"] = cv.extract(image)
                
                # Apply 3-layer tag verification
                if "tags" in result:
                    verifier = TagVerifier(
                        max_tags=int(os.getenv("MAX_TAGS", "30")),
                        min_len=int(os.getenv("MIN_TAG_LENGTH", "2")),
                        max_len=int(os.getenv("MAX_TAG_LENGTH", "25")),
                    )
                    result["verified_tags"] = verifier.verify(result["tags"])
                    result["tags"] = result["verified_tags"]["cleaned"]
                
                result["metadata"] = metadata
                # Final sanitize pass on tags before caching and returning
                if "tags" in result and isinstance(result["tags"], list):
                    result["tags"] = sanitize_tags(result["tags"])
                if "verified_tags" in result and isinstance(result["verified_tags"], dict):
                    cleaned = result["verified_tags"].get("cleaned", [])
                    result["verified_tags"]["cleaned"] = sanitize_tags(cleaned)
                _set_cached(contents, result)
                return result
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
            result = self._format_result(filename, analysis, media_kind)
            if "tags" in result and isinstance(result["tags"], list):
                result["tags"] = sanitize_tags(result["tags"])
            _set_cached(contents, result)
            return result

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
                result = self._format_result(filename, merged_analysis, media_kind)
                if "tags" in result and isinstance(result["tags"], list):
                    result["tags"] = sanitize_tags(result["tags"])
                _set_cached(contents, result)
                return result
                
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
                if "tags" in result and isinstance(result["tags"], list):
                    result["tags"] = sanitize_tags(result["tags"])
                _set_cached(contents, result)
                return result
            except Exception as e:
                logger.error("Error processing audio %s: %s", filename, e)
                return {
                    "file": filename,
                    "media_kind": media_kind,
                    "error": f"Audio processing failed: {str(e)}",
                    "retryable": False,
                }

        result = {
            "file": filename,
            "media_kind": media_kind,
            "error": "Unsupported media type",
            "retryable": False,
        }
        _set_cached(contents, result)
        return result

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

        # Strip common prefix patterns that the LLM may have added
        # e.g., "Subject: black top" -> "black top"
        PREFIX_PATTERNS = [
            r"^Subject:\s*",
            r"^Genre:\s*",
            r"^Lighting:\s*",
            r"^Color/Tone:\s*",
            r"^Time/Season:\s*",
            r"^Similar Artist:\s*",
            r"^Cinematography:\s*",
            r"^Production:\s*",
            r"^Mood:\s*",
            r"^Instrumentation:\s*",
            r"^Structure:\s*",
            r"^Topic:\s*",
            r"^Tone:\s*",
            r"^Intent:\s*",
            r"^Entity:\s*",
            r"^subjects:\s*",
            r"^genre:\s*",
            r"^lighting:\s*",
            r"^color_and_tone:\s*",
            r"^time_or_season:\s*",
        ]

        cleaned = []
        for tag in collected:
            if not isinstance(tag, str):
                continue
            tag = str(tag).strip()
            if not tag:
                continue
            for pattern in PREFIX_PATTERNS:
                tag = re.sub(pattern, "", tag, flags=re.IGNORECASE)
            tag = tag.strip()
            if tag:
                cleaned.append(tag)

        return sorted({t for t in cleaned})


def sanitize_tags(tag_list: list[str]) -> list[str]:
    """Final safety pass: strip any remaining prefix patterns from tags."""
    PREFIX_PATTERNS = [
        r"^Subject\s*[:\-]\s*",
        r"^Genre\s*[:\-]\s*",
        r"^Lighting\s*[:\-]\s*",
        r"^Color[/\s]*Tone\s*[:\-]\s*",
        r"^Time[/\s]*Season\s*[:\-]\s*",
        r"^Similar\s*Artist\s*[:\-]\s*",
        r"^Cinematography\s*[:\-]\s*",
        r"^Production\s*[:\-]\s*",
        r"^Mood\s*[:\-]\s*",
        r"^Instrumentation\s*[:\-]\s*",
        r"^Structure\s*[:\-]\s*",
        r"^Topic\s*[:\-]\s*",
        r"^Tone\s*[:\-]\s*",
        r"^Intent\s*[:\-]\s*",
        r"^Entity\s*[:\-]\s*",
        r"^subjects\s*[:\-]\s*",
        r"^genre\s*[:\-]\s*",
        r"^lighting\s*[:\-]\s*",
        r"^color_and_tone\s*[:\-]\s*",
        r"^time_or_season\s*[:\-]\s*",
    ]
    out = []
    for tag in tag_list:
        if not isinstance(tag, str):
            continue
        tag = str(tag).strip()
        if not tag:
            continue
        for pattern in PREFIX_PATTERNS:
            tag = re.sub(pattern, "", tag, flags=re.IGNORECASE)
        tag = tag.strip()
        if tag and tag not in out:
            out.append(tag)
    return out


# -------------------------------------------------------------------------
# CLI & Server
# -------------------------------------------------------------------------

app_instance = LocalCuraApp()

# Clear analysis cache on startup to ensure fresh results (old prefixed tags purged)
clear_cache()

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


@app.get("/cache/stats")
def cache_stats():
    return {
        "cached_entries": len(_analysis_cache),
        "max_size": _CACHE_MAX_SIZE,
    }


@app.post("/cache/clear")
def cache_clear():
    clear_cache()
    return {"status": "cleared"}


@app.get("/models")
def list_models():
    """List installed Ollama models with vision capability detection."""
    base = app_instance.cfg.ollama_base_url.rstrip("/api").rstrip("/")
    try:
        resp = requests.get(f"{base}/api/tags", timeout=5)
        resp.raise_for_status()
        raw = resp.json().get("models", [])
        models = []
        for m in raw:
            name = m.get("name", "")
            size = m.get("size", 0)
            size_gb = round(size / (1024 ** 3), 2) if size else 0
            # Heuristic: vision models usually have 'vl' or vision-related names
            is_vision = any(k in name.lower() for k in ['vl', 'vision', 'llava', 'bakllava', 'moondream', 'cogvlm'])
            models.append({
                "name": name,
                "size_gb": size_gb,
                "vision": is_vision,
                "modified": m.get("modified_at", ""),
            })
        models.sort(key=lambda x: x["size_gb"], reverse=True)
        return {
            "models": models,
            "recommended": next((m["name"] for m in models if m["vision"]), None),
            "current": app_instance.cfg.ollama_model,
        }
    except Exception as e:
        return {"error": str(e), "models": []}


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
