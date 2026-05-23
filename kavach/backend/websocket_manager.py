"""backend/websocket_manager.py"""
import json
from typing import Dict, List
from fastapi import WebSocket
from loguru import logger


class WebSocketManager:
    def __init__(self):
        self.dashboard_connections: List[WebSocket] = []
        self.device_connections: Dict[str, WebSocket] = {}

    async def connect_dashboard(self, ws: WebSocket):
        await ws.accept()
        self.dashboard_connections.append(ws)
        logger.info(f"Dashboard connected | total: {len(self.dashboard_connections)}")

    def disconnect_dashboard(self, ws: WebSocket):
        if ws in self.dashboard_connections:
            self.dashboard_connections.remove(ws)

    async def connect_device(self, ws: WebSocket, device_id: str):
        await ws.accept()
        self.device_connections[device_id] = ws

    def disconnect_device(self, device_id: str):
        self.device_connections.pop(device_id, None)

    async def broadcast_dashboard(self, data: dict):
        dead = []
        for ws in self.dashboard_connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect_dashboard(ws)

    async def send_to_device(self, device_id: str, data: dict):
        ws = self.device_connections.get(device_id)
        if ws:
            try:
                await ws.send_json(data)
                logger.debug(f"Sent to device {device_id}: {data.get('action')}")
            except Exception as e:
                logger.warning(f"Failed to send to device {device_id}: {e}")
        else:
            logger.debug(f"Device {device_id} not connected via WS (REST fallback)")


ws_manager = WebSocketManager()
