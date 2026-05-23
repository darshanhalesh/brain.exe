"""
backend/alerts.py
──────────────────────────────────────────────────────────────────────────────
Alert dispatch: Twilio SMS, WhatsApp, 112 API, Evidence Vault.
All dispatches run concurrently via asyncio.gather().
"""

import asyncio
import os
import json
import uuid
from datetime import datetime, timezone
from loguru import logger
import httpx

from backend.state import incident_store
from backend.websocket_manager import ws_manager
from backend.optimizer import build_contacts_from_config, optimize_alert_order

# ── Config ────────────────────────────────────────────────────────────────────
TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM = os.getenv("TWILIO_FROM_NUMBER", "+15555555555")
TRUSTED_CONTACTS_RAW = os.getenv("TRUSTED_CONTACTS", "")
EMERGENCY_API_URL = os.getenv("EMERGENCY_API_URL", "https://mock-112.kavach.dev/alert")
AWS_BUCKET = os.getenv("AWS_BUCKET_NAME", "kavach-evidence")

LEVEL_EMOJI = {1: "🟢", 2: "🟡", 3: "🔴", 4: "⚫"}


async def dispatch_all_alerts(incident_id: str, payload: dict, threat_level: int):
    """Coordinate simultaneous dispatch to all channels based on threat level."""
    incident = incident_store.get(incident_id)
    if not incident:
        logger.error(f"[{incident_id}] Incident not found for dispatch")
        return

    # Build + optimize contact order
    contacts_cfg = [
        {"id": f"c{i}", "name": f"Contact {i+1}", "phone": p.strip(), "priority": 4.0 - i}
        for i, p in enumerate(TRUSTED_CONTACTS_RAW.split(",") if TRUSTED_CONTACTS_RAW else [])
        if p.strip()
    ]

    user_location = (payload.get("latitude", 0), payload.get("longitude", 0))
    contacts = build_contacts_from_config(contacts_cfg, user_location)
    ranked_contacts = optimize_alert_order(contacts, threat_level)

    tasks = []

    # Level 2+: SMS/WhatsApp to contacts
    if threat_level >= 2:
        for contact in ranked_contacts:
            tasks.append(_send_sms(contact.phone, payload, threat_level, incident_id))
            if threat_level >= 3:
                tasks.append(_send_whatsapp(contact.phone, payload, threat_level))

    # Level 3+: 112 police alert
    if threat_level >= 3:
        tasks.append(_alert_112(payload, incident_id))

    # Level 2+: Evidence vault upload
    if threat_level >= 2:
        tasks.append(_upload_evidence(incident_id, payload))

    # Level 3+: Fake call / siren via device
    if threat_level >= 3:
        tasks.append(_trigger_device_siren(incident["device_id"]))

    # Run all concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)

    alerts_sent = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"[{incident_id}] Alert task {i} failed: {result}")
        else:
            alerts_sent.append(result)

    incident["alerts_sent"] = [r for r in alerts_sent if r]
    incident["status"] = "dispatched"
    incident["dispatched_at"] = datetime.now(timezone.utc).isoformat()
    incident["updated_at"] = datetime.now(timezone.utc).isoformat()

    logger.info(f"[{incident_id}] Dispatched {len(alerts_sent)}/{len(tasks)} alerts successfully")

    await ws_manager.broadcast_dashboard({
        "event": "dispatched",
        "incident_id": incident_id,
        "alerts_sent": len(alerts_sent),
        "threat_level": threat_level,
    })

    # Send device confirmation
    await ws_manager.send_to_device(incident["device_id"], {
        "action": "speak",
        "text": "Help is coming. You are not alone." if threat_level >= 3 else "Alert sent. Stay calm.",
    })


async def _send_sms(phone: str, payload: dict, level: int, incident_id: str) -> dict | None:
    """Send SMS via Twilio REST API."""
    emoji = LEVEL_EMOJI.get(level, "🚨")
    maps_link = payload.get("maps_link", "")
    msg = (
        f"{emoji} KAVACH ALERT (Level {level})\n"
        f"Emergency signal detected.\n"
        f"Location: {maps_link}\n"
        f"Time: {payload.get('timestamp', '')[:19]}\n"
        f"Incident: {incident_id}"
    )

    if not TWILIO_SID or not TWILIO_TOKEN:
        logger.info(f"[SMS SIMULATION] → {phone}: {msg[:60]}...")
        return {"channel": "sms", "to": phone, "status": "simulated"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                auth=(TWILIO_SID, TWILIO_TOKEN),
                data={"From": TWILIO_FROM, "To": phone, "Body": msg},
                timeout=10.0,
            )
            if resp.status_code == 201:
                logger.info(f"SMS sent to {phone}")
                return {"channel": "sms", "to": phone, "status": "sent", "sid": resp.json().get("sid")}
            else:
                logger.error(f"SMS failed: {resp.status_code} {resp.text[:100]}")
                return {"channel": "sms", "to": phone, "status": "failed"}
    except Exception as e:
        logger.error(f"SMS error: {e}")
        return None


async def _send_whatsapp(phone: str, payload: dict, level: int) -> dict | None:
    """Send WhatsApp message via Twilio."""
    if not TWILIO_SID:
        logger.info(f"[WHATSAPP SIMULATION] → {phone}")
        return {"channel": "whatsapp", "to": phone, "status": "simulated"}

    try:
        maps_link = payload.get("maps_link", "")
        msg = f"🆘 *KAVACH EMERGENCY*\nLevel {level} alert activated.\nLocation: {maps_link}"
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
                auth=(TWILIO_SID, TWILIO_TOKEN),
                data={"From": f"whatsapp:{TWILIO_FROM}", "To": f"whatsapp:{phone}", "Body": msg},
                timeout=10.0,
            )
            status = "sent" if resp.status_code == 201 else "failed"
            return {"channel": "whatsapp", "to": phone, "status": status}
    except Exception as e:
        logger.error(f"WhatsApp error: {e}")
        return None


async def _alert_112(payload: dict, incident_id: str) -> dict | None:
    """Alert 112 India emergency API (mock for MVP)."""
    alert_data = {
        "incident_id": incident_id,
        "type": "women_safety",
        "latitude": payload.get("latitude"),
        "longitude": payload.get("longitude"),
        "timestamp": payload.get("timestamp"),
        "source": "kavach_device",
        "priority": "HIGH",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                EMERGENCY_API_URL,
                json=alert_data,
                headers={"X-API-Key": os.getenv("EMERGENCY_API_KEY", "mock")},
                timeout=5.0,
            )
            logger.info(f"[{incident_id}] 112 API: {resp.status_code}")
            return {"channel": "112_api", "status": "sent" if resp.status_code < 300 else "failed"}
    except Exception as e:
        logger.warning(f"112 API unavailable (mock): {e}")
        return {"channel": "112_api", "status": "simulated"}


async def _upload_evidence(incident_id: str, payload: dict) -> dict | None:
    """Upload encrypted evidence to S3 vault."""
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError

        evidence = {
            "incident_id": incident_id,
            "payload": payload,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
        }
        key = f"incidents/{incident_id}/evidence_{uuid.uuid4().hex[:8]}.json"

        s3 = boto3.client("s3", region_name=os.getenv("AWS_REGION", "ap-south-1"))
        s3.put_object(
            Bucket=AWS_BUCKET,
            Key=key,
            Body=json.dumps(evidence).encode(),
            ServerSideEncryption="aws:kms",
        )
        logger.info(f"[{incident_id}] Evidence uploaded to s3://{AWS_BUCKET}/{key}")
        return {"channel": "evidence_vault", "key": key, "status": "uploaded"}
    except ImportError:
        logger.info(f"[{incident_id}] Evidence vault: boto3 not installed (simulated)")
        return {"channel": "evidence_vault", "status": "simulated"}
    except Exception as e:
        logger.warning(f"Evidence upload failed: {e}")
        return {"channel": "evidence_vault", "status": "failed", "error": str(e)}


async def _trigger_device_siren(device_id: str) -> dict | None:
    """Tell ESP32 device to play siren / loud alarm."""
    from backend.websocket_manager import ws_manager
    await ws_manager.send_to_device(device_id, {
        "action": "siren",
        "duration_ms": 5000,
    })
    return {"channel": "device_siren", "status": "triggered"}
