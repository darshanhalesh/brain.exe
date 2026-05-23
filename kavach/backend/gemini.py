"""
backend/gemini.py
──────────────────────────────────────────────────────────────────────────────
Gemini Live API integration for trigger word detection and voice analysis.
The ESP32 streams audio → Gemini detects trigger word → returns structured JSON.
"""

import os
import json
import httpx
from loguru import logger

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash-exp"
TRIGGER_WORDS = ["kavach", "shield", "help me", "bachao"]


async def analyze_trigger(audio_b64: str = None, transcript: str = None) -> dict:
    """
    Analyze voice input for trigger word + initial stress indicators.
    
    In MVP: accepts transcript from ESP32 (Gemini already decoded on device).
    In prod: stream raw audio to Gemini Live API.
    
    Returns:
        {
          "trigger_detected": bool,
          "trigger_word": str,
          "transcript": str,
          "initial_stress": float,  # 0-1 rough estimate
          "language": str,
        }
    """
    if not GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY not set — using mock trigger detection")
        return _mock_trigger(transcript)

    prompt = f"""
You are analyzing voice input from a women's safety device called Kavach.

Transcript: "{transcript or '[audio]'}"

Determine:
1. Was any trigger/safety word detected? (kavach, shield, help me, bachao, or similar distress phrases)
2. Estimate voice stress level from transcript patterns (0.0=calm, 1.0=extreme panic)
3. Detect language

Respond ONLY with valid JSON:
{{
  "trigger_detected": true/false,
  "trigger_word": "word detected or null",
  "initial_stress": 0.0-1.0,
  "language": "en/hi/kn/te/etc",
  "confidence": 0.0-1.0
}}
"""

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
                headers={"Content-Type": "application/json"},
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "maxOutputTokens": 200},
                },
                timeout=8.0,
            )
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            clean = text.strip().strip("```json").strip("```").strip()
            return json.loads(clean)
    except Exception as e:
        logger.error(f"Gemini API error: {e}")
        return _mock_trigger(transcript)


def _mock_trigger(transcript: str = None) -> dict:
    """Mock trigger detection for demo/testing."""
    text = (transcript or "").lower()
    triggered = any(w in text for w in TRIGGER_WORDS)
    return {
        "trigger_detected": triggered,
        "trigger_word": next((w for w in TRIGGER_WORDS if w in text), None),
        "initial_stress": 0.7 if triggered else 0.1,
        "language": "en",
        "confidence": 0.9,
        "source": "mock",
    }
