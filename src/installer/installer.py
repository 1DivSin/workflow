from __future__ import annotations

import json
import os
import re
import sys
import shutil
import subprocess
import tomllib
from pathlib import Path
from typing import Callable, Sequence

from .detect import detect_host


_CODEX_BEGIN = "# BEGIN dynamic-workflow"
_CODEX_END = "# END dynamic-workflow"

_HERMES_BEGIN = "  # BEGIN dynamic-workflow"
_HERMES_END = "  # END dynamic-workflow"


def _scan_toml_container(text: str, start: int, opener: str, closer: str) -> int:
    """Return the matching closer while ignoring braces inside TOML strings."""
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if quote is not None:
            if quote == '"' and escaped:
                escaped = False
                continue
            if quote == '"' and char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unterminated inline TOML table")


def _split_inline_toml_entries(body: str) -> list[str]:
    """Split one TOML inline table at top-level commas without rewriting values."""
    entries: list[str] = []
    start = 0
    braces = brackets = 0
    quote: str | None = None
    escaped = False
    for index, char in enumerate(body):
        if quote is not None:
            if quote == '"' and escaped:
                escaped = False
                continue
            if quote == '"' and char == "\\":
                escaped = True
                continue
            if char == quote:
                quote = None
            continue
        if char in {'"', "'"}:
            quote = char
        elif char == "{":
            braces += 1
        elif char == "}":
            braces -= 1
        elif char == "[":
            brackets += 1
        elif char == "]":
            brackets -= 1
        elif char == "," and braces == 0 and brackets == 0:
            entry = body[start:index].strip()
            if entry:
                entries.append(entry)
            start = index + 1
    entry = body[start:].strip()
    if entry:
        entries.append(entry)
    return entries


def _expand_inline_mcp_servers(lines: list[str]) -> tuple[list[str], int] | None:
    """Expand root ``mcp_servers = {...}`` into equivalent dotted assignments."""
    pattern = re.compile(r'^(?P<indent>\s*)(?:mcp_servers|"mcp_servers")\s*=\s*\{')
    for index, line in enumerate(lines):
        match = pattern.match(line)
        if match is None:
            continue
        if match.group("indent"):
            raise ValueError("mcp_servers must be a root TOML key")
        open_index = line.find("{", match.start())
        close_index = _scan_toml_container(line, open_index, "{", "}")
        trailing = line[close_index + 1 :].strip()
        if trailing and not trailing.startswith("#"):
            raise ValueError("Unsupported content after inline mcp_servers table")
        body = line[open_index + 1 : close_index]
        replacement: list[str] = []
        if trailing:
            replacement.append(trailing)
        replacement.extend(
            f"mcp_servers.{entry}" for entry in _split_inline_toml_entries(body)
        )
        lines[index : index + 1] = replacement
        return lines, index + len(replacement)
    return None


def _codex_managed_block(
    runtime: str | Path,
    workspace: str | Path,
    *,
    dotted: bool,
) -> list[str]:
    runtime_src = json.dumps(str(Path(runtime).resolve() / "src"))
    workspace_value = json.dumps(str(Path(workspace).resolve()))
    if dotted:
        return [
            _CODEX_BEGIN,
            "mcp_servers.fusion_flow = { "
            f"command = {json.dumps(sys.executable)}, "
            'args = ["-m", "fusion_flow.mcp_server"], '
            "env = { "
            f"PYTHONPATH = {runtime_src}, "
            'PSI_WORKFLOW_HOST = "codex", '
            f"PSI_WORKFLOW_WORKSPACE = {workspace_value} "
            "} }",
            _CODEX_END,
        ]
    return [
        _CODEX_BEGIN,
        "[mcp_servers.fusion_flow]",
        f"command = {json.dumps(sys.executable)}",
        'args = ["-m", "fusion_flow.mcp_server"]',
        "[mcp_servers.fusion_flow.env]",
        f"PYTHONPATH = {runtime_src}",
        'PSI_WORKFLOW_HOST = "codex"',
        f"PSI_WORKFLOW_WORKSPACE = {workspace_value}",
        _CODEX_END,
    ]


def configure_codex_mcp(
    config: str | Path,
    runtime: str | Path,
    workspace: str | Path,
) -> Path:
    """Register the workflow MCP server in Codex config idempotently."""
    path = Path(config).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    config_data = tomllib.loads(text)
    lines = text.splitlines()
    if _CODEX_BEGIN in lines or _CODEX_END in lines:
        if lines.count(_CODEX_BEGIN) != 1 or lines.count(_CODEX_END) != 1:
            raise ValueError("Incomplete or duplicate dynamic-workflow config markers")
        start = lines.index(_CODEX_BEGIN)
        end = lines.index(_CODEX_END, start)
        dotted = any(
            line.lstrip().startswith("mcp_servers.fusion_flow =")
            for line in lines[start + 1 : end]
        )
    else:
        servers = config_data.get("mcp_servers", {})
        if not isinstance(servers, dict):
            raise ValueError("mcp_servers must be a TOML table")
        if "fusion_flow" in servers:
            return path  # An existing user-owned server is authoritative.
        expanded = _expand_inline_mcp_servers(lines) if "mcp_servers" in config_data else None
        if expanded is not None:
            lines, start = expanded
            end = start - 1
            dotted = True
        else:
            if lines and lines[-1].strip():
                lines.append("")
            start, end = len(lines), len(lines) - 1
            dotted = False

    lines[start : end + 1] = _codex_managed_block(
        runtime,
        workspace,
        dotted=dotted,
    )

    result = "\n".join(lines).rstrip() + "\n"
    tomllib.loads(result)
    path.write_text(result, encoding="utf-8")
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
        if h.get("name") != "openclaw":
            raise ValueError(
                "--register-plugin is only supported for OpenClaw"
            )

        if not (plugin_dir / "openclaw.plugin.json").is_file():
            raise FileNotFoundError(
                f"OpenClaw plugin manifest is missing: {plugin_dir}"
            )

        executable = h.get("executable") or shutil.which("openclaw")
        if not executable:
            raise FileNotFoundError(
                "OpenClaw executable is required to register the plugin"
            )

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
