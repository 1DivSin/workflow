"""Cross-platform subprocess helpers."""

from __future__ import annotations
import asyncio
import os
import signal
from contextlib import suppress

import anyio
import subprocess
import sys
from asyncio import subprocess as asyncio_subprocess
from typing import Any


def _is_windows_shim(command: tuple[str, ...]) -> bool:
    return (
        sys.platform == "win32" and bool(command) and command[0].lower().endswith((".cmd", ".bat"))
    )


def _spawn_argv(command: tuple[str, ...]) -> tuple[str, ...]:
    """Return an argv that asyncio can execute, including npm shims on Windows."""
    if not _is_windows_shim(command):
        return command
    comspec = os.environ.get("COMSPEC") or "cmd.exe"
    return (comspec, "/d", "/s", "/c", subprocess.list2cmdline(command))


async def create_subprocess_exec(*command: str, **kwargs: Any) -> asyncio_subprocess.Process:
    """Spawn *command*, including npm .cmd/.bat shims on Windows."""
    if os.name == "posix":
        kwargs.setdefault("start_new_session", True)
    with anyio.CancelScope(shield=True):
        return await asyncio_subprocess.create_subprocess_exec(
            *_spawn_argv(tuple(command)), **kwargs
        )


async def drain_stream(stream: asyncio.StreamReader | None) -> bytes:
    """Consume diagnostic output continuously, retaining only the last 64 KiB."""
    tail = bytearray()
    if stream is not None:
        while chunk := await stream.read(65536):
            tail.extend(chunk)
            del tail[:-65536]
    return bytes(tail)


async def close_subprocess(
    process: asyncio_subprocess.Process,
    stderr_task: asyncio.Task[bytes] | None = None,
) -> None:
    """Reap a host transport and its managed process group despite cancellation."""
    with anyio.CancelScope(shield=True):
        drains = [asyncio.create_task(drain_stream(process.stdout))]
        drains.append(stderr_task or asyncio.create_task(drain_stream(process.stderr)))
        try:
            if process.stdin is not None:
                process.stdin.close()
            if os.name == "posix":
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            elif process.returncode is None:
                # Kill the CLI tree as well as the wrapper (e.g. npm .cmd).
                try:
                    with anyio.fail_after(5):
                        await anyio.run_process(
                            ("taskkill", "/PID", str(process.pid), "/T", "/F"),
                            check=False,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                except (OSError, TimeoutError):
                    pass
            if process.returncode is None:
                with suppress(ProcessLookupError):
                    process.kill()
            with anyio.fail_after(5):
                await process.wait()
                await asyncio.gather(*drains)
        finally:
            for task in drains:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*drains, return_exceptions=True)
