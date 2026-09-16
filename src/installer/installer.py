from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Mapping

from .detect import detect_host


def _skill_source(source: Path) -> Path:
    for candidate in (source / "src" / "SKILL.md", source / "SKILL.md"):
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Workflow source is missing SKILL.md: {source}")


def _replace_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as raw:
        staged = Path(raw) / destination.name
        shutil.copytree(source, staged, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "*.egg-info"))
        if destination.is_symlink() or destination.is_file():
            destination.unlink()
        elif destination.is_dir():
            shutil.rmtree(destination)
        shutil.copytree(staged, destination)


def install(source: str | Path, host: Mapping[str, object] | None = None, destination: str | Path | None = None) -> Path:
    """Install a source tree, expose its skill, and persist paths for uninstall."""
    selected = dict(host or detect_host(source))
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"Workflow source does not exist: {source_path}")
    target = Path(destination or Path(str(selected["tools_dir"])) / "genuineknowledge-method").expanduser().resolve()
    if target == source_path or source_path in target.parents:
        raise ValueError("Installation destination must be outside the workflow source")
    skill_source = _skill_source(source_path)
    skill_relative = skill_source.relative_to(source_path)
    _replace_tree(source_path, target)
    skill_dir = Path(str(selected["skills_dir"])).expanduser() / "workflow"
    skill_dir.mkdir(parents=True, exist_ok=True)
    installed_skill = target / skill_relative
    shutil.copy2(installed_skill if installed_skill.is_file() else skill_source, skill_dir / "SKILL.md")
    state_dir = Path(str(selected["state_dir"])).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "genuineknowledge-method.json").write_text(
        json.dumps({"target": str(target), "skill_dir": str(skill_dir), "host": selected["name"]}, indent=2),
        encoding="utf-8",
    )
    if not (skill_dir / "SKILL.md").is_file():
        raise OSError("Installed skill verification failed")
    return target
