from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Mapping


HOSTS = ("codex", "openclaw", "hermes")


def _available(
    name: str,
    *,
    home: Path,
    environ: Mapping[str, str],
    which: Callable[[str], str | None],
) -> bool:
    if environ.get(f"{name.upper()}_EXECUTABLE"):
        return True
    if name == "codex" and environ.get("CODEX_APP_SERVER_COMMAND"):
        return True
    if name == "hermes" and environ.get("HERMES_ACP_COMMAND"):
        return True
    host_home = Path(environ.get(f"{name.upper()}_HOME", str(home / f".{name}"))).expanduser()
    return bool(which(name) or host_home.exists())


def detect_host(
    root: str | Path = ".",
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
):
    env = os.environ if environ is None else environ
    root_path = Path(root).resolve()
    home_path = (home or Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())).expanduser()
    forced = env.get("PSI_WORKFLOW_HOST", "").strip().lower()
    names = (forced,) if forced else HOSTS
    for name in names:
        if name not in HOSTS or not _available(name, home=home_path, environ=env, which=which):
            continue
        host_home = Path(env.get(f"{name.upper()}_HOME", str(home_path / f".{name}")))
        workspace = Path(env.get(f"{name.upper()}_WORKSPACE", str(root_path)))
        if name == "codex":
            skills_dir = Path(env.get("CODEX_SKILLS_DIR", str(home_path / ".agents" / "skills")))
        elif name == "openclaw":
            skills_dir = Path(env.get("OPENCLAW_SKILLS_DIR", str(host_home / "skills")))
        else:
            skills_dir = Path(env.get("HERMES_SKILLS_DIR", str(host_home / "skills")))
        return {
            "name": name,
            "executable": env.get(f"{name.upper()}_EXECUTABLE") or which(name),
            "home": str(host_home),
            "workspace": str(workspace),
            "state_dir": str(Path(env.get("PSI_WORKFLOW_STATE_DIR", str(host_home / "state")))),
            "tools_dir": str(Path(env.get("PSI_WORKFLOW_TOOLS_DIR", str(host_home / "tools")))),
            "skills_dir": str(skills_dir),
            "available": True,
        }
    return {
        "name": "generic",
        "home": str(root_path / ".psi"),
        "workspace": str(root_path),
        "state_dir": str(root_path / ".psi" / "state"),
        "tools_dir": str(root_path / ".psi" / "tools"),
        "skills_dir": str(root_path / ".psi" / "skills"),
        "available": False,
    }
