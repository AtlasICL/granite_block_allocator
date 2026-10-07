"""Reading the settings form and remembering it between runs."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from allocator import APP_NAME
from allocator.blockfile import parse_weight

MAX_BLOCK_LIMIT = 10
NO_LIMIT = "No limit"


class InputError(ValueError):
    """A setting the user typed is invalid. The message is meant for the user."""


# --------------------------------------------------------------------------
# Parsing the form
# --------------------------------------------------------------------------


def parse_container_count(text: str) -> int:
    s = text.strip()
    if not s:
        raise InputError("Enter the number of containers.")
    try:
        value = float(s.replace(",", "."))
    except ValueError:
        raise InputError(f"Number of containers must be a whole number (you entered '{s}').") from None
    if not value.is_integer():
        raise InputError(f"Number of containers must be a whole number (you entered '{s}').")
    if value < 1:
        raise InputError("Number of containers must be at least 1.")
    return int(value)


def parse_capacity(text: str) -> float:
    s = text.strip()
    if not s:
        raise InputError("Enter the max weight per container.")
    value = parse_weight(s)
    if value is None:
        raise InputError(f"Max weight per container must be a number (you entered '{s}').")
    if value <= 0:
        raise InputError("Max weight per container must be more than 0.")
    return value


def parse_max_blocks(text: str) -> int | None:
    s = text.strip()
    if not s or s.lower() == NO_LIMIT.lower():
        return None
    try:
        value = int(s)
    except ValueError:
        raise InputError(f"Max blocks per container must be a whole number or '{NO_LIMIT}'.") from None
    if value < 1:
        raise InputError("Max blocks per container must be at least 1.")
    return value


# --------------------------------------------------------------------------
# Remembering settings
# --------------------------------------------------------------------------


@dataclass
class Settings:
    container_count: str = "2"
    capacity: str = ""
    max_blocks: str = NO_LIMIT
    balance: bool = False
    last_file: str = ""
    last_dir: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        defaults = cls()
        values: dict[str, Any] = {}
        for f in fields(cls):
            value = data.get(f.name, getattr(defaults, f.name))
            if not isinstance(value, type(getattr(defaults, f.name))):
                value = getattr(defaults, f.name)
            values[f.name] = value
        return cls(**values)


def settings_path() -> Path:
    """Where settings live: the usual per-user config folder for each OS."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME / "settings.json"


def load_settings(path: Path | None = None) -> Settings:
    """Load saved settings, or defaults if there are none or they're unreadable."""
    path = path or settings_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Settings()
    if not isinstance(data, dict):
        return Settings()
    return Settings.from_dict(data)


def save_settings(settings: Settings, path: Path | None = None) -> bool:
    """Save settings. Returns False instead of raising if that isn't possible."""
    path = path or settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False
