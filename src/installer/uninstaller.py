from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Mapping

from .detect import detect_host


def uninstall(host: Mapping[str, object] | None = None, target: str | Path | None = None, purge_state: bool = False) -> list[Path]:
    selected = dict(host or detect_host())
    state = Path(str(selected["state_dir"])).expanduser() / "genuineknowledge-method.json"
    metadata = json.loads(state.read_text(encoding="utf-8")) if state.is_file() else {}
    target_path = Path(target or metadata.get("target") or Path(str(selected["tools_dir"])) / "genuineknowledge-method").expanduser()
    removed: list[Path] = []
    if target_path.is_dir():
        shutil.rmtree(target_path)
        removed.append(target_path)
    skill_dir = Path(str(metadata.get("skill_dir", ""))).expanduser() if metadata.get("skill_dir") else None
    if skill_dir and skill_dir.is_dir():
        shutil.rmtree(skill_dir)
        removed.append(skill_dir)
    if purge_state and state.is_file():
        state.unlink()
        removed.append(state)
    return removed
