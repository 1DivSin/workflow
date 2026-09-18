from __future__ import annotations

import tempfile

import anyio

from flow_manage import _atomic_write, _parse_frontmatter, _validate_flow_name


def test_flow_persistence_handles_crlf_and_windows_names():
    metadata, body = _parse_frontmatter("---\r\ntitle: x\r\n---\r\nbody")
    assert metadata == {"title": "x"}
    assert body == "body"
    assert _validate_flow_name("CON")
    assert _validate_flow_name("report") is None


def test_flow_persistence_allows_concurrent_writes():
    async def run() -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = anyio.Path(raw) / "flow.md"

            async def write(index: int) -> None:
                await _atomic_write(path, f"value-{index}")

            for _ in range(3):
                async with anyio.create_task_group() as tasks:
                    for index in range(8):
                        tasks.start_soon(write, index)
            assert (await path.read_text()).startswith("value-")

    anyio.run(run)
