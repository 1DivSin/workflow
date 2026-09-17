from __future__ import annotations

import json
import os
import re
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .detect import detect_host


_CODEX_BEGIN = "# BEGIN dynamic-workflow"
_CODEX_END = "# END dynamic-workflow"

_HERMES_BEGIN = "  # BEGIN dynamic-workflow"
_HERMES_END = "  # END dynamic-workflow"


def configure_codex_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
    """Register the workflow MCP server in Codex config idempotently."""
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


def _has_hermes_server(lines: list[str]) -> bool:
    try:
        start = next(
            i
            for i, line in enumerate(lines)
            if re.fullmatch(r"mcp_servers:\s*", line)
        )
    except StopIteration:
        return False

    return any(
        re.fullmatch(r"  fusion_flow:\s*", line)
        for line in lines[start + 1 :]
    )


def configure_hermes_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
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


def _openclaw_plugin_command(executable: str | Path, plugin_dir: Path) -> tuple[str, ...]:
    command = (
        str(executable),
        "plugins",
        "install",
        "--link",
        str(plugin_dir),
        "--force",
    )
    if sys.platform == "win32" and str(executable).lower().endswith((".cmd", ".bat")):
        comspec = os.environ.get("COMSPEC", "cmd.exe")
        return (comspec, "/d", "/s", "/c", subprocess.list2cmdline(command))
    return command


def install(
    source,
    host=None,
    destination=None,
    *,
    target_host: str | None = None,
    register_plugin: bool = False,
    runner: Callable[..., object] = subprocess.run,
):
    if register_plugin:
        if target_host not in (None, "openclaw"):
            raise ValueError("--register-plugin requires the OpenClaw host")
        if host is not None and host.get("name") != "openclaw":
            raise ValueError("--register-plugin is only supported for OpenClaw")
        target_host = "openclaw"

    h = host or detect_host(target=target_host)
    if target_host is not None and h.get("name") != target_host:
        raise RuntimeError(f"Requested host {target_host!r} is not available")

    s = Path(source).resolve()

    plugin_executable: str | Path | None = None
    if register_plugin:
        if h.get("name") != "openclaw":
            raise ValueError("--register-plugin is only supported for OpenClaw")
        plugin_source = s / "plugins" / "openclaw-workflow"
        if not (plugin_source / "openclaw.plugin.json").is_file():
            raise FileNotFoundError(
                f"OpenClaw plugin manifest is missing: {plugin_source}"
            )
        plugin_executable = (
            h.get("executable")
            or os.getenv("OPENCLAW_EXECUTABLE")
            or shutil.which("openclaw")
        )
        if not plugin_executable:
            raise FileNotFoundError(
                "OpenClaw executable is required to register the plugin"
            )

    d = Path(destination or Path(h["tools_dir"]) / "genuineknowledge-method")

    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        shutil.rmtree(d)

    shutil.copytree(
        s,
        d,
        ignore=shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".git",
            "*.egg-info",
        ),
    )

    skill_dir = Path(h["skills_dir"]) / "workflow"
    skill_source = d / "src" / "SKILL.md"
    if skill_source.is_file():
        skill_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(skill_source, skill_dir / "SKILL.md")

    if h["name"] == "codex":
        home = Path(h.get("home", Path(h["state_dir"]).parent))
        configure_codex_mcp(
            Path(os.getenv("CODEX_CONFIG", str(home / "config.toml"))),
            d,
            h.get("workspace", "."),
        )

    if h["name"] == "hermes":
        configure_hermes_mcp(
            Path(h["home"]) / "config.yaml",
            d,
            h["workspace"],
        )
        Path(h["state_dir"]).mkdir(parents=True, exist_ok=True)
        (
            Path(h["state_dir"]) / "genuineknowledge-method.json"
        ).write_text(
            json.dumps(
                {
                    "target": str(d),
                    "skill_dir": str(Path(h["skills_dir"]) / "workflow"),
                    "host": h["name"],
                },
                indent=2,
            )
        )
        return d

    plugin_dir = d / "plugins" / "openclaw-workflow"
    registered = False

    if register_plugin:
        assert plugin_executable is not None
        command: Sequence[str] = _openclaw_plugin_command(plugin_executable, plugin_dir)
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
