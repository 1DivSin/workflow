"""Cross-platform subprocess helpers."""
from __future__ import annotations
import os
import subprocess
import sys
from asyncio import subprocess as asyncio_subprocess
from typing import Any

def _is_windows_shim(command: tuple[str, ...]) -> bool:
    return sys.platform == "win32" and bool(command) and command[0].lower().endswith((".cmd", ".bat"))

def _spawn_argv(command: tuple[str, ...]) -> tuple[str, ...]:
    """Return an argv that asyncio can execute, including npm shims on Windows."""
    if not _is_windows_shim(command):
        return command
    comspec = os.environ.get("COMSPEC", "cmd.exe")
    return (comspec, "/d", "/s", "/c", subprocess.list2cmdline(command))

async def create_subprocess_exec(*command: str, **kwargs: Any) -> asyncio_subprocess.Process:
    """Spawn *command*, including npm .cmd/.bat shims on Windows."""
    return await asyncio_subprocess.create_subprocess_exec(*_spawn_argv(tuple(command)), **kwargs)
