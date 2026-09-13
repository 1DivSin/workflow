import os
import shutil
from pathlib import Path


def _available(name: str, root: Path) -> bool:
    if os.getenv(f"{name.upper()}_HOME"):
        return True
    if shutil.which(name):
        return True
    if (Path.home() / f".{name}").exists():
        return True
    if name == "hermes":
        return (root / ".venv").exists() or (root / "hermes_cli").exists()
    return False


def detect_host(root="."):
    r = Path(root).resolve()
    forced = os.getenv("PSI_WORKFLOW_HOST", "").lower()
    names = [forced] if forced else ["codex", "openclaw", "hermes"]
    for n in names:
        if n in ("codex", "openclaw", "hermes") and _available(n, r):
            h = Path(os.getenv(f"{n.upper()}_HOME", str(Path.home() / f".{n}")))
            workspace = Path(os.getenv(f"{n.upper()}_WORKSPACE", str(r)))
            return {
                "name": n,
                "home": str(h),
                "workspace": str(workspace),
                "state_dir": str(h / "state"),
                "tools_dir": str(h / "tools"),
                "skills_dir": str(h / "skills"),
                "available": True,
            }
    return {
        "name": "generic",
        "home": str(r / ".psi"),
        "workspace": str(r),
        "state_dir": str(r / ".psi/state"),
        "tools_dir": str(r / ".psi/tools"),
        "skills_dir": str(r / ".psi/skills"),
        "available": False,
    }
