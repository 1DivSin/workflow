import json
import re
import sys
import shutil
from pathlib import Path
from .detect import detect_host


_HERMES_BEGIN = "  # BEGIN dynamic-workflow"
_HERMES_END = "  # END dynamic-workflow"


def _has_hermes_server(lines: list[str]) -> bool:
    try:
        start = next(i for i, line in enumerate(lines) if re.fullmatch(r"mcp_servers:\s*", line))
    except StopIteration:
        return False
    return any(re.fullmatch(r"  fusion_flow:\s*", line) for line in lines[start + 1 :])


def configure_hermes_mcp(config: str | Path, runtime: str | Path, workspace: str | Path) -> Path:
    """Add the workflow MCP server without overwriting user configuration."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    try:
        start = lines.index(_HERMES_BEGIN)
        end = lines.index(_HERMES_END, start)
        del lines[start : end + 1]
    except ValueError:
        if _has_hermes_server(lines):
            return path
    if not any(re.fullmatch(r"mcp_servers:\s*", line) for line in lines):
        lines.append("mcp_servers:")
    if lines and lines[-1].strip():
        lines.append("")
    lines.extend(
        [
            _HERMES_BEGIN,
            "  fusion_flow:",
            f"    command: {json.dumps(sys.executable)}",
            '    args: ["-m", "fusion_flow.mcp_server"]',
            "    env:",
            f"      PYTHONPATH: {json.dumps(str(Path(runtime).resolve() / 'src'))}",
            '      PSI_WORKFLOW_HOST: "hermes"',
            f"      PSI_WORKFLOW_WORKSPACE: {json.dumps(str(Path(workspace).resolve()))}",
            _HERMES_END,
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
    if h["name"] == "hermes":
        configure_hermes_mcp(Path(h["home"]) / "config.yaml", d, h["workspace"])
    Path(h["state_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(h["state_dir"]) / "genuineknowledge-method.json").write_text(json.dumps({"target": str(d), "skill_dir": str(Path(h["skills_dir"]) / "workflow"), "host": h["name"]}, indent=2))
    return d
