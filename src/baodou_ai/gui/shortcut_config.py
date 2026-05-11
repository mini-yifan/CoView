"""Shortcut configuration helpers for the floating overlay."""

from __future__ import annotations

import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple


SHORTCUT_ACTION_ACTIVATE = "activate"
SHORTCUT_ACTION_HIDE = "hide"
SHORTCUT_ACTIONS = (SHORTCUT_ACTION_ACTIVATE, SHORTCUT_ACTION_HIDE)

SHORTCUT_DEFAULTS: Dict[str, Dict[str, List[str]]] = {
    "windows": {
        SHORTCUT_ACTION_ACTIVATE: ["ctrl", "alt", "i"],
        SHORTCUT_ACTION_HIDE: ["ctrl", "alt", "o"],
    },
    "macos": {
        SHORTCUT_ACTION_ACTIVATE: ["control", "option", "i"],
        SHORTCUT_ACTION_HIDE: ["control", "option", "o"],
    },
}

_MODIFIER_ALIASES = {
    "cmd": "command",
    "command": "command",
    "meta": "command",
    "win": "win",
    "windows": "win",
    "ctrl": "ctrl",
    "control": "control",
    "alt": "alt",
    "option": "option",
    "shift": "shift",
}

_WINDOWS_MODIFIERS = {"ctrl", "alt", "shift", "win"}
_MACOS_MODIFIERS = {"control", "option", "shift", "command"}
_DISALLOWED_KEYS = {"enter", "return", "tab"}

_DISPLAY_NAMES = {
    "ctrl": "Ctrl",
    "control": "Control",
    "alt": "Alt",
    "option": "Option",
    "shift": "Shift",
    "win": "Win",
    "command": "Command",
    "space": "Space",
    "escape": "Esc",
    "backspace": "Backspace",
    "delete": "Delete",
}

_MACOS_KEY_CODES = {
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "6": 22,
    "5": 23,
    "9": 25,
    "7": 26,
    "8": 28,
    "0": 29,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,
    "space": 49,
    "escape": 53,
    "delete": 51,
}


def current_shortcut_platform() -> str:
    return "macos" if sys.platform == "darwin" else "windows"


def platform_shortcut_defaults(platform_name: Optional[str] = None) -> Dict[str, List[str]]:
    platform_key = platform_name or current_shortcut_platform()
    source = SHORTCUT_DEFAULTS.get(platform_key, SHORTCUT_DEFAULTS["windows"])
    return {
        action: list(keys)
        for action, keys in source.items()
    }


def normalize_shortcut_keys(keys: Any, platform_name: Optional[str] = None) -> List[str]:
    platform_key = platform_name or current_shortcut_platform()
    allowed_modifiers = _MACOS_MODIFIERS if platform_key == "macos" else _WINDOWS_MODIFIERS
    normalized: List[str] = []
    for key in _coerce_key_list(keys):
        token = str(key or "").strip().lower().replace("+", "")
        token = _MODIFIER_ALIASES.get(token, token)
        if platform_key == "windows" and token == "control":
            token = "ctrl"
        if platform_key == "macos" and token == "alt":
            token = "option"
        if token == "return":
            token = "enter"
        if not token:
            continue
        if token in normalized:
            continue
        normalized.append(token)

    modifiers = [key for key in normalized if key in allowed_modifiers]
    main_keys = [key for key in normalized if key not in allowed_modifiers]
    if len(main_keys) != 1:
        return []
    return modifiers + [main_keys[0]]


def shortcut_is_valid(keys: Any, platform_name: Optional[str] = None) -> bool:
    normalized = normalize_shortcut_keys(keys, platform_name)
    if not normalized:
        return False
    if any(key in _DISALLOWED_KEYS for key in normalized):
        return False
    platform_key = platform_name or current_shortcut_platform()
    allowed_modifiers = _MACOS_MODIFIERS if platform_key == "macos" else _WINDOWS_MODIFIERS
    return any(key in allowed_modifiers for key in normalized)


def display_shortcut(keys: Any, platform_name: Optional[str] = None) -> str:
    normalized = normalize_shortcut_keys(keys, platform_name)
    if not normalized:
        return ""
    return "+".join(
        _DISPLAY_NAMES.get(key, key.upper() if len(key) == 1 else key.title())
        for key in normalized
    )


def get_configured_shortcut(
    config: Any,
    action: str,
    platform_name: Optional[str] = None,
) -> List[str]:
    platform_key = platform_name or current_shortcut_platform()
    defaults = platform_shortcut_defaults(platform_key)
    default_keys = defaults.get(action, [])
    raw = None
    if config is not None:
        getter = getattr(config, "get", None)
        if callable(getter):
            raw = getter(f"shortcut_config.{platform_key}.{action}", None)
    normalized = normalize_shortcut_keys(raw, platform_key)
    if shortcut_is_valid(normalized, platform_key):
        return normalized
    return list(default_keys)


def shortcut_contains_disallowed_key(keys: Iterable[str]) -> bool:
    return any(str(key or "").strip().lower() in _DISALLOWED_KEYS for key in keys)


def macos_shortcut_matches_event(keys: Any, event) -> bool:
    normalized = normalize_shortcut_keys(keys, "macos")
    if not normalized:
        return False
    main_key = normalized[-1]
    expected_key_code = _MACOS_KEY_CODES.get(main_key)
    if expected_key_code is None:
        return False
    try:
        modifier_flags = int(event.modifierFlags())
        key_code = int(event.keyCode())
    except Exception:
        return False
    required = {
        "shift": 1 << 17,
        "control": 1 << 18,
        "option": 1 << 19,
        "command": 1 << 20,
    }
    if key_code != expected_key_code:
        return False
    return all(
        bool(modifier_flags & flag) == (modifier in normalized)
        for modifier, flag in required.items()
    )


def windows_shortcut_to_native(keys: Any) -> Optional[Tuple[int, int]]:
    normalized = normalize_shortcut_keys(keys, "windows")
    if not normalized:
        return None
    modifiers = 0
    for key in normalized[:-1]:
        if key == "alt":
            modifiers |= 0x0001
        elif key == "ctrl":
            modifiers |= 0x0002
        elif key == "shift":
            modifiers |= 0x0004
        elif key == "win":
            modifiers |= 0x0008
    virtual_key = _windows_virtual_key(normalized[-1])
    if virtual_key is None:
        return None
    return modifiers, virtual_key


def _windows_virtual_key(key: str) -> Optional[int]:
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and key.isdigit():
        return ord(key)
    if key.startswith("f") and key[1:].isdigit():
        index = int(key[1:])
        if 1 <= index <= 24:
            return 0x70 + index - 1
    special = {
        "space": 0x20,
        "escape": 0x1B,
        "backspace": 0x08,
        "delete": 0x2E,
    }
    return special.get(key)


def _coerce_key_list(keys: Any) -> List[str]:
    if isinstance(keys, str):
        return [part.strip() for part in keys.replace("-", "+").split("+")]
    if isinstance(keys, (list, tuple)):
        return [str(key) for key in keys]
    return []
