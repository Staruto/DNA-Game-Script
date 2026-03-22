from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from dna.config import ROOT_DIR

ROUTE_STATS_FILE = ROOT_DIR / "defence_route_stats.json"


def load_route_stats(path: Path = ROUTE_STATS_FILE) -> Dict[str, Dict[str, int]]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(payload, dict):
        return {}
    stats = payload.get("routes", payload)
    if not isinstance(stats, dict):
        return {}

    normalized: Dict[str, Dict[str, int]] = {}
    for route_name, raw in stats.items():
        if not isinstance(route_name, str) or not isinstance(raw, dict):
            continue
        attempts = int(raw.get("attempts", 0) or 0)
        successes = int(raw.get("successes", 0) or 0)
        if attempts < 0:
            attempts = 0
        if successes < 0:
            successes = 0
        if successes > attempts:
            successes = attempts
        normalized[route_name] = {"attempts": attempts, "successes": successes}
    return normalized


def save_route_stats(stats: Dict[str, Dict[str, int]], path: Path = ROUTE_STATS_FILE) -> Path:
    payload: Dict[str, Any] = {"version": 1, "routes": stats}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def record_attempt(stats: Dict[str, Dict[str, int]], route_name: str):
    if not route_name:
        return
    entry = stats.setdefault(route_name, {"attempts": 0, "successes": 0})
    entry["attempts"] = int(entry.get("attempts", 0) or 0) + 1
    entry["successes"] = min(int(entry.get("successes", 0) or 0), entry["attempts"])


def record_success(stats: Dict[str, Dict[str, int]], route_name: str):
    if not route_name:
        return
    entry = stats.setdefault(route_name, {"attempts": 0, "successes": 0})
    attempts = int(entry.get("attempts", 0) or 0)
    successes = int(entry.get("successes", 0) or 0) + 1
    if attempts <= 0:
        attempts = 1
    if successes > attempts:
        successes = attempts
    entry["attempts"] = attempts
    entry["successes"] = successes


def get_rate(stats: Dict[str, Dict[str, int]], route_name: str) -> tuple[int, int, float]:
    entry = stats.get(route_name, {})
    attempts = int(entry.get("attempts", 0) or 0)
    successes = int(entry.get("successes", 0) or 0)
    if attempts <= 0:
        return 0, 0, 0.0
    rate = successes / attempts * 100.0
    return attempts, successes, rate
