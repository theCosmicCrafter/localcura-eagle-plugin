import logging
import numpy as np
import librosa
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger("localcura.audio")


class AudioAnalyzer:
    """
    Analyzes audio files for basic properties and content tags.
    Uses librosa for feature extraction.
    """

    def __init__(self):
        self.supported_exts = {".mp3", ".wav", ".ogg", ".flac", ".m4a"}

    def is_audio(self, filepath: Path) -> bool:
        return filepath.suffix.lower() in self.supported_exts

    def analyze(self, filepath: Path) -> Dict[str, Any]:
        """
        Analyze audio file to extract tempo, duration, and basic acoustic tags.
        """
        try:
            # Load audio (limited duration to save memory/time)
            y, sr = librosa.load(str(filepath), duration=60)

            # Extract features
            duration = librosa.get_duration(y=y, sr=sr)
            tempo, _ = librosa.feature.beat.beat_track(y=y, sr=sr)
            zero_crossing_rate = np.mean(librosa.feature.zero_crossing_rate(y))
            spectral_centroid = np.mean(librosa.feature.spectral_centroid(y=y, sr=sr))

            tags = []

            # Tempo tags
            bpm = round(float(tempo))
            tags.append(f"{bpm} bpm")
            if bpm < 60:
                tags.append("slow tempo")
            elif bpm > 120:
                tags.append("fast tempo")
            else:
                tags.append("medium tempo")

            # Duration tags
            if duration < 10:
                tags.append("short clip")
            elif duration > 60:
                tags.append("long track")

            # Acoustic tags (rudimentary heuristics)
            if zero_crossing_rate > 0.1:
                tags.append("noisy")  # High freq content
            else:
                tags.append("clean")

            if spectral_centroid < 1000:
                tags.append("bass heavy")
            elif spectral_centroid > 3000:
                tags.append("bright")

            return {
                "tags": tags,
                "bpm": bpm,
                "duration": round(duration, 2),
                "summary": f"Audio clip, {bpm} BPM, {round(duration)}s duration",
            }

        except Exception as e:
            logger.error(f"Audio analysis failed for {filepath}: {e}")
            return {"tags": [], "error": str(e)}
