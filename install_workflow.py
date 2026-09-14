"""Interactive local installer for the Dynamic Workflow skill."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


@dataclass(frozen=True)
class Host:
    name: str
    command: str
    evidence: tuple[str, ...]
    available: bool


@dataclass(frozen=True)
class InstallResult:
    ok: bool
    host: str
    target: Path
    error: str = ""


def _default_home() -> Path:
    return Path(os.environ.get("USERPROFILE") or os.environ.get("HOME") or Path.home())


def _host_specs(home: Path) -> tuple[tuple[str, str, tuple[Path, ...]], ...]:
    return (
        ("Codex", "codex", (home / ".codex", home / ".agents" / "skills")),
        ("Claude", "claude", (home / ".claude",)),
        ("Cursor", "cursor", (home / ".cursor", home / "AppData" / "Roaming" / "Cursor")),
        ("OpenCode", "opencode", (home / ".config" / "opencode", home / ".opencode")),
        ("Gemini", "gemini", (home / ".gemini",)),
        ("Copilot", "copilot", (home / ".copilot",)),
    )


def detect_hosts(*, home: Path | None = None, which: Callable[[str], str | None] = shutil.which) -> list[Host]:
    """Return locally detected hosts without starting a process or using a network."""

    home = (home or _default_home()).expanduser()
    hosts: list[Host] = []
    for name, command, directories in _host_specs(home):
        evidence = []
        command_path = which(command)
        if command_path:
            evidence.append(f"{command} ({command_path})")
        evidence.extend(str(path) for path in directories if path.is_dir())
        if evidence:
            hosts.append(Host(name, command, tuple(evidence), True))
    return hosts


def choose_host(
    hosts: Iterable[Host],
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], object] = print,
) -> Host:
    """Interactively choose one detected host; raise ``KeyboardInterrupt`` to cancel."""

    choices = list(hosts)
    if not choices:
        raise ValueError("No supported agent host detected.")
    while True:
        answer = input_fn("Select agent (number, q to cancel): ").strip().lower()
        if answer == "q":
            raise KeyboardInterrupt
        if answer.isdigit() and 1 <= int(answer) <= len(choices):
            return choices[int(answer) - 1]
        output_fn("Invalid selection. Enter one of the listed numbers or q.")


def _copy_tree(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as raw:
        staged = Path(raw) / destination.name
        shutil.copytree(source, staged)
        if destination.exists() or destination.is_symlink():
            if destination.is_dir() and not destination.is_symlink():
                shutil.rmtree(destination)
            else:
                destination.unlink()
        shutil.copytree(staged, destination)


def _expose_skills(skills_source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_dir() and not target.is_symlink():
            shutil.rmtree(target)
        else:
            target.unlink()
    if os.name == "nt":
        completed = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(target), str(skills_source)],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode == 0:
            return
    try:
        target.symlink_to(skills_source, target_is_directory=True)
    except OSError:
        shutil.copytree(skills_source, target)


def install_codex(source: Path, home: Path | None = None) -> InstallResult:
    """Install the package and expose its skill through Codex discovery."""

    source = source.resolve()
    home = (home or _default_home()).expanduser().resolve()
    target = home / ".agents" / "skills" / "dynamic-workflow"
    if not source.is_dir():
        return InstallResult(False, "Codex", target, f"Workflow source does not exist: {source}")
    try:
        installed = home / ".codex" / "dynamic-workflow"
        _copy_tree(source, installed)
        skills = installed / "skills" / "dynamic-workflow"
        if not skills.exists():
            skills.mkdir(parents=True)
            source_skill = source / "SKILL.md"
            if not source_skill.is_file():
                raise FileNotFoundError(f"Workflow source is missing SKILL.md: {source_skill}")
            shutil.copy2(source_skill, skills / "SKILL.md")
        _expose_skills(skills, target)
        if not (target / "SKILL.md").is_file():
            raise OSError("Installed skill verification failed: SKILL.md is missing")
        return InstallResult(True, "Codex", target)
    except (OSError, shutil.Error) as error:
        return InstallResult(False, "Codex", target, str(error))


def install_host(host: Host, source: Path, home: Path | None = None) -> InstallResult:
    if host.name == "Codex":
        return install_codex(source, home)
    skill_roots = {
        "Claude": ".claude/skills",
        "Cursor": ".cursor/skills",
        "OpenCode": ".config/opencode/skills",
        "Gemini": ".gemini/skills",
        "Copilot": ".copilot/skills",
    }
    root = (home or _default_home()).expanduser().resolve()
    target = root / skill_roots.get(host.name, "skills") / "dynamic-workflow"
    source_skill = source.resolve() / "SKILL.md"
    if not source_skill.is_file():
        return InstallResult(False, host.name, target, f"Workflow source is missing SKILL.md: {source_skill}")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=target.parent) as raw:
            staged = Path(raw) / target.name
            staged.mkdir()
            shutil.copy2(source_skill, staged / "SKILL.md")
            if target.exists() or target.is_symlink():
                if target.is_dir() and not target.is_symlink():
                    shutil.rmtree(target)
                else:
                    target.unlink()
            shutil.copytree(staged, target)
        if not (target / "SKILL.md").is_file():
            raise OSError("Installed skill verification failed: SKILL.md is missing")
        return InstallResult(True, host.name, target)
    except (OSError, shutil.Error) as error:
        return InstallResult(False, host.name, target, str(error))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install Dynamic Workflow into a detected agent host")
    parser.add_argument("--source", type=Path, default=Path(__file__).parent)
    args = parser.parse_args(argv)
    hosts = detect_hosts()
    print("Detected agent hosts:")
    for index, host in enumerate(hosts, 1):
        print(f"  {index}. {host.name} - {', '.join(host.evidence)}")
    try:
        selected = choose_host(hosts)
        print(f"Selected: {selected.name}")
        if input("Install this workflow? [y/N]: ").strip().lower() not in {"y", "yes"}:
            print("CANCELLED: installation not changed")
            return 1
        result = install_host(selected, args.source)
    except (KeyboardInterrupt, EOFError):
        print("CANCELLED: installation not changed")
        return 1
    except ValueError as error:
        print(f"FAILURE: {error}")
        return 1
    if result.ok:
        print(f"SUCCESS: {result.host} installed at {result.target}")
        print("Restart the agent to discover the workflow.")
        return 0
    print(f"FAILURE: {result.host}: {result.error}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
