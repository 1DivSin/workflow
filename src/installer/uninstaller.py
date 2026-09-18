from __future__ import annotations

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Callable

from .detect import detect_host
from .installer import (
    _CODEX_BEGIN,
    _CODEX_END,
    _CODEX_INLINE_MANAGED,
    _HERMES_BEGIN,
    _HERMES_END,
    _openclaw_cli_command,
    _toml_inline_value,
)


def _remove_marked_block(path: Path, begin: str, end: str) -> None:
    if not path.exists():
        return
    lines = path.read_text(encoding="utf-8").splitlines()
    if begin not in lines and end not in lines:
        return
    if lines.count(begin) != 1 or lines.count(end) != 1:
        raise ValueError(f"Incomplete or duplicate managed block in {path}")
    start, finish = lines.index(begin), lines.index(end)
    if finish < start:
        raise ValueError(f"Managed block is out of order in {path}")
    path.write_text("\n".join(lines[:start] + lines[finish + 1:]).rstrip() + "\n", encoding="utf-8")


def _remove_codex_config(path: Path) -> None:
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    if _CODEX_BEGIN in text or _CODEX_END in text:
        _remove_marked_block(path, _CODEX_BEGIN, _CODEX_END)
        return
    lines = text.splitlines()
    inline = next((i for i, line in enumerate(lines) if _CODEX_INLINE_MANAGED in line), None)
    if inline is None:
        return
    parsed = tomllib.loads(text)
    servers = parsed.get("mcp_servers", {})
    if not isinstance(servers, dict) or "fusion_flow" not in servers:
        return
    remaining = dict(servers)
    remaining.pop("fusion_flow", None)
    if remaining:
        lines[inline] = f"mcp_servers = {_toml_inline_value(remaining)}"
    else:
        del lines[inline]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _remove_hermes_config(path: Path) -> None:
    _remove_marked_block(path, _HERMES_BEGIN, _HERMES_END)


def _safe_managed_path(path: Path, leaf: str) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.name != leaf or resolved == Path(resolved.anchor):
        raise ValueError(f"Refusing to remove unexpected managed path: {path}")
    return resolved


def uninstall(
    host=None,
    target=None,
    purge_state=False,
    *,
    runner: Callable[..., object] = subprocess.run,
):
    h = host or detect_host()
    state_path = Path(h["state_dir"]) / "genuineknowledge-method.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    target_path = _safe_managed_path(Path(target or state.get("target") or Path(h["tools_dir"]) / "genuineknowledge-method"), "genuineknowledge-method")
    skill_path = _safe_managed_path(Path(state.get("skill_dir") or Path(h["skills_dir"]) / "workflow"), "workflow")
    removed = []

    if state.get("plugin_registered") and h.get("name") == "openclaw":
        executable = h.get("executable") or os.getenv("OPENCLAW_EXECUTABLE") or shutil.which("openclaw")
        if not executable:
            raise FileNotFoundError(
                "OpenClaw executable is required to unregister genuineknowledge-workflow"
            )
        runner(
            _openclaw_cli_command(executable, "plugins", "uninstall", "genuineknowledge-workflow", "--force"),
            check=True,
        )

    if h.get("name") == "codex":
        home = Path(h.get("home", Path(h["state_dir"]).parent))
        _remove_codex_config(Path(os.getenv("CODEX_CONFIG", str(home / "config.toml"))))
    elif h.get("name") == "hermes":
        _remove_hermes_config(Path(h["home"]) / "config.yaml")

    if skill_path.exists():
        shutil.rmtree(skill_path)
        removed.append(skill_path)
    if target_path.exists():
        shutil.rmtree(target_path)
        removed.append(target_path)
    if purge_state and state_path.exists():
        state_path.unlink()
        removed.append(state_path)
    return removed
