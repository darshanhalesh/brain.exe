"""
quantum/train.py
──────────────────────────────────────────────────────────────────────────────
Trains a Variational Quantum Classifier (VQC) on voice stress features.

Dataset: RAVDESS (Ryerson Audio-Visual Database of Emotional Speech and Song)
         Download from Kaggle: https://www.kaggle.com/datasets/uwrfkaggler/ravdess-emotional-speech-audio
         Place audio files in: quantum/data/ravdess/

Features extracted per audio clip:
  - Mean pitch (Hz)
  - Pitch variance (tremor proxy)
  - Speech rate (zero-crossing rate)
  - Pause ratio (silence-to-speech ratio)

QML Architecture:
  4 input features → AngleEmbedding → 2 layers of StronglyEntanglingLayers
  → PauliZ measurement → sigmoid → threat score (0.0–1.0)
"""

import os
import numpy as np
import pennylane as qml
from pennylane import numpy as pnp
import librosa
import json
from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import classification_report
import pickle
from loguru import logger

# ── Config ──────────────────────────────────────────────────────────────────
SEED = 42
N_QUBITS = 4
N_LAYERS = 2
LEARNING_RATE = 0.01
EPOCHS = 60
BATCH_SIZE = 16
MODEL_DIR = Path("quantum/model")
DATA_DIR = Path("quantum/data/ravdess")

np.random.seed(SEED)
MODEL_DIR.mkdir(parents=True, exist_ok=True)


# ── Feature Extraction ───────────────────────────────────────────────────────
def extract_features(audio_path: str) -> np.ndarray | None:
    """Extract 4 voice stress features from an audio file."""
    try:
        y, sr = librosa.load(audio_path, sr=22050, duration=3.0)

        # 1. Mean pitch
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        pitch_vals = pitches[magnitudes > np.median(magnitudes)]
        mean_pitch = float(np.mean(pitch_vals)) if len(pitch_vals) > 0 else 0.0

        # 2. Pitch variance (tremor proxy)
        pitch_var = float(np.var(pitch_vals)) if len(pitch_vals) > 0 else 0.0

        # 3. Speech rate (zero crossing rate mean)
        zcr = librosa.feature.zero_crossing_rate(y)
        speech_rate = float(np.mean(zcr))

        # 4. Pause ratio (RMS energy below threshold)
        rms = librosa.feature.rms(y=y)[0]
        silence_threshold = np.percentile(rms, 20)
        pause_ratio = float(np.mean(rms < silence_threshold))

        return np.array([mean_pitch, pitch_var, speech_rate, pause_ratio])
    except Exception as e:
        logger.warning(f"Feature extraction failed for {audio_path}: {e}")
        return None


def load_ravdess_labels(audio_path: str) -> int:
    """
    RAVDESS filename: 03-01-{emotion}-{intensity}-{statement}-{repetition}-{actor}.wav
    Emotion codes: 01=neutral, 02=calm, 03=happy, 04=sad, 05=angry, 06=fearful, 07=disgust, 08=surprised
    Binary: 0 = low stress (neutral, calm, happy), 1 = high stress (angry, fearful, disgust)
    """
    fname = Path(audio_path).stem
    parts = fname.split("-")
    if len(parts) < 3:
        return -1
    emotion_code = int(parts[2])
    return 1 if emotion_code in [05, 06, 07] else 0


def build_dataset():
    """Load RAVDESS audio files and extract features + labels."""
    features, labels = [], []

    if not DATA_DIR.exists():
        logger.warning(f"RAVDESS data not found at {DATA_DIR}. Generating synthetic dataset for demo.")
        return _synthetic_dataset()

    audio_files = list(DATA_DIR.rglob("*.wav"))
    logger.info(f"Found {len(audio_files)} audio files")

    for fpath in audio_files:
        feats = extract_features(str(fpath))
        label = load_ravdess_labels(str(fpath))
        if feats is not None and label != -1:
            features.append(feats)
            labels.append(label)

    if len(features) == 0:
        logger.warning("No valid audio files processed. Using synthetic dataset.")
        return _synthetic_dataset()

    logger.info(f"Loaded {len(features)} samples | Stressed: {sum(labels)} | Calm: {len(labels)-sum(labels)}")
    return np.array(features), np.array(labels)


def _synthetic_dataset():
    """Synthetic fallback for demo/testing without RAVDESS."""
    logger.info("Generating synthetic voice stress dataset (demo mode)")
    np.random.seed(SEED)
    n = 200

    # Calm voices: low pitch variance, moderate speech rate, higher pauses
    calm = np.column_stack([
        np.random.normal(180, 20, n // 2),   # mean pitch
        np.random.normal(500, 100, n // 2),  # pitch var
        np.random.normal(0.05, 0.01, n // 2), # speech rate
        np.random.normal(0.4, 0.05, n // 2),  # pause ratio
    ])

    # Stressed voices: higher pitch, more variance, faster rate, fewer pauses
    stressed = np.column_stack([
        np.random.normal(250, 40, n // 2),   # mean pitch
        np.random.normal(2000, 400, n // 2), # pitch var (tremor)
        np.random.normal(0.09, 0.02, n // 2), # speech rate
        np.random.normal(0.15, 0.05, n // 2), # pause ratio
    ])

    X = np.vstack([calm, stressed])
    y = np.array([0] * (n // 2) + [1] * (n // 2))
    idx = np.random.permutation(len(X))
    return X[idx], y[idx]


# ── Quantum Circuit ──────────────────────────────────────────────────────────
dev = qml.device("default.qubit", wires=N_QUBITS)

@qml.qnode(dev)
def vqc_circuit(inputs, weights):
    """4-qubit Variational Quantum Classifier circuit."""
    # Normalize inputs to [0, π]
    qml.AngleEmbedding(inputs * np.pi, wires=range(N_QUBITS), rotation="Y")
    # Variational layers
    qml.StronglyEntanglingLayers(weights, wires=range(N_QUBITS))
    return qml.expval(qml.PauliZ(0))


def predict_proba(inputs: np.ndarray, weights: np.ndarray) -> float:
    """Returns threat probability [0, 1]."""
    raw = vqc_circuit(inputs, weights)
    return float((1 - raw) / 2)  # map [-1,1] → [0,1]


# ── Training ─────────────────────────────────────────────────────────────────
def cost_fn(weights, X_batch, y_batch):
    """Binary cross-entropy loss."""
    loss = 0.0
    for x, y in zip(X_batch, y_batch):
        pred = predict_proba(x, weights)
        pred = np.clip(pred, 1e-7, 1 - 1e-7)
        loss += -(y * np.log(pred) + (1 - y) * np.log(1 - pred))
    return loss / len(X_batch)


def train():
    logger.info("── Kavach QML Training ──")

    # Load data
    X, y = build_dataset()

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_scaled = np.clip(X_scaled, -1, 1)  # keep in valid angle range

    # Split
    X_train, X_test, y_train, y_test = train_test_split(
        X_scaled, y, test_size=0.2, random_state=SEED, stratify=y
    )

    # Init weights
    weight_shape = qml.StronglyEntanglingLayers.shape(n_layers=N_LAYERS, n_wires=N_QUBITS)
    weights = pnp.random.uniform(-np.pi, np.pi, weight_shape, requires_grad=True)

    # Optimizer
    opt = qml.AdamOptimizer(stepsize=LEARNING_RATE)

    # Training loop
    best_loss = float("inf")
    best_weights = None

    for epoch in range(EPOCHS):
        # Shuffle
        idx = np.random.permutation(len(X_train))
        X_train, y_train = X_train[idx], y_train[idx]

        epoch_loss = 0.0
        for i in range(0, len(X_train), BATCH_SIZE):
            X_b = X_train[i:i+BATCH_SIZE]
            y_b = y_train[i:i+BATCH_SIZE]
            weights, loss = opt.step_and_cost(cost_fn, weights, X_batch=X_b, y_batch=y_b)
            epoch_loss += float(loss)

        avg_loss = epoch_loss / max(1, len(X_train) // BATCH_SIZE)

        if avg_loss < best_loss:
            best_loss = avg_loss
            best_weights = np.array(weights)

        if (epoch + 1) % 10 == 0:
            # Quick accuracy on test
            preds = [1 if predict_proba(x, weights) > 0.5 else 0 for x in X_test]
            acc = np.mean(np.array(preds) == y_test)
            logger.info(f"Epoch {epoch+1:3d}/{EPOCHS} | Loss: {avg_loss:.4f} | Test Acc: {acc:.3f}")

    # Final eval
    final_preds = [1 if predict_proba(x, best_weights) > 0.5 else 0 for x in X_test]
    logger.info("\n── Final Evaluation ──")
    logger.info(f"\n{classification_report(y_test, final_preds, target_names=['Calm', 'Stressed'])}")

    # Save
    np.save(MODEL_DIR / "vqc_weights.npy", best_weights)
    with open(MODEL_DIR / "scaler.pkl", "wb") as f:
        pickle.dump(scaler, f)

    meta = {
        "n_qubits": N_QUBITS,
        "n_layers": N_LAYERS,
        "seed": SEED,
        "features": ["mean_pitch", "pitch_variance", "speech_rate", "pause_ratio"],
        "dataset": "RAVDESS (or synthetic fallback)",
        "final_loss": float(best_loss),
    }
    with open(MODEL_DIR / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    logger.info(f"Model saved to {MODEL_DIR}/")
    return best_weights, scaler


if __name__ == "__main__":
    train()
