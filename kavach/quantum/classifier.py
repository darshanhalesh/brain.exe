"""
quantum/classifier.py
──────────────────────────────────────────────────────────────────────────────
QML inference module. Loads trained VQC weights and runs threat scoring
on live voice feature vectors extracted from ESP32 audio.
"""

import numpy as np
import pennylane as qml
import pickle
import json
from pathlib import Path
from loguru import logger

MODEL_DIR = Path("quantum/model")
N_QUBITS = 4
N_LAYERS = 2

dev = qml.device("default.qubit", wires=N_QUBITS)

@qml.qnode(dev)
def vqc_circuit(inputs, weights):
    qml.AngleEmbedding(inputs * np.pi, wires=range(N_QUBITS), rotation="Y")
    qml.StronglyEntanglingLayers(weights, wires=range(N_QUBITS))
    return qml.expval(qml.PauliZ(0))


class KavachQMLClassifier:
    """
    Loads trained VQC and scores voice stress in real time.
    
    Threat probability → Kavach level:
      0.0 – 0.30 → Level 1 (Low)
      0.30 – 0.60 → Level 2 (Medium)
      0.60 – 0.85 → Level 3 (High)
      0.85 – 1.00 → Level 4 (Critical)
    """

    THRESHOLDS = [0.30, 0.60, 0.85]

    def __init__(self):
        self.weights = None
        self.scaler = None
        self.meta = {}
        self._loaded = False

    def load(self):
        weights_path = MODEL_DIR / "vqc_weights.npy"
        scaler_path = MODEL_DIR / "scaler.pkl"
        meta_path = MODEL_DIR / "meta.json"

        if not weights_path.exists():
            logger.warning("QML model not found. Run: python quantum/train.py")
            logger.warning("Falling back to heuristic scoring.")
            return self

        self.weights = np.load(weights_path)
        with open(scaler_path, "rb") as f:
            self.scaler = pickle.load(f)
        if meta_path.exists():
            with open(meta_path) as f:
                self.meta = json.load(f)

        self._loaded = True
        logger.info(f"QML model loaded | Qubits: {N_QUBITS} | Layers: {N_LAYERS}")
        return self

    def score(self, features: dict) -> dict:
        """
        Args:
            features: dict with keys:
                mean_pitch, pitch_variance, speech_rate, pause_ratio
        Returns:
            dict: threat_score, threat_level, confidence, breakdown
        """
        vec = np.array([
            features.get("mean_pitch", 0.0),
            features.get("pitch_variance", 0.0),
            features.get("speech_rate", 0.0),
            features.get("pause_ratio", 0.0),
        ])

        if not self._loaded:
            return self._heuristic_score(vec, features)

        # Scale
        vec_scaled = self.scaler.transform(vec.reshape(1, -1))[0]
        vec_scaled = np.clip(vec_scaled, -1, 1)

        # QML inference
        raw = vqc_circuit(vec_scaled, self.weights)
        threat_score = float((1 - raw) / 2)

        level = self._score_to_level(threat_score)

        return {
            "threat_score": round(threat_score, 4),
            "threat_level": level,
            "confidence": round(abs(raw), 3),
            "method": "QML_VQC",
            "breakdown": {
                "mean_pitch": round(float(vec[0]), 2),
                "pitch_variance": round(float(vec[1]), 2),
                "speech_rate": round(float(vec[2]), 4),
                "pause_ratio": round(float(vec[3]), 4),
            }
        }

    def _score_to_level(self, score: float) -> int:
        if score < self.THRESHOLDS[0]:
            return 1
        elif score < self.THRESHOLDS[1]:
            return 2
        elif score < self.THRESHOLDS[2]:
            return 3
        return 4

    def _heuristic_score(self, vec: np.ndarray, features: dict) -> dict:
        """Fallback scoring without trained model."""
        pitch = features.get("mean_pitch", 150)
        variance = features.get("pitch_variance", 500)
        rate = features.get("speech_rate", 0.05)
        pauses = features.get("pause_ratio", 0.4)

        score = 0.0
        score += min(0.3, (pitch - 150) / 300) if pitch > 150 else 0
        score += min(0.3, variance / 5000)
        score += min(0.2, (rate - 0.04) / 0.08) if rate > 0.04 else 0
        score += min(0.2, (0.4 - pauses) / 0.4) if pauses < 0.4 else 0
        score = float(np.clip(score, 0.0, 1.0))

        return {
            "threat_score": round(score, 4),
            "threat_level": self._score_to_level(score),
            "confidence": 0.5,
            "method": "heuristic_fallback",
            "breakdown": {
                "mean_pitch": round(float(vec[0]), 2),
                "pitch_variance": round(float(vec[1]), 2),
                "speech_rate": round(float(vec[2]), 4),
                "pause_ratio": round(float(vec[3]), 4),
            }
        }


# Singleton
classifier = KavachQMLClassifier()
