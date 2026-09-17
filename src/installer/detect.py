from __future__ import annotations

import os
import shlex
import shutil
from pathlib import Path
from typing import Callable, Mapping


HOSTS = ("codex", "openclaw", "hermes")
_COMMAND_OVERRIDES = {
    "codex": "CODEX_APP_SERVER_COMMAND",
    "openclaw": "OPENCLAW_COMMAND",
    "hermes": "HERMES_ACP_COMMAND",
}


def _split_command(value: str) -> tuple[str, ...]:
    if os.name == "nt":
        lexer = shlex.shlex(value, posix=True)
        lexer.whitespace_split = True
        lexer.escape = ""
        return tuple(lexer)
    return tuple(shlex.split(value))


def _available(
    name: str,
    *,
    home: Path,
    environ: Mapping[str, str],
    which: Callable[[str], str | None],
) -> bool:
    if environ.get(f"{name.upper()}_EXECUTABLE"):
        return True
    if environ.get(_COMMAND_OVERRIDES[name]):
        return True
    return bool(which(name) or (home / f".{name}").exists())


def detect_host(
    root: str | Path = ".",
    *,
    target: str | None = None,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
):
    env = environ or os.environ
    root_path = Path(root).resolve()
    home_path = (
        home or Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())
    ).expanduser()
    forced = (target or env.get("PSI_WORKFLOW_HOST", "")).strip().lower()
    if forced and forced not in HOSTS:
        raise ValueError(f"Unsupported host: {forced}")
    names = (forced,) if forced else HOSTS
    for name in names:
        if not _available(name, home=home_path, environ=env, which=which):
            continue
        host_home = Path(env.get(f"{name.upper()}_HOME", str(home_path / f".{name}")))
        workspace = Path(env.get(f"{name.upper()}_WORKSPACE", str(root_path)))
        if name == "codex":
            skills_dir = Path(env.get("CODEX_SKILLS_DIR", str(home_path / ".agents" / "skills")))
        elif name == "openclaw":
            skills_dir = Path(env.get("OPENCLAW_SKILLS_DIR", str(host_home / "skills")))
        else:
            skills_dir = Path(env.get("HERMES_SKILLS_DIR", str(host_home / "skills")))

        executable = env.get(f"{name.upper()}_EXECUTABLE", "").strip() or None
        command_override = env.get(_COMMAND_OVERRIDES[name], "").strip()
        if executable is None and command_override:
            command = _split_command(command_override)
            executable = command[0] if command else None
        if executable is None:
            executable = which(name)

        return {
            "name": name,
            "home": str(host_home),
            "workspace": str(workspace),
            "state_dir": str(Path(env.get("PSI_WORKFLOW_STATE_DIR", str(host_home / "state")))),
            "tools_dir": str(Path(env.get("PSI_WORKFLOW_TOOLS_DIR", str(host_home / "tools")))),
            "skills_dir": str(skills_dir),
            "executable": executable,
            "available": True,
        }
    return {
        "name": "generic",
        "home": str(root_path / ".psi"),
        "workspace": str(root_path),
        "state_dir": str(root_path / ".psi" / "state"),
        "tools_dir": str(root_path / ".psi" / "tools"),
        "skills_dir": str(root_path / ".psi" / "skills"),
        "executable": None,
        "available": False,
    }
