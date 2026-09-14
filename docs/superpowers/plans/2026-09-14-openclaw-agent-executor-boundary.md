# OpenClaw Agent Executor Boundary Implementation Plan

> **For agentic workers:** This plan is executed inline in the current task because the user requested a PR attempt.

**Goal:** Remove the OpenClaw Agent Step path from the PSI session implementation by introducing a small executor contract and an OpenClaw CLI adapter.

**Architecture:** FusionFlow keeps graph scheduling, checkpointing, concurrency, and artifact validation. Agent Steps call an injected runtime with a typed request/result. The OpenClaw adapter invokes the host-owned `openclaw agent --json` CLI, so gateway authentication and pairing stay inside OpenClaw. Existing PSI and Human/Program paths remain unchanged in this PR.

**Tech Stack:** Python 3.11, standard-library `asyncio`, `dataclasses`, `Protocol`, OpenClaw CLI JSON output, unittest.

---

### Task 1: Add the runtime contract

**Files:**
- Create: `src/fusion_flow/agent_runtime.py`
- Test: `tests/test_agent_runtime.py`

- [x] Write tests for request validation, structured success parsing, and nonzero executor failure.
- [x] Run `PYTHONPATH=src python -m unittest tests.test_agent_runtime -v` and observe failure because the contract module is absent.
- [x] Implement `AgentRequest`, `AgentResult`, `AgentRuntime`, and a JSON envelope parser with no host imports.
- [x] Run the focused tests again and confirm they pass.

### Task 2: Implement the OpenClaw CLI executor

**Files:**
- Create: `src/fusion_flow/adapters/openclaw_cli.py`
- Modify: `src/fusion_flow/adapters/__init__.py`
- Test: `tests/test_openclaw_cli.py`

- [x] Add a fake Python command in the test that reads the prompt from stdin and emits the documented JSON envelope.
- [x] Run the focused test and observe failure because `OpenClawCliRuntime` is absent.
- [x] Implement async process execution with `openclaw agent --session-key ... --message-file - --json`, passing no token/password arguments.
- [x] Parse `final`, `status`, `sessionId`, usage, and structured errors; terminate on timeout.
- [x] Run the focused test and confirm success.

### Task 3: Route Agent Steps through the runtime

**Files:**
- Modify: `src/run_flow.py`
- Modify: `src/fusion_flow/host_adapter.py`
- Test: `tests/test_run_flow_runtime_boundary.py`

- [x] Add a source-boundary test proving `run_flow.py` routes through the injected host runtime and contains no direct PSI or raw OpenClaw client import.
- [x] Run it and observe failure because `_AgentSessionAdapter` only supports the PSI session path.
- [x] Resolve the host runtime in `host_adapter.py`, inject it into `_AgentSessionAdapter`, and use an opaque stable invocation session id.
- [x] Keep the existing PSI path as the fallback and leave Human/Program execution on that path.
- [x] Return an explicit capability error when an OpenClaw runtime is selected for a workflow containing Human or Program executors.
- [x] Run the focused test and the existing compile/test checks.

### Task 4: Document and verify

**Files:**
- Modify: `README.md`
- Modify: `package.json`

- [x] Document that OpenClaw auth is host-owned and the workflow invokes `openclaw agent --json`.
- [x] Add the unittest discovery command to the test script without adding runtime dependencies.
- [x] Run the full test command and inspect the diff.
- [x] Commit with `feat: decouple agent steps from psi runtime`.
