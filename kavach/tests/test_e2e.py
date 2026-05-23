"""
tests/test_e2e.py
──────────────────────────────────────────────────────────────────────────────
End-to-end tests for Kavach VoiceShield core flow.
Run: pytest tests/ -v
"""

import pytest
import asyncio
import numpy as np
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ── QML Tests ─────────────────────────────────────────────────────────────────

class TestQMLClassifier:
    def test_classifier_loads(self):
        from quantum.classifier import KavachQMLClassifier
        clf = KavachQMLClassifier()
        # Without trained model, should fall back to heuristic
        result = clf.score({
            "mean_pitch": 200.0,
            "pitch_variance": 1000.0,
            "speech_rate": 0.07,
            "pause_ratio": 0.2,
        })
        assert "threat_score" in result
        assert "threat_level" in result
        assert 0 <= result["threat_score"] <= 1
        assert 1 <= result["threat_level"] <= 4

    def test_calm_voice_low_threat(self):
        from quantum.classifier import KavachQMLClassifier
        clf = KavachQMLClassifier()
        result = clf.score({
            "mean_pitch": 160.0,
            "pitch_variance": 300.0,
            "speech_rate": 0.04,
            "pause_ratio": 0.45,
        })
        assert result["threat_level"] in [1, 2], f"Calm voice should be low threat, got level {result['threat_level']}"

    def test_stressed_voice_high_threat(self):
        from quantum.classifier import KavachQMLClassifier
        clf = KavachQMLClassifier()
        result = clf.score({
            "mean_pitch": 320.0,
            "pitch_variance": 4500.0,
            "speech_rate": 0.12,
            "pause_ratio": 0.05,
        })
        assert result["threat_level"] >= 2, f"Stressed voice should be medium+ threat, got level {result['threat_level']}"

    def test_score_to_level_mapping(self):
        from quantum.classifier import KavachQMLClassifier
        clf = KavachQMLClassifier()
        assert clf._score_to_level(0.1) == 1
        assert clf._score_to_level(0.45) == 2
        assert clf._score_to_level(0.7) == 3
        assert clf._score_to_level(0.9) == 4


# ── PQC Encryption Tests ──────────────────────────────────────────────────────

class TestPQCEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        from encryption.pqc import KavachPQC
        pqc = KavachPQC()
        payload = {
            "incident_id": "TEST001",
            "latitude": 12.9716,
            "longitude": 77.5946,
            "message": "Test SOS",
        }
        encrypted = pqc.encrypt(payload)
        assert "ciphertext" in encrypted
        assert "nonce" in encrypted
        assert "scheme" in encrypted

        decrypted = pqc.decrypt(encrypted)
        assert decrypted["incident_id"] == payload["incident_id"]
        assert decrypted["latitude"] == payload["latitude"]

    def test_encryption_scheme_present(self):
        from encryption.pqc import KavachPQC
        pqc = KavachPQC()
        result = pqc.encrypt({"test": "data"})
        assert result["scheme"] in ["Kyber512+AES256GCM", "AES256GCM_demo"]

    def test_different_keys_different_ciphertext(self):
        from encryption.pqc import KavachPQC
        pqc1 = KavachPQC()
        pqc2 = KavachPQC()
        payload = {"msg": "hello"}
        enc1 = pqc1.encrypt(payload)
        enc2 = pqc2.encrypt(payload)
        # Different keypairs → different ciphertexts
        assert enc1["ciphertext"] != enc2["ciphertext"]


# ── Alert Optimizer Tests ─────────────────────────────────────────────────────

class TestAlertOptimizer:
    def test_optimize_contact_order(self):
        from backend.optimizer import Contact, optimize_alert_order
        contacts = [
            Contact("c1", "Priya", "+91111", distance_km=5.0, avg_response_time_s=30.0, priority_weight=4.0),
            Contact("c2", "Mom", "+91222", distance_km=2.0, avg_response_time_s=15.0, priority_weight=5.0),
            Contact("c3", "Friend", "+91333", distance_km=10.0, avg_response_time_s=60.0, priority_weight=2.0),
        ]
        ranked = optimize_alert_order(contacts, threat_level=2)
        assert len(ranked) == 3
        # Mom should rank highest (closest + fastest + highest priority)
        assert ranked[0].id == "c2"

    def test_level3_alerts_all(self):
        from backend.optimizer import Contact, optimize_alert_order
        contacts = [
            Contact("c1", "A", "+91111", 5.0, 30.0, 3.0),
            Contact("c2", "B", "+91222", 2.0, 15.0, 5.0),
        ]
        ranked = optimize_alert_order(contacts, threat_level=3)
        assert len(ranked) == 2  # All contacts at Level 3+

    def test_empty_contacts(self):
        from backend.optimizer import optimize_alert_order
        result = optimize_alert_order([], threat_level=2)
        assert result == []


# ── Feature Extraction Tests ──────────────────────────────────────────────────

class TestFeatureExtraction:
    def test_default_features_valid(self):
        from quantum.features import _default_features
        feats = _default_features()
        assert "mean_pitch" in feats
        assert "pitch_variance" in feats
        assert "speech_rate" in feats
        assert "pause_ratio" in feats
        assert feats["mean_pitch"] > 0


# ── Full Pipeline Integration Test ───────────────────────────────────────────

class TestFullPipeline:
    def test_trigger_to_dispatch_flow(self):
        """Simulate the full flow: features → QML → encrypt → ready for dispatch."""
        from quantum.classifier import KavachQMLClassifier
        from encryption.pqc import KavachPQC

        # Step 1: Voice features (simulated stressed voice)
        features = {
            "mean_pitch": 280.0,
            "pitch_variance": 3200.0,
            "speech_rate": 0.10,
            "pause_ratio": 0.08,
        }

        # Step 2: QML assessment
        clf = KavachQMLClassifier()
        result = clf.score(features)
        assert result["threat_level"] >= 1

        # Step 3: Build SOS payload
        sos = {
            "incident_id": "PIPE_TEST_001",
            "threat_level": result["threat_level"],
            "latitude": 12.9716,
            "longitude": 77.5946,
            "qml_score": result["threat_score"],
        }

        # Step 4: PQC encrypt
        pqc = KavachPQC()
        encrypted = pqc.encrypt(sos)
        assert encrypted["scheme"] in ["Kyber512+AES256GCM", "AES256GCM_demo"]

        # Step 5: Decrypt and verify integrity
        decrypted = pqc.decrypt(encrypted)
        assert decrypted["incident_id"] == sos["incident_id"]
        assert decrypted["qml_score"] == result["threat_score"]

        print(f"\n✅ Full pipeline: threat_level={result['threat_level']} | score={result['threat_score']:.3f} | scheme={encrypted['scheme']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
