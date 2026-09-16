from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Callable, Mapping

HOSTS = ("codex", "openclaw", "hermes")


def detect_host(
    root: str | Path = ".",
    *,
    home: Path | None = None,
    environ: Mapping[str, str] | None = None,
    which: Callable[[str], str | None] = shutil.which,
) -> dict[str, object]:
    """Return the selected host paths without starting a process or using a network."""
    env = environ if environ is not None else os.environ
    root_path = Path(root).expanduser().resolve()
    home_path = (home or Path(env.get("USERPROFILE") or env.get("HOME") or Path.home())).expanduser().resolve()
    forced = env.get("PSI_WORKFLOW_HOST", "").strip().lower()
    names = (forced,) if forced else HOSTS
    for name in names:
        if name not in HOSTS:
            continue
        configured = env.get(f"{name.upper()}_EXECUTABLE") or (
            env.get("CODEX_APP_SERVER_COMMAND") if name == "codex" else None
        ) or (env.get("HERMES_ACP_COMMAND") if name == "hermes" else None)
        if not (configured or which(name) or (home_path / f".{name}").exists()):
            continue
        host_home = Path(env.get(f"{name.upper()}_HOME", str(home_path / f".{name}"))).expanduser()
        skills = {
            "codex": env.get("CODEX_SKILLS_DIR", str(home_path / ".agents" / "skills")),
            "openclaw": env.get("OPENCLAW_SKILLS_DIR", str(host_home / "skills")),
            "hermes": env.get("HERMES_SKILLS_DIR", str(host_home / "skills")),
        }[name]
        return {
            "name": name,
            "home": str(host_home),
            "workspace": str(Path(env.get("PSI_WORKFLOW_WORKSPACE", str(root_path))).expanduser()),
            "state_dir": str(Path(env.get("PSI_WORKFLOW_STATE_DIR", str(host_home / "state"))).expanduser()),
            "tools_dir": str(Path(env.get("PSI_WORKFLOW_TOOLS_DIR", str(host_home / "tools"))).expanduser()),
            "skills_dir": str(Path(skills).expanduser()),
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
