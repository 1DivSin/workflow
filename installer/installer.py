import json
import shutil
from pathlib import Path
from .detect import detect_host

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
    Path(h["state_dir"]).mkdir(parents=True, exist_ok=True)
    (Path(h["state_dir"]) / "genuineknowledge-method.json").write_text(json.dumps({"target": str(d), "skill_dir": str(Path(h["skills_dir"]) / "workflow"), "host": h["name"]}, indent=2))
    return d
