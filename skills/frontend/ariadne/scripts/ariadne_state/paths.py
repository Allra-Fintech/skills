"""Path management for Ariadne v2 state."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AriadnePaths:
    root: Path
    state_dir: Path
    config_path: Path
    catalog_path: Path
    state_path: Path
    waivers_path: Path


def state_paths(root: Path) -> AriadnePaths:
    resolved_root = root.resolve()
    state_dir = resolved_root / ".ariadne"
    return AriadnePaths(
        root=resolved_root,
        state_dir=state_dir,
        config_path=state_dir / "config.yaml",
        catalog_path=state_dir / "catalog.json",
        state_path=state_dir / "state.json",
        waivers_path=state_dir / "waivers.yaml",
    )


def ensure_state_layout(root: Path) -> AriadnePaths:
    layout = state_paths(root)
    layout.state_dir.mkdir(parents=True, exist_ok=True)
    return layout


def reset_for_v2(layout: AriadnePaths) -> None:
    legacy_names = [
        "records",
        "cache",
        "backend-summary.json",
        "api-catalog.json",
        "impact-index.json",
        "frontend-topology.json",
        "pr-ledger.json",
        "ambiguity-queue.json",
        "project-rubric.json",
        "summary.json",
    ]
    for name in legacy_names:
        path = layout.state_dir / name
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()
