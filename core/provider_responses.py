"""
Custom provider metadata for OpenAI Responses input mode.

Stored outside openclaw.json to avoid schema conflicts across OpenClaw versions.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any, Dict


DEFAULT_OPENCLAW_CONFIG_PATH = os.environ.get("OPENCLAW_CONFIG_PATH", "/root/.openclaw/openclaw.json")
ALLOWED_INPUT_MODES = {"auto", "array", "string"}
ALLOWED_DETECTED_MODES = {"array", "string", "both", "none", "unknown"}


def _default_provider_responses_path() -> str:
    override = str(os.environ.get("OPENCLAW_PROVIDER_RESPONSES_PATH", "") or "").strip()
    if override:
        return override
    base_dir = os.path.dirname(DEFAULT_OPENCLAW_CONFIG_PATH) or "/root/.openclaw"
    default_path = os.path.join(base_dir, "clawpanel", "provider_responses.json")
    legacy_path = os.path.join(base_dir, "easyclaw", "provider_responses.json")
    if os.path.exists(default_path):
        return default_path
    if os.path.exists(legacy_path):
        return legacy_path
    return default_path


DEFAULT_PROVIDER_RESPONSES_PATH = _default_provider_responses_path()


def _normalize_provider(provider: str) -> str:
    return str(provider or "").strip().lower()


def normalize_responses_input_mode(mode: str) -> str:
    token = str(mode or "").strip().lower()
    return token if token in ALLOWED_INPUT_MODES else "auto"


def _normalize_detected_mode(mode: str) -> str:
    token = str(mode or "").strip().lower()
    return token if token in ALLOWED_DETECTED_MODES else "unknown"


def _ensure_parent_dir(path: str):
    parent = os.path.dirname(path)
    if parent and not os.path.exists(parent):
        os.makedirs(parent, exist_ok=True)


def _default_payload() -> Dict[str, Any]:
    return {"providers": {}}


def _resolve_path(path: str = "") -> str:
    if path:
        return path
    return _default_provider_responses_path()


def _load_raw(path: str = "") -> Dict[str, Any]:
    target_path = _resolve_path(path)
    if not os.path.exists(target_path):
        return _default_payload()
    try:
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_payload()
        providers = data.get("providers", {})
        if not isinstance(providers, dict):
            data["providers"] = {}
        return data
    except Exception:
        return _default_payload()


def _save_raw(data: Dict[str, Any], path: str = "") -> bool:
    target_path = _resolve_path(path)
    try:
        _ensure_parent_dir(target_path)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(data if isinstance(data, dict) else _default_payload(), f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False


def list_provider_responses_modes(path: str = "") -> Dict[str, Dict[str, Any]]:
    raw = _load_raw(path=path)
    providers = raw.get("providers", {}) if isinstance(raw.get("providers"), dict) else {}
    out: Dict[str, Dict[str, Any]] = {}
    for provider, row in providers.items():
        pid = _normalize_provider(provider)
        if not pid or not isinstance(row, dict):
            continue
        mode = normalize_responses_input_mode(row.get("mode", "auto"))
        probe = row.get("probe", {}) if isinstance(row.get("probe"), dict) else {}
        out[pid] = {
            "mode": mode,
            "probe": {
                "detectedMode": _normalize_detected_mode(probe.get("detectedMode", "unknown")),
                "stringOk": bool(probe.get("stringOk", False)),
                "arrayOk": bool(probe.get("arrayOk", False)),
                "stringError": str(probe.get("stringError", "") or ""),
                "arrayError": str(probe.get("arrayError", "") or ""),
                "probedAt": int(probe.get("probedAt", 0) or 0),
            },
        }
    return out


def get_provider_responses_input_mode(provider: str, path: str = "") -> str:
    pid = _normalize_provider(provider)
    if not pid:
        return "auto"
    all_rows = list_provider_responses_modes(path=path)
    row = all_rows.get(pid, {})
    return normalize_responses_input_mode(row.get("mode", "auto"))


def set_provider_responses_input_mode(provider: str, mode: str, path: str = "") -> bool:
    pid = _normalize_provider(provider)
    if not pid:
        return False
    normalized_mode = normalize_responses_input_mode(mode)

    raw = _load_raw(path=path)
    providers = raw.get("providers", {}) if isinstance(raw.get("providers"), dict) else {}
    row = providers.get(pid, {}) if isinstance(providers.get(pid), dict) else {}
    row["mode"] = normalized_mode
    providers[pid] = row
    raw["providers"] = providers
    return _save_raw(raw, path=path)


def get_provider_responses_probe(provider: str, path: str = "") -> Dict[str, Any]:
    pid = _normalize_provider(provider)
    if not pid:
        return {}
    all_rows = list_provider_responses_modes(path=path)
    row = all_rows.get(pid, {})
    probe = row.get("probe", {}) if isinstance(row.get("probe"), dict) else {}
    if not probe:
        return {}
    return {
        "detectedMode": _normalize_detected_mode(probe.get("detectedMode", "unknown")),
        "stringOk": bool(probe.get("stringOk", False)),
        "arrayOk": bool(probe.get("arrayOk", False)),
        "stringError": str(probe.get("stringError", "") or ""),
        "arrayError": str(probe.get("arrayError", "") or ""),
        "probedAt": int(probe.get("probedAt", 0) or 0),
    }


def set_provider_responses_probe(
    provider: str,
    detected_mode: str,
    string_ok: bool,
    array_ok: bool,
    string_error: str = "",
    array_error: str = "",
    path: str = "",
) -> bool:
    pid = _normalize_provider(provider)
    if not pid:
        return False

    raw = _load_raw(path=path)
    providers = raw.get("providers", {}) if isinstance(raw.get("providers"), dict) else {}
    row = providers.get(pid, {}) if isinstance(providers.get(pid), dict) else {}
    row["probe"] = {
        "detectedMode": _normalize_detected_mode(detected_mode),
        "stringOk": bool(string_ok),
        "arrayOk": bool(array_ok),
        "stringError": str(string_error or ""),
        "arrayError": str(array_error or ""),
        "probedAt": int(time.time()),
    }
    providers[pid] = row
    raw["providers"] = providers
    return _save_raw(raw, path=path)
