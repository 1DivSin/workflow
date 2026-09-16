# Interactive Workflow Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local interactive installer that detects available agent hosts, lets the user choose one, installs this workflow, and reports success or failure.

**Architecture:** Keep one focused Python module with host descriptors, local detection, safe copy installation, and a terminal wizard. Detection and installation accept injected home/path data so tests never touch real agent directories. The first executable adapter is Codex-style skills installation; other detected CLIs are reported as unsupported until their native action is implemented.

**Tech Stack:** Python 3.11 standard library (`argparse`, `shutil`, `pathlib`, `importlib.metadata` not needed), pytest-compatible tests, existing package layout.

---

### Task 1: Define installer behavior with deterministic tests

**Files:**
- Create: `tests/test_install_workflow.py`
- Create: `install_workflow.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path

from install_workflow import detect_hosts, install_codex, choose_host


def test_detect_hosts_reports_codex_from_native_directories(tmp_path):
    (tmp_path / ".codex").mkdir()
    hosts = detect_hosts(home=tmp_path, which=lambda _name: None)
    assert [host.name for host in hosts] == ["Codex"]
    assert hosts[0].available is True


def test_choose_host_rejects_invalid_input_then_accepts_number(capsys):
    hosts = detect_hosts(home=Path("C:/missing"), which=lambda _name: "x")
    selected = choose_host(hosts, input_fn=iter(["9", "1"]).__next__, output_fn=print)
    assert selected.name == hosts[0].name
    assert "Invalid selection" in capsys.readouterr().out


def test_install_codex_copies_workflow_and_skill(tmp_path):
    source = tmp_path / "source"
    (source / "skills" / "dynamic-workflow").mkdir(parents=True)
    (source / "skills" / "dynamic-workflow" / "SKILL.md").write_text("---\nname: dynamic-workflow\n---\n", encoding="utf-8")
    result = install_codex(source, tmp_path / "home")
    assert result.ok is True
    assert (tmp_path / "home" / ".codex" / "dynamic-workflow" / "skills" / "dynamic-workflow" / "SKILL.md").exists()
    assert result.target.exists()


def test_install_codex_reports_missing_source(tmp_path):
    result = install_codex(tmp_path / "missing", tmp_path / "home")
    assert result.ok is False
    assert "source" in result.error.lower()
```

- [ ] **Step 2: Run the tests and verify they fail because the module is missing**

Run: `python -m unittest tests.test_install_workflow -v`
Expected: import failure with `ModuleNotFoundError: No module named 'install_workflow'`.

### Task 2: Implement detection, Codex installation, and wizard

**Files:**
- Modify: `install_workflow.py`
- Modify: `README.md`

- [ ] **Step 1: Implement the smallest public API used by the tests**

Implement `Host`, `InstallResult`, `detect_hosts`, `choose_host`, `install_codex`, `install_host`, and `main`. Use `shutil.copytree(..., dirs_exist_ok=True)` for updates, create a Windows junction with `mklink /J` when possible, fall back to a normal copied skills directory, and verify `SKILL.md` after installation. Directory-based hosts use their native user skills directory.

- [ ] **Step 2: Run the focused tests**

Run: `python -m unittest tests.test_install_workflow -v`
Expected: all tests pass.

- [ ] **Step 3: Document the command**

Add `python install_workflow.py` usage to `README.md`, including the four interactive phases and the restart reminder.

### Task 3: Verify the package

**Files:**
- No additional files.

- [ ] **Step 1: Run the full available checks**

Run: `python -m unittest discover -v`; `python -m compileall -q fusion_flow install_workflow.py`
Expected: unittest exits 0 and compileall exits 0.

- [ ] **Step 2: Inspect the diff and report any environment limitation**

Run: `git diff --check` and `git status --short`. If Git still cannot write the worktree index, report that limitation without changing repository metadata outside the workspace.
