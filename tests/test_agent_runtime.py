from __future__ import annotations

import unittest
import importlib.util
import sys
from pathlib import Path


_MODULE_PATH = Path(__file__).parents[1] / "src" / "fusion_flow" / "agent_runtime.py"
_SPEC = importlib.util.spec_from_file_location("fusion_flow.agent_runtime", _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load {_MODULE_PATH}")
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)
AgentRequest = _MODULE.AgentRequest
AgentResult = _MODULE.AgentResult
parse_agent_result = _MODULE.parse_agent_result


class AgentRuntimeContractTests(unittest.TestCase):
    def test_request_requires_prompt_session_and_workspace(self) -> None:
        with self.assertRaises(ValueError):
            AgentRequest(prompt="", session_id="step-1", workspace=Path("."))
        with self.assertRaises(ValueError):
            AgentRequest(prompt="work", session_id="", workspace=Path("."))

    def test_parse_success_envelope_preserves_text_session_and_usage(self) -> None:
        result = parse_agent_result(
            {
                "ok": True,
                "status": "ok",
                "final": "done",
                "sessionId": "session-1",
                "usage": {"input": 12, "output": 4},
            }
        )

        self.assertEqual(
            result,
            AgentResult(
                status="ok",
                text="done",
                session_id="session-1",
                usage={"input": 12, "output": 4},
            ),
        )

    def test_parse_failure_envelope_preserves_error(self) -> None:
        result = parse_agent_result(
            {
                "ok": False,
                "status": "timeout",
                "error": {"message": "agent timed out", "kind": "timeout"},
            }
        )

        self.assertEqual(result.status, "timeout")
        self.assertEqual(result.error, "agent timed out")
        self.assertFalse(result.ok)


if __name__ == "__main__":
    unittest.main()
