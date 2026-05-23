"""
backend/main.py
──────────────────────────────────────────────────────────────────────────────
Kavach VoiceShield — FastAPI Orchestration Server

Endpoints:
  POST /trigger          — ESP32 sends voice trigger + audio blob
  POST /assess           — Run QML threat assessment on audio features
  POST /dispatch         — Encrypt + dispatch SOS to all channels
  GET  /status/{incident_id} — Get incident status
  GET  /incidents        — List all incidents
  WS   /ws/dashboard     — Real-time dashboard WebSocket
  WS   /ws/device/{id}   — ESP32 device WebSocket
  POST /monitor/start    — Start MONITOR mode
  POST /monitor/stop     — Stop MONITOR mode
  GET  /health           — Health check
"""

import asyncio
import json
import uuid
import os
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

from backend.state import incident_store, device_registry, monitor_state
from backend.alerts import dispatch_all_alerts
from backend.gemini import analyze_trigger
from backend.websocket_manager import ws_manager
from quantum.classifier import classifier
from quantum.features import extract_from_bytes
from encryption.pqc import pqc

# ── Lifespan ─────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🛡️  Kavach VoiceShield starting...")
    classifier.load()
    logger.info("✅ QML classifier ready")
    logger.info(f"✅ PQC scheme: {pqc.KEM_ALGORITHM if hasattr(pqc, 'KEM_ALGORITHM') else 'AES-256-GCM demo'}")
    yield
    logger.info("Kavach shutting down")

app = FastAPI(
    title="Kavach VoiceShield API",
    description="Women's safety voice alert system with Quantum ML and Post-Quantum Cryptography",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Models ────────────────────────────────────────────────────────────────────
class TriggerRequest(BaseModel):
    device_id: str
    trigger_word: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    timestamp: Optional[str] = None

class AssessRequest(BaseModel):
    incident_id: str
    mean_pitch: float = 150.0
    pitch_variance: float = 500.0
    speech_rate: float = 0.05
    pause_ratio: float = 0.4

class DispatchRequest(BaseModel):
    incident_id: str
    threat_level: int
    override_message: Optional[str] = None

class MonitorRequest(BaseModel):
    device_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    trusted_contacts: Optional[list] = None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "Kavach VoiceShield",
        "qml": classifier._loaded,
        "pqc_scheme": "Kyber512" if hasattr(pqc, '_kem') and pqc._kem else "AES256-demo",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/trigger")
async def receive_trigger(req: TriggerRequest, background_tasks: BackgroundTasks):
    """
    Step 1: ESP32 sends trigger word detection.
    Creates incident, schedules QML assessment + escalation timer.
    """
    incident_id = str(uuid.uuid4())[:8].upper()
    incident = {
        "id": incident_id,
        "device_id": req.device_id,
        "trigger_word": req.trigger_word,
        "latitude": req.latitude or 12.9716,   # default: Bengaluru
        "longitude": req.longitude or 77.5946,
        "threat_level": 1,
        "threat_score": 0.0,
        "status": "triggered",
        "audio_evidence": [],
        "alerts_sent": [],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    incident_store[incident_id] = incident
    logger.info(f"[{incident_id}] Trigger received from {req.device_id} | word='{req.trigger_word}'")

    # Notify dashboard
    await ws_manager.broadcast_dashboard({
        "event": "trigger",
        "incident": incident,
    })

    # Send confirmation whisper to ESP32
    await ws_manager.send_to_device(req.device_id, {
        "action": "speak",
        "text": "Kavach activated. Say 'safe' to cancel.",
    })

    # Start Level 1 escalation timer (10s)
    background_tasks.add_task(_level1_escalation_timer, incident_id, req.device_id)

    return {
        "incident_id": incident_id,
        "status": "triggered",
        "threat_level": 1,
        "message": "Kavach activated. Monitoring.",
    }


@app.post("/assess")
async def assess_threat(req: AssessRequest):
    """
    Step 2: QML threat scoring from voice features.
    Features extracted from audio on ESP32 side or server side.
    """
    incident = incident_store.get(req.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    features = {
        "mean_pitch": req.mean_pitch,
        "pitch_variance": req.pitch_variance,
        "speech_rate": req.speech_rate,
        "pause_ratio": req.pause_ratio,
    }

    result = classifier.score(features)
    threat_level = result["threat_level"]
    threat_score = result["threat_score"]

    # Update incident
    incident["threat_level"] = threat_level
    incident["threat_score"] = threat_score
    incident["qml_result"] = result
    incident["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"[{req.incident_id}] QML: score={threat_score:.3f} → Level {threat_level} | method={result['method']}")

    # Broadcast updated status
    await ws_manager.broadcast_dashboard({
        "event": "threat_assessed",
        "incident_id": req.incident_id,
        "threat_level": threat_level,
        "threat_score": threat_score,
        "qml_breakdown": result,
    })

    return result


@app.post("/assess/audio")
async def assess_from_audio(incident_id: str, audio: UploadFile = File(...)):
    """Assess threat from raw audio file upload."""
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    audio_bytes = await audio.read()
    features = extract_from_bytes(audio_bytes)
    result = classifier.score(features)

    incident["threat_level"] = result["threat_level"]
    incident["threat_score"] = result["threat_score"]
    incident["qml_result"] = result
    incident["audio_evidence"].append({
        "size_bytes": len(audio_bytes),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "encrypted": False,
    })
    incident["updated_at"] = datetime.now(timezone.utc).isoformat()

    await ws_manager.broadcast_dashboard({
        "event": "threat_assessed",
        "incident_id": incident_id,
        "threat_level": result["threat_level"],
        "threat_score": result["threat_score"],
    })

    return result


@app.post("/dispatch")
async def dispatch_sos(req: DispatchRequest, background_tasks: BackgroundTasks):
    """
    Step 3: Encrypt SOS payload and dispatch to all channels.
    Runs encryption + alert dispatch in background.
    """
    incident = incident_store.get(req.incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    threat_level = req.threat_level or incident.get("threat_level", 2)
    incident["status"] = "dispatching"
    incident["updated_at"] = datetime.now(timezone.utc).isoformat()

    # Build SOS payload
    sos_payload = {
        "incident_id": req.incident_id,
        "threat_level": threat_level,
        "latitude": incident["latitude"],
        "longitude": incident["longitude"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "device_id": incident["device_id"],
        "maps_link": f"https://maps.google.com/?q={incident['latitude']},{incident['longitude']}",
        "message": req.override_message or _default_message(threat_level),
    }

    # PQC encrypt
    encrypted = pqc.encrypt(sos_payload)
    incident["encrypted_payload"] = encrypted
    logger.info(f"[{req.incident_id}] SOS encrypted with {encrypted.get('scheme', 'unknown')}")

    # Dispatch in background
    background_tasks.add_task(dispatch_all_alerts, req.incident_id, sos_payload, threat_level)

    await ws_manager.broadcast_dashboard({
        "event": "dispatching",
        "incident_id": req.incident_id,
        "threat_level": threat_level,
        "encrypted_scheme": encrypted.get("scheme"),
    })

    return {
        "incident_id": req.incident_id,
        "status": "dispatching",
        "threat_level": threat_level,
        "encrypted_scheme": encrypted.get("scheme"),
        "channels": _channels_for_level(threat_level),
    }


@app.post("/safe/{incident_id}")
async def mark_safe(incident_id: str, device_id: str):
    """User confirms they are safe — cancel all escalations."""
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")

    incident["status"] = "resolved_safe"
    incident["resolved_at"] = datetime.now(timezone.utc).isoformat()
    incident["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"[{incident_id}] SAFE confirmed by {device_id}")

    await ws_manager.broadcast_dashboard({"event": "safe", "incident_id": incident_id})
    await ws_manager.send_to_device(device_id, {
        "action": "speak",
        "text": "Kavach deactivated. You are safe.",
    })

    return {"status": "resolved", "incident_id": incident_id}


@app.get("/status/{incident_id}")
async def get_status(incident_id: str):
    incident = incident_store.get(incident_id)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


@app.get("/incidents")
async def list_incidents(limit: int = 20):
    sorted_incidents = sorted(
        incident_store.values(),
        key=lambda x: x["created_at"],
        reverse=True
    )
    return {"incidents": sorted_incidents[:limit], "total": len(incident_store)}


@app.post("/monitor/start")
async def start_monitor(req: MonitorRequest, background_tasks: BackgroundTasks):
    """Start MONITOR mode — passive location tracking."""
    monitor_state[req.device_id] = {
        "active": True,
        "device_id": req.device_id,
        "latitude": req.latitude or 12.9716,
        "longitude": req.longitude or 77.5946,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_update": datetime.now(timezone.utc).isoformat(),
        "contacts": req.trusted_contacts or [],
    }

    background_tasks.add_task(_monitor_loop, req.device_id)
    logger.info(f"MONITOR mode started for {req.device_id}")

    return {"status": "monitoring", "device_id": req.device_id}


@app.post("/monitor/stop")
async def stop_monitor(device_id: str):
    if device_id in monitor_state:
        monitor_state[device_id]["active"] = False
    return {"status": "stopped", "device_id": device_id}


# ── WebSocket Endpoints ───────────────────────────────────────────────────────

@app.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    await ws_manager.connect_dashboard(websocket)
    try:
        # Send current state on connect
        await websocket.send_json({
            "event": "connected",
            "incidents": list(incident_store.values())[-10:],
            "monitor": list(monitor_state.values()),
        })
        while True:
            data = await websocket.receive_text()
            # Dashboard can send commands
            try:
                msg = json.loads(data)
                if msg.get("action") == "ping":
                    await websocket.send_json({"event": "pong"})
            except Exception:
                pass
    except WebSocketDisconnect:
        ws_manager.disconnect_dashboard(websocket)


@app.websocket("/ws/device/{device_id}")
async def device_ws(websocket: WebSocket, device_id: str):
    await ws_manager.connect_device(websocket, device_id)
    device_registry[device_id] = {"connected": True, "last_seen": datetime.now(timezone.utc).isoformat()}
    logger.info(f"ESP32 device connected: {device_id}")
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            await _handle_device_message(device_id, msg)
    except WebSocketDisconnect:
        ws_manager.disconnect_device(device_id)
        device_registry[device_id]["connected"] = False
        logger.info(f"ESP32 device disconnected: {device_id}")


# ── Background Tasks ──────────────────────────────────────────────────────────

async def _level1_escalation_timer(incident_id: str, device_id: str):
    """Wait 10s after Level 1 — if no 'safe' signal, escalate to Level 2."""
    await asyncio.sleep(10)
    incident = incident_store.get(incident_id)
    if not incident:
        return
    if incident["status"] in ("resolved_safe", "dispatching", "dispatched"):
        return

    if incident["threat_level"] == 1:
        logger.info(f"[{incident_id}] Level 1 timeout → escalating to Level 2")
        incident["threat_level"] = 2
        incident["status"] = "escalated"
        await ws_manager.broadcast_dashboard({
            "event": "escalated",
            "incident_id": incident_id,
            "new_level": 2,
            "reason": "No safe confirmation in 10s",
        })
        # Auto-dispatch Level 2
        await dispatch_all_alerts(incident_id, {
            "incident_id": incident_id,
            "threat_level": 2,
            "latitude": incident["latitude"],
            "longitude": incident["longitude"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device_id": device_id,
            "maps_link": f"https://maps.google.com/?q={incident['latitude']},{incident['longitude']}",
            "message": _default_message(2),
        }, 2)


async def _monitor_loop(device_id: str):
    """MONITOR mode: send location updates every 5 min, escalate at 10 min silence."""
    last_user_action = datetime.now(timezone.utc)
    update_count = 0

    while monitor_state.get(device_id, {}).get("active", False):
        await asyncio.sleep(300)  # 5 minutes
        state = monitor_state.get(device_id)
        if not state or not state["active"]:
            break

        update_count += 1
        state["last_update"] = datetime.now(timezone.utc).isoformat()

        await ws_manager.broadcast_dashboard({
            "event": "monitor_update",
            "device_id": device_id,
            "latitude": state["latitude"],
            "longitude": state["longitude"],
            "update_count": update_count,
        })

        # 10 min silence check (2 × 5min updates)
        if update_count % 2 == 0:
            logger.warning(f"MONITOR: No user action for 10min on {device_id} — escalating to Level 2")
            # Trigger Level 2 protocol
            await ws_manager.send_to_device(device_id, {
                "action": "speak",
                "text": "Are you safe? Say 'safe' to confirm.",
            })


async def _handle_device_message(device_id: str, msg: dict):
    """Handle incoming messages from ESP32 device."""
    action = msg.get("action")
    logger.debug(f"[{device_id}] Message: {action}")

    if action == "trigger":
        # Handled via REST endpoint normally; WebSocket fallback
        pass
    elif action == "safe":
        incident_id = msg.get("incident_id")
        if incident_id:
            await mark_safe(incident_id, device_id)
    elif action == "location_update":
        if device_id in monitor_state:
            monitor_state[device_id]["latitude"] = msg.get("latitude")
            monitor_state[device_id]["longitude"] = msg.get("longitude")
    elif action == "heartbeat":
        await ws_manager.send_to_device(device_id, {"action": "ack"})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _default_message(level: int) -> str:
    messages = {
        1: "Kavach alert: Trigger detected. Monitoring situation.",
        2: "🚨 Kavach ALERT: Help may be needed. Location shared.",
        3: "🆘 KAVACH EMERGENCY: Immediate assistance required!",
        4: "⚫ KAVACH CRITICAL: Auto-emergency protocol activated!",
    }
    return messages.get(level, "Kavach safety alert")


def _channels_for_level(level: int) -> list:
    channels = {
        1: ["recording"],
        2: ["closest_contact", "fake_call", "gps_tracking"],
        3: ["all_contacts", "police_112", "siren", "gps_tracking"],
        4: ["all_contacts", "police_112", "auto_call", "evidence_upload"],
    }
    return channels.get(level, ["all_contacts"])
