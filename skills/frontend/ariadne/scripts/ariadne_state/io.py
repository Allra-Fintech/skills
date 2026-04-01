"""Filesystem and serialization helpers for Ariadne state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def yaml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def yaml_list(values: list[str], indent: int = 0) -> str:
    prefix = " " * indent
    if not values:
        return f"{prefix}[]"
    return "\n".join(f"{prefix}- {yaml_quote(value)}" for value in values)


def yaml_keyed_list(name: str, values: list[str]) -> str:
    if not values:
        return f"{name}: []"
    return f"{name}:\n{yaml_list(values, indent=2)}"


def yaml_keyed_rule_list(name: str, values: list[dict[str, str]]) -> str:
    if not values:
        return f"{name}: []"
    lines = [f"{name}:"]
    for item in values:
        lines.append(f'  - match: {yaml_quote(item.get("match", ""))}')
        lines.append(f'    replace: {yaml_quote(item.get("replace", ""))}')
    return "\n".join(lines)


def yaml_keyed_mapping_list(name: str, values: list[dict[str, Any]]) -> str:
    if not values:
        return f"{name}: []"
    lines = [f"{name}:"]
    for item in values:
        if not item:
            lines.append("  - {}")
            continue
        first = True
        for key, value in item.items():
            if isinstance(value, bool):
                rendered = "true" if value else "false"
            elif value is None:
                rendered = "null"
            elif isinstance(value, int | float):
                rendered = str(value)
            else:
                rendered = yaml_quote(str(value))
            prefix = "  - " if first else "    "
            lines.append(f"{prefix}{key}: {rendered}")
            first = False
    return "\n".join(lines)


def write_text_if_allowed(path: Path, content: str, force: bool) -> bool:
    if path.exists() and not force:
        return False
    atomic_write_text(path, content)
    return True


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        handle.write(content)
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def atomic_write_json(path: Path, payload: Any) -> None:
    atomic_write_text(path, json.dumps(payload, ensure_ascii=True, indent=2) + "\n")


def read_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def read_json_payload(raw: str) -> Any:
    return json.loads(raw)


def load_json_or_default(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return deepcopy(default)
    payload = read_json_file(path)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return payload


def print_json(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=True, indent=2))


def parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in ("[]", ""):
        return []
    if value == "{}":
        return {}
    if value == "null":
        return None
    if value in ("true", "false"):
        return value == "true"
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1].replace('\\"', '"').replace("\\\\", "\\")
    if value.isdigit():
        return int(value)
    if re.match(r"^-?[0-9]+\.[0-9]+$", value):
        return float(value)
    return value


def load_simple_yaml(path: Path) -> dict[str, Any]:
    output: dict[str, Any] = {}
    current_key: str | None = None
    current_item: dict[str, Any] | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        if not line.startswith(" "):
            current_item = None
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            if value:
                output[key] = parse_scalar(value)
                current_key = None
            else:
                output[key] = []
                current_key = key
            continue

        if current_key is None:
            continue

        stripped = line.strip()
        if stripped.startswith("- "):
            remainder = stripped[2:].strip()
            if ":" in remainder:
                item_key, _, item_value = remainder.partition(":")
                current_item = {item_key.strip(): parse_scalar(item_value.strip())}
                output[current_key].append(current_item)
            else:
                output[current_key].append(parse_scalar(remainder))
                current_item = None
            continue

        if current_item is not None and ":" in stripped:
            item_key, _, item_value = stripped.partition(":")
            current_item[item_key.strip()] = parse_scalar(item_value.strip())

    return output
