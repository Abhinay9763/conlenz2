from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_FLAGS: dict[str, bool] = {
    "api_key": True,
    "private_key": True,
    "credit_card": True,
    "aadhaar": True,
    "pan": True,
    "email": True,
    "phone": True,
    "ip_address": True,
    "personal_name": True,
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "receiver_email": "",
    "scan_flags": DEFAULT_FLAGS,
    "allow_list": {
        "domains": [],
        "emails": [],
    },
    "auto_track": {
        "enabled": True,
        "debounce_seconds": 15,
        "default_scan_type": "quick",
        "repos": [],
    },
    "ocr": {
        "enabled_deep": True,
        "enabled_quick": False,
        "languages": ["en"],
        "pdf_readability_threshold": 200,
    },
    "limits": {
        "max_file_size_mb_quick": 10,
        "max_file_size_mb_deep": 25,
        "max_text_chars": 500000,
    },
    "names": {
        "personal_names": [],
    },
}


def _app_root() -> Path:
    root = Path.home() / ".conlenz_audit"
    root.mkdir(parents=True, exist_ok=True)
    return root


def app_root() -> Path:
    return _app_root()


def settings_path() -> Path:
    return _app_root() / "settings.json"


def quick_state_path() -> Path:
    return _app_root() / "quick_scan_state.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_SETTINGS))

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_SETTINGS))

    settings = json.loads(json.dumps(DEFAULT_SETTINGS))
    if isinstance(data, dict):
        for key in settings:
            if key in data:
                settings[key] = data[key]

    flags = settings.get("scan_flags", {}) if isinstance(settings.get("scan_flags", {}), dict) else {}
    merged_flags = dict(DEFAULT_FLAGS)
    for key, value in flags.items():
        if key in merged_flags:
            merged_flags[key] = bool(value)
    settings["scan_flags"] = merged_flags

    allow_list = settings.get("allow_list", {}) if isinstance(settings.get("allow_list", {}), dict) else {}
    settings["allow_list"]["domains"] = allow_list.get("domains", [])
    settings["allow_list"]["emails"] = allow_list.get("emails", [])

    auto_track = settings.get("auto_track", {}) if isinstance(settings.get("auto_track", {}), dict) else {}
    settings["auto_track"]["enabled"] = bool(auto_track.get("enabled", True))
    settings["auto_track"]["debounce_seconds"] = int(auto_track.get("debounce_seconds", 15))
    settings["auto_track"]["default_scan_type"] = str(auto_track.get("default_scan_type", "quick"))
    settings["auto_track"]["repos"] = auto_track.get("repos", [])

    return settings


def save_settings(settings: dict[str, Any]) -> None:
    path = settings_path()
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def load_quick_state() -> dict[str, float]:
    path = quick_state_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    cleaned: dict[str, float] = {}
    for key, value in data.items():
        try:
            cleaned[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return cleaned


def save_quick_state(state: dict[str, float]) -> None:
    path = quick_state_path()
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def update_quick_state(folder: Path, timestamp: float) -> None:
    state = load_quick_state()
    state[str(folder)] = float(timestamp)
    save_quick_state(state)
