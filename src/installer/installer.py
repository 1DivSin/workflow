import json
import os
import shutil
import sys
from pathlib import Path
from .detect import detect_host


_CODEX_BEGIN = "# BEGIN dynamic-workflow"
_CODEX_END = "# END dynamic-workflow"


def configure_codex_mcp(config: str | Path, runtime: str | Path, workspace: str | Path) -> Path:
    """Register the three workflow tools in Codex' MCP config idempotently."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    try:
        start = lines.index(_CODEX_BEGIN)
        end = lines.index(_CODEX_END, start)
        del lines[start : end + 1]
    except ValueError:
        pass
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(
        [
            _CODEX_BEGIN,
            "[mcp_servers.fusion_flow]",
            f"command = {json.dumps(sys.executable)}",
            'args = ["-m", "fusion_flow.mcp_server"]',
            "[mcp_servers.fusion_flow.env]",
            f"PYTHONPATH = {json.dumps(str(Path(runtime).resolve() / 'src'))}",
            'PSI_WORKFLOW_HOST = "codex"',
            f"PSI_WORKFLOW_WORKSPACE = {json.dumps(str(Path(workspace).resolve()))}",
            _CODEX_END,
        ]
    )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path

def install(source, host=None, destination=None):
    h = host or detect_host()
    s = Path(source).resolve()
    d = Path(destination or Path(h["tools_dir"]) / "genuineknowledge-method")
    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(s, d, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".git", "*.egg-info"))
    skill_source = d / "src" / "SKILL.md"
    if skill_source.exists():
        skill_dir = Path(h["skills_dir"]) / "workflow"
        skill_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_source, skill_dir / "SKILL.md")
    if h["name"] == "codex":
        home = Path(h.get("home", Path(h["state_dir"]).parent))
        configure_codex_mcp(Path(os.getenv("CODEX_CONFIG", str(home / "config.toml"))), d, h.get("workspace", "."))
    Path(h["state_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(h["state_dir"]) / "genuineknowledge-method.json").write_text(json.dumps({"target": str(d), "skill_dir": str(Path(h["skills_dir"]) / "workflow"), "host": h["name"]}, indent=2))
    return d
