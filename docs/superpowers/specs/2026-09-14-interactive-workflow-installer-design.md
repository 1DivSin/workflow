# Interactive Workflow Installer Design

## Goal

Add a local, step-by-step installer for this workflow package. The installer
must detect usable agent hosts first, let the user select one explicitly, run
that host's native installation path, and print an unambiguous success or
failure result.

## Detection

Detection is local and conservative. Each host adapter reports a host only
when its known CLI is available or its native configuration directory already
exists. The first version covers:

- **Codex**: `codex` on `PATH`, `~/.codex`, or `~/.agents/skills`.
- **Claude**: `claude` on `PATH` or `~/.claude`.
- **Cursor**: `cursor` on `PATH` or its user configuration directory.
- **OpenCode**: `opencode` on `PATH` or its user configuration directory.
- **Gemini**: `gemini` on `PATH` or its user configuration directory.
- **Copilot**: `copilot` on `PATH` or its user configuration directory.

Detection never starts an agent, contacts a network service, or guesses a
different host after selection. Results include the host name, detection
evidence, and planned target path.

## Interactive flow

The command runs as a terminal wizard:

1. Print the detected hosts and their evidence.
2. Ask for one numeric selection, with `q` to cancel.
3. Show the selected host and target, then ask for an explicit confirmation.
4. Install the workflow using the selected host adapter.
5. Print `SUCCESS` with host and target, or `FAILURE` with a stable reason.

Non-interactive execution fails with a clear message instead of selecting a
default host. Invalid selections and cancellation do not modify files.

## Installation

The workflow source is copied into the selected host's native skills location,
using a single directory named `dynamic-workflow`. Existing installations are
updated in place only after the source and destination have passed path-safety
checks. The Codex adapter follows superpowers' proven layout: it installs the
repository payload under `~/.codex/dynamic-workflow` and exposes its `skills`
directory through `~/.agents/skills/dynamic-workflow` (junction on Windows,
symlink where supported). Other hosts use their documented native CLI or
configuration path. Hosts without a writable native directory produce a
failure result rather than a silent copy to another location.

## Error handling and verification

Each adapter returns a structured result with `ok`, `host`, `target`, and an
optional error. The CLI renders that result for humans and exits non-zero on
failure. Installation is best-effort atomic: temporary copies are written
before replacing the destination. Verification checks that the installed
directory exists and contains the workflow's `SKILL.md`.

## Testing

Keep tests local and deterministic. Test detection with injected paths and
commands, selection validation, cancellation, successful installation into a
temporary directory, and failure reporting. No network or real user
directories are touched by tests.
