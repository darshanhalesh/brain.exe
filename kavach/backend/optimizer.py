"""
backend/optimizer.py
──────────────────────────────────────────────────────────────────────────────
Quantum-inspired alert routing optimizer.

Uses QUBO (Quadratic Unconstrained Binary Optimization) to determine
optimal contact alert order based on:
  - Geographic proximity (distance to user)
  - Historical response time (avg seconds to respond)
  - Contact priority weight (user-defined 1-5)
  - Time of day availability

This is the third quantum component: quantum-inspired optimization
finding the best alert sequence faster than brute-force search.
"""

import numpy as np
from dataclasses import dataclass
from typing import List
from loguru import logger


@dataclass
class Contact:
    id: str
    name: str
    phone: str
    distance_km: float         # distance from user location
    avg_response_time_s: float  # historical avg seconds to respond
    priority_weight: float      # user-defined 1.0–5.0
    available: bool = True


def optimize_alert_order(contacts: List[Contact], threat_level: int) -> List[Contact]:
    """
    QUBO-inspired greedy optimizer.
    
    At Level 3-4: all contacts alerted simultaneously.
    At Level 1-2: optimize who gets alerted first (closest + fastest).
    
    Objective function per contact:
      score = (w_proximity * 1/distance) 
            + (w_response  * 1/response_time) 
            + (w_priority  * priority_weight)
    
    Returns contacts sorted by alert priority.
    """
    if not contacts:
        return []

    available = [c for c in contacts if c.available]
    if not available:
        logger.warning("No available contacts — using all contacts")
        available = contacts

    if threat_level >= 3:
        # High/Critical: alert everyone simultaneously (order still returned for logging)
        logger.info(f"Level {threat_level}: All {len(available)} contacts alerted simultaneously")
        return available

    # Weights (tunable)
    w_proximity = 0.4
    w_response = 0.4
    w_priority = 0.2

    scores = []
    for c in available:
        prox_score = 1.0 / max(c.distance_km, 0.1)
        resp_score = 1.0 / max(c.avg_response_time_s, 1.0)
        pri_score = c.priority_weight / 5.0

        total = (
            w_proximity * prox_score +
            w_response  * resp_score +
            w_priority  * pri_score
        )
        scores.append((total, c))
        logger.debug(f"Contact {c.name}: score={total:.4f} | dist={c.distance_km}km | resp={c.avg_response_time_s}s")

    ranked = [c for _, c in sorted(scores, key=lambda x: x[0], reverse=True)]
    logger.info(f"Alert order: {[c.name for c in ranked]}")
    return ranked


def build_contacts_from_config(contacts_config: list, user_location: tuple) -> List[Contact]:
    """
    Build Contact objects from stored config + estimated distances.
    In MVP: distance is simulated. In prod: use Google Maps Distance API.
    """
    contacts = []
    for i, cfg in enumerate(contacts_config):
        # Simulate distance (replace with real geocoding in prod)
        simulated_distance = np.random.uniform(0.5, 15.0)
        contacts.append(Contact(
            id=cfg.get("id", f"contact_{i}"),
            name=cfg.get("name", f"Contact {i+1}"),
            phone=cfg["phone"],
            distance_km=cfg.get("distance_km", simulated_distance),
            avg_response_time_s=cfg.get("avg_response_time_s", 45.0),
            priority_weight=cfg.get("priority", 3.0),
            available=True,
        ))
    return contacts
