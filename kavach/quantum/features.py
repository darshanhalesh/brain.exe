"""
quantum/features.py
──────────────────────────────────────────────────────────────────────────────
Extracts voice stress features from raw audio bytes or file path.
Used by FastAPI backend to prepare input for QML classifier.
"""

import numpy as np
import librosa
import io
from loguru import logger


def extract_from_bytes(audio_bytes: bytes, sr: int = 22050) -> dict:
    """Extract voice features from raw PCM/WAV audio bytes."""
    try:
        audio_file = io.BytesIO(audio_bytes)
        y, sr = librosa.load(audio_file, sr=sr, duration=5.0)
        return _extract(y, sr)
    except Exception as e:
        logger.error(f"Feature extraction from bytes failed: {e}")
        return _default_features()


def extract_from_file(path: str, sr: int = 22050) -> dict:
    """Extract voice features from audio file."""
    try:
        y, sr = librosa.load(path, sr=sr, duration=5.0)
        return _extract(y, sr)
    except Exception as e:
        logger.error(f"Feature extraction from file failed: {e}")
        return _default_features()


def _extract(y: np.ndarray, sr: int) -> dict:
    # Pitch
    pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
    pitch_vals = pitches[magnitudes > np.median(magnitudes)]
    mean_pitch = float(np.mean(pitch_vals)) if len(pitch_vals) > 0 else 150.0
    pitch_var = float(np.var(pitch_vals)) if len(pitch_vals) > 0 else 500.0

    # Speech rate
    zcr = librosa.feature.zero_crossing_rate(y)
    speech_rate = float(np.mean(zcr))

    # Pause ratio
    rms = librosa.feature.rms(y=y)[0]
    silence_threshold = np.percentile(rms, 20)
    pause_ratio = float(np.mean(rms < silence_threshold))

    # MFCC energy (bonus feature for logging)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
    mfcc_energy = float(np.mean(np.abs(mfcc[0])))

    return {
        "mean_pitch": round(mean_pitch, 2),
        "pitch_variance": round(pitch_var, 2),
        "speech_rate": round(speech_rate, 6),
        "pause_ratio": round(pause_ratio, 4),
        "mfcc_energy": round(mfcc_energy, 4),
    }


def _default_features() -> dict:
    return {
        "mean_pitch": 150.0,
        "pitch_variance": 500.0,
        "speech_rate": 0.05,
        "pause_ratio": 0.4,
        "mfcc_energy": 0.0,
    }
