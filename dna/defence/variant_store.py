from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping

from dna.config import ROOT_DIR

DEFAULT_VARIANTS_FILE = ROOT_DIR / "defence_variants.json"


def _normalize_variant_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    safe = "".join(ch if (ch.isalnum() or ch in ("_", "-")) else "_" for ch in text)
    return safe.strip("_")


def _normalize_variant_payload(key: str, raw: Mapping[str, Any]) -> Dict[str, str]:
    display_name = str(raw.get("display_name") or key).strip() or key
    entry_template = str(raw.get("entry_template") or "").strip()
    route_name = str(raw.get("route_name") or key).strip() or key
    return {
        "display_name": display_name,
        "entry_template": entry_template,
        "route_name": route_name,
    }


def normalize_variants(raw: Mapping[str, Any]) -> Dict[str, Dict[str, str]]:
    normalized: Dict[str, Dict[str, str]] = {}
    if not isinstance(raw, Mapping):
        return normalized
    for key, value in raw.items():
        norm_key = _normalize_variant_key(key)
        if not norm_key or not isinstance(value, Mapping):
            continue
        payload = _normalize_variant_payload(norm_key, value)
        if not payload["entry_template"]:
            continue
        normalized[norm_key] = payload
    return normalized


def _read_json_payload(path: Path) -> Mapping[str, Any]:
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[WARN] Failed to read {path.name}: {exc}")
        return {}
    if isinstance(loaded, Mapping):
        return loaded
    return {}


def load_variants(base_config: Mapping[str, Any], file_path: Path = DEFAULT_VARIANTS_FILE) -> Dict[str, Dict[str, str]]:
    if file_path.exists():
        payload = _read_json_payload(file_path)
        variants = payload.get("variants", payload)
        normalized = normalize_variants(variants if isinstance(variants, Mapping) else {})
        if normalized:
            return normalized

    fallback = normalize_variants(base_config.get("defence_variants", {}))
    return fallback


def save_variants(variants: Mapping[str, Any], file_path: Path = DEFAULT_VARIANTS_FILE) -> Path:
    normalized = normalize_variants(variants)
    payload = {
        "version": 1,
        "variants": normalized,
    }
    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return file_path
