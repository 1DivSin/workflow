import pytest
from fusion_flow import process

def test_windows_shim_with_spaces_is_wrapped_with_comspec(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.setenv("COMSPEC", r"C:\Windows\System32\cmd.exe")
    assert process._spawn_argv((r"C:\Program Files\npm\openclaw.cmd", "gateway", "--port", "18789")) == (r"C:\Windows\System32\cmd.exe", "/d", "/s", "/c", r'"C:\Program Files\npm\openclaw.cmd" gateway --port 18789')

def test_non_windows_commands_are_unchanged(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "linux")
    command = ("openclaw", "gateway")
    assert process._spawn_argv(command) == command

@pytest.mark.asyncio
async def test_spawn_helper_delegates_resolved_argv(monkeypatch):
    monkeypatch.setattr(process.sys, "platform", "win32")
    monkeypatch.delenv("COMSPEC", raising=False)
    seen = {}
    async def fake_spawn(*argv, **kwargs):
        seen["argv"] = argv
        return object()
    monkeypatch.setattr(process.asyncio_subprocess, "create_subprocess_exec", fake_spawn)
    result = await process.create_subprocess_exec(r"C:\npm\openclaw.cmd", "--version")
    assert result is not None
    assert seen["argv"][:3] == ("cmd.exe", "/d", "/s")
