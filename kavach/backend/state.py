"""backend/state.py — In-memory state (replace with Redis/DB in prod)"""
from typing import Dict

incident_store: Dict[str, dict] = {}
device_registry: Dict[str, dict] = {}
monitor_state: Dict[str, dict] = {}
