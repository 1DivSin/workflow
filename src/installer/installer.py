from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .detect import detect_host


def install(
    source,
    host=None,
    destination=None,
    *,
    register_plugin: bool = False,
    runner: Callable[..., object] = subprocess.run,
):
    h = host or detect_host()
    s = Path(source).resolve()
    d = Path(destination or Path(h["tools_dir"]) / "genuineknowledge-method")
    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "*.egg-info"))

    skill_dir = Path(h["skills_dir"]) / "workflow"
    skill_source = d / "src" / "SKILL.md"
    if skill_source.is_file():
        skill_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_source, skill_dir / "SKILL.md")

    plugin_dir = d / "plugins" / "openclaw-workflow"
    registered = False
    if register_plugin:
        if h.get("name") != "openclaw":
            raise ValueError("--register-plugin is only supported for OpenClaw")
        if not (plugin_dir / "openclaw.plugin.json").is_file():
            raise FileNotFoundError(f"OpenClaw plugin manifest is missing: {plugin_dir}")
        executable = h.get("executable") or shutil.which("openclaw")
        if not executable:
            raise FileNotFoundError("OpenClaw executable is required to register the plugin")
        command: Sequence[str] = (
            str(executable),
            "plugins",
            "install",
            "--link",
            str(plugin_dir),
            "--force",
        )
        runner(command, check=True)
        registered = True

    state_dir = Path(h["state_dir"])
    state_dir.mkdir(parents=True, exist_ok=True)
    state = {
        "target": str(d),
        "skill_dir": str(skill_dir),
        "host": h["name"],
    }
    if plugin_dir.is_dir():
        state["plugin_dir"] = str(plugin_dir)
        state["plugin_registered"] = registered
    (state_dir / "genuineknowledge-method.json").write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )
    return d